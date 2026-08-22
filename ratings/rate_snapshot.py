"""Build the lean rating core and its explicitly separate audit layers.

The production skill model has two views of one binary W/L/D evidence stream:
causal Glicko-2 (``canonical``) and retrospective Whole-History Rating
(``whr``). ``method`` is retained as a zero-extra-pass research diagnostic.
Side-specific performance/integrity sleeves and the era premium are not
production ratings: they either fail to define one paired likelihood or add a
scenario assumption that bout outcomes cannot identify.

The public career functional is Symon Career Skill Mass: the sum of positive
annual WHR skill above that year's field mean, with at most one contribution
per active year. Five- and ten-year Symon scores are separate peak diagnostics.
Legacy period tables remain temporarily for compatibility, never as the public
All-time definition.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Package import shim: let `python ratings/rate_snapshot.py` work as well as `-m`.
if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ratings.glicko2_engine import DEFAULT_TAU, RatingEngine
from ratings.dominance import per_fight_dominance, per_fighter_dominance
from ratings.constants import (
    ACTIVITY_MU_PENALTY_CAP,
    ACTIVITY_MU_PENALTY_FULL_MONTHS,
    ACTIVITY_MU_PENALTY_START_MONTHS,
    WHR_STREAM,
    rename_rating_columns,
)
from ratings.diagnostics import (
    calibration_residual_rows,
    division_entropy_rows,
)
from ratings.division_resume import division_resume_rows, primary_division_rows
from ratings.integrity_adjustment import build_integrity_appearances
from ratings.appearance_context import peak_appearance_quality
from ratings.symon_score import career_skill_mass, symon_peak_score, symon_prime_score
from ratings.whr import run_whr
from ratings.performance_adjustment import build_performance_appearances
from ratings.performance_adjustment import _group_bounds, normalize_division_label
from loaders.integrity_flags import (
    INTEGRITY_COLUMNS,
    build_integrity_flags,
    confirmed_counts,
)
from loaders.odds_loader import has_odds_artifact, load_odds_lines
from loaders.ufcstats_loader import METHOD_SCORES


# ---------------------------------------------------------------------------
# Helpers


def _ensure_integrity_columns(fights: pd.DataFrame) -> pd.DataFrame:
    out = fights.copy()
    for col in INTEGRITY_COLUMNS:
        if col == "fight_url":
            continue
        if col not in out.columns:
            out[col] = False if col in {"ped_confirmed", "is_dq", "missed_weight"} else None
    for col in ("ped_confirmed", "is_dq", "missed_weight"):
        out[col] = out[col].fillna(False).astype(bool)
    return out


def _iter_event_bouts(fights: pd.DataFrame, columns: list[str]):
    """Yield ``(event_date, event_name, bouts)`` per event from column arrays.

    A ``groupby(...).to_dict("records")`` per event costs more than the Glicko
    arithmetic it feeds once the fight table carries tens of thousands of
    events, so the frame is converted to arrays once and sliced.
    """
    f = fights.sort_values(["event_date", "event_name"]).reset_index(drop=True)
    arrays = {c: f[c].to_numpy() for c in columns}
    dates = f["event_date"].to_numpy()
    names = f["event_name"].to_numpy()
    for lo, hi in zip(*_group_bounds(f["event_date"], f["event_name"])):
        bouts = [{c: arrays[c][k] for c in columns} for k in range(lo, hi)]
        yield pd.Timestamp(dates[lo]), names[lo], bouts


def _run_canonical_engine(fights: pd.DataFrame, tau: float) -> RatingEngine:
    engine = RatingEngine(tau=tau)
    columns = ["fighter_a", "fighter_b", "winner", "is_draw", "method_score_winner"]
    for event_date, event_name, bouts in _iter_event_bouts(fights, columns):
        engine.process_event(event_date, event_name, bouts)
    return engine


def _attach_org_only_weights(fights: pd.DataFrame) -> pd.DataFrame:
    """Set ``weight_a``/``weight_b`` to the per-fight ``org_weight`` only.

    UFC bouts are unchanged at 1.0. Non-UFC weights are accepted only in the
    explicitly requested experimental cross-org scope.
    """
    out = fights.copy()
    ow = pd.to_numeric(out.get("org_weight", 1.0), errors="coerce")
    ow = ow.fillna(1.0) if hasattr(ow, "fillna") else 1.0
    out["weight_a"] = ow
    out["weight_b"] = ow
    return out


def _stream_current_columns(
    engine_current: pd.DataFrame,
    history: pd.DataFrame,
    *,
    suffix: str,
) -> pd.DataFrame:
    """Translate a weighted-engine's `current_table()` into per-stream columns."""
    out = engine_current.rename(columns={
        "mu": f"mu_{suffix}",
        "phi": f"phi_{suffix}",
        "sigma": f"sigma_{suffix}",
    })
    out = out.drop(columns=["last_event_date", "peak_mu"], errors="ignore")
    return out[["fighter", f"mu_{suffix}", f"phi_{suffix}", f"sigma_{suffix}"]]


def _attach_rank_and_delta(
    current: pd.DataFrame,
    *,
    suffix: str,
    baseline_col: str,
    min_fights: int,
) -> pd.DataFrame:
    rating_col = f"mu_{suffix}"
    if rating_col not in current.columns:
        return current
    eligible = current["rating_periods"].fillna(0) >= min_fights
    current[f"delta_mu_{suffix}"] = current[rating_col] - current[baseline_col]
    current[f"rank_{suffix}"] = pd.NA
    current.loc[eligible, f"rank_{suffix}"] = (
        current.loc[eligible, rating_col]
        .rank(method="min", ascending=False)
        .astype("Int64")
    )
    return current


def _attach_activity_adjusted_mu(current: pd.DataFrame, snapshot_max_date: pd.Timestamp) -> pd.DataFrame:
    """Add current-view inactivity penalties without mutating rating history."""
    out = current.copy()
    last = pd.to_datetime(out.get("last_event_date"), errors="coerce")
    months = (pd.Timestamp(snapshot_max_date) - last).dt.days / 30.4375
    months = months.clip(lower=0.0)
    denom = max(ACTIVITY_MU_PENALTY_FULL_MONTHS - ACTIVITY_MU_PENALTY_START_MONTHS, 1.0)
    level = ((months - ACTIVITY_MU_PENALTY_START_MONTHS) / denom).clip(lower=0.0, upper=1.0)
    # Lower-confidence fighters should not be over-penalized; high phi already
    # warns the reader. A 350-phi debut has near-zero structural penalty.
    phi = pd.to_numeric(out.get("phi_canonical"), errors="coerce").fillna(350.0)
    confidence = (1.0 - (phi / 350.0).clip(lower=0.0, upper=1.0))
    out["months_inactive"] = months.round(2)
    out["activity_mu_penalty"] = (ACTIVITY_MU_PENALTY_CAP * (level ** 2) * confidence).round(6)
    for col in [c for c in out.columns if c.startswith("mu_") and not c.endswith("_activity_adjusted")]:
        out[f"{col}_activity_adjusted"] = (
            pd.to_numeric(out[col], errors="coerce") - out["activity_mu_penalty"]
        )
    return out


def _attach_record(current: pd.DataFrame, fights: pd.DataFrame) -> pd.DataFrame:
    """Attach each fighter's rated win/loss/draw record.

    The board already carried an appearance count, which cannot distinguish a
    fighter who has never lost from one who splits every card. That difference
    is exactly what decides how far a Bradley--Terry rating can travel, so it
    belongs beside the rating.
    """
    for col in ("wins", "losses", "draws"):
        current[col] = 0
    if fights is None or fights.empty:
        return current
    sides = [
        fights[[side, "winner", "is_draw"]].rename(columns={side: "fighter"})
        for side in ("fighter_a", "fighter_b")
    ]
    long = pd.concat(sides, ignore_index=True, sort=False).dropna(subset=["fighter"])
    long["is_draw"] = long["is_draw"].fillna(False).astype(bool)
    long["win"] = long["winner"].eq(long["fighter"]) & ~long["is_draw"]
    long["loss"] = long["winner"].notna() & ~long["winner"].eq(long["fighter"]) & ~long["is_draw"]
    record = long.groupby("fighter").agg(
        wins=("win", "sum"), losses=("loss", "sum"), draws=("is_draw", "sum"),
    ).reset_index()
    out = current.drop(columns=["wins", "losses", "draws"]).merge(
        record, on="fighter", how="left")
    for col in ("wins", "losses", "draws"):
        out[col] = out[col].fillna(0).astype(int)
    return out


def _attach_recent_division_gender(current: pd.DataFrame, fights: pd.DataFrame) -> pd.DataFrame:
    """Attach each fighter's most recent UFC division and inferred gender split."""
    if fights is None or fights.empty:
        current["recent_division"] = pd.NA
        current["gender"] = pd.NA
        return current
    f = fights[["event_date", "event_name", "fighter_a", "fighter_b", "weight_class"]].copy()
    f["event_date"] = pd.to_datetime(f["event_date"], errors="coerce")
    f["recent_division"] = f["weight_class"].map(normalize_division_label)
    a = f[["event_date", "event_name", "recent_division", "fighter_a"]].rename(columns={"fighter_a": "fighter"})
    b = f[["event_date", "event_name", "recent_division", "fighter_b"]].rename(columns={"fighter_b": "fighter"})
    recent = (
        pd.concat([a, b], ignore_index=True, sort=False)
        .dropna(subset=["fighter"])
        .sort_values(["fighter", "event_date", "event_name"])
        .groupby("fighter", as_index=False)
        .last()[["fighter", "recent_division"]]
    )
    recent["gender"] = np.where(
        recent["recent_division"].fillna("").astype(str).str.startswith("Women's"),
        "F",
        "M",
    )
    return current.merge(recent, on="fighter", how="left")


def _print_top(
    current: pd.DataFrame,
    *,
    rating_col: str,
    extra_cols: list[str],
    title: str,
    n: int = 20,
    min_fights: int = 3,
) -> None:
    eligible = current[current["rating_periods"].fillna(0) >= min_fights].copy()
    eligible = eligible.dropna(subset=[rating_col])
    if eligible.empty:
        return
    cols = ["fighter", rating_col, *[c for c in extra_cols if c in eligible.columns]]
    out = eligible.sort_values(rating_col, ascending=False).head(n)[cols]
    out = rename_rating_columns(out)
    print(f"\n=== {title} ===")
    print(out.to_string(index=False))


# ---------------------------------------------------------------------------
# Main


def run(
    snapshot_dir: Path,
    tau: float = DEFAULT_TAU,
    min_fights: int = 3,
    *,
    mdabbert_csv: Path | None = None,
    include_experimental_crossorg: bool = False,
) -> dict:
    snapshot_dir = Path(snapshot_dir).resolve()
    fights = pd.read_parquet(snapshot_dir / "canonical_fights.parquet")
    rounds = pd.read_parquet(snapshot_dir / "canonical_rounds.parquet")
    # The production scope is UFC-only. Existing cross-org weights were derived
    # from fighters' eventual UFC careers, so automatically consuming them here
    # would leak future information into historical evidence. They remain an
    # explicitly requested research scope until weights are fold-local or
    # outcome-independent.
    fights["org_weight"] = 1.0
    if "source" not in fights.columns:
        fights["source"] = "ufc"
    crossorg_path = snapshot_dir / "crossorg_fights.parquet"
    if crossorg_path.exists() and include_experimental_crossorg:
        crossorg = pd.read_parquet(crossorg_path)
        if not crossorg.empty:
            if "org_weight" not in crossorg.columns:
                crossorg["org_weight"] = 1.0
            fights = pd.concat([fights, crossorg], ignore_index=True, sort=False)
            print(f"[rate] merged {len(crossorg):,} cross-org bouts "
                  f"(EXPERIMENTAL; orgs: "
                  f"{sorted(crossorg.get('org', pd.Series(dtype=str)).dropna().unique())})")
    elif crossorg_path.exists():
        print("[rate] cross-org artifact quarantined from the UFC production core")

    fights["event_date"] = pd.to_datetime(fights["event_date"])
    if "method_class" in fights.columns:
        recalculated_method_scores = fights["method_class"].map(METHOD_SCORES)
        fights["method_score_winner"] = recalculated_method_scores.combine_first(
            pd.to_numeric(fights.get("method_score_winner"), errors="coerce")
        )
    fights = fights.sort_values(["event_date", "event_name"]).reset_index(drop=True)

    # ------------------------------------------------------------------
    # Integrity flags (PED + DQ + missed-weight)
    integrity = build_integrity_flags(fights, mdabbert_csv=mdabbert_csv)
    # Merge flags onto the fight rows for the audit layers and exclusions.
    fights = fights.drop(columns=[c for c in INTEGRITY_COLUMNS if c != "fight_url" and c in fights.columns], errors="ignore")
    fights = fights.merge(integrity, on="fight_url", how="left")
    fights = _ensure_integrity_columns(fights)

    # Drop excluded bouts before rating. Keep them for audit if present.
    rated_fights = fights[~fights["is_excluded"]].copy() if "is_excluded" in fights.columns else fights.copy()

    # ------------------------------------------------------------------
    # Canonical + method base engine (one pass, two ratings)
    base_engine = _run_canonical_engine(rated_fights, tau=tau)
    history = base_engine.history_df()
    current = base_engine.current_table().drop(
        columns=["peak_mu_canonical", "peak_mu_method"],
        errors="ignore",
    )
    fight_counts = history.groupby("fighter").size().rename("rating_periods").reset_index()
    current = current.merge(fight_counts, on="fighter", how="left")

    # ------------------------------------------------------------------
    # Audit layers. These explain source coverage, method/dominance and policy
    # questions, but they do not mutate the production skill likelihood.
    integrity_app = build_integrity_appearances(rated_fights)

    odds_lines = load_odds_lines(snapshot_dir) if has_odds_artifact(snapshot_dir) else pd.DataFrame()
    # Judge scorecards feed the decision "round win gap" dominance component.
    scorecards_path = snapshot_dir / "datalab_scorecards.parquet"
    scorecards = pd.read_parquet(scorecards_path) if scorecards_path.exists() else None
    fight_dom = per_fight_dominance(rounds, rated_fights, scorecards=scorecards)
    fighter_dom = per_fighter_dominance(fight_dom, rated_fights)

    perf_app = build_performance_appearances(
        rated_fights,
        history,
        odds_lines if not odds_lines.empty else None,
        fight_dominance=fight_dom,
    )

    # Persist appearance audit frames.
    integrity_app.to_parquet(snapshot_dir / "integrity_appearances.parquet", index=False)
    perf_app.to_parquet(snapshot_dir / "performance_appearances.parquet", index=False)

    # ------------------------------------------------------------------
    # WHR is the retrospective estimator of the same binary/draw evidence used
    # by canonical Glicko. It receives one shared source weight per bout and no
    # implicit quality-score column. Era is neutral by default because a common
    # additive era term cancels from every within-era Bradley--Terry matchup.
    whr_history = run_whr(_attach_org_only_weights(rated_fights))
    whr_history.to_parquet(snapshot_dir / "ratings_history_whr.parquet", index=False)
    whr_current = (
        whr_history.sort_values(["fighter", "event_date"])
        .groupby("fighter")["mu_whr"]
        .last()
        .reset_index()
    )
    current = current.merge(whr_current, on="fighter", how="left")

    # One all-time functional and two clearly separate period diagnostics. The
    # score inputs are only latent WHR appearances; title labels, opponent rank,
    # streaks, activity bonuses and market prices are not counted again.
    symon_tables = (
        (career_skill_mass(whr_history), "symon_career"),
        (symon_prime_score(whr_history), "symon_prime"),
        (symon_peak_score(whr_history), "symon_peak"),
    )
    for table, prefix in symon_tables:
        renamed = table.rename(
            columns={
                c: (f"{prefix}_skill_mass" if prefix == "symon_career" and c == "score"
                    else f"{prefix}_score" if c == "score"
                    else f"{prefix}_{c}")
                for c in table.columns
                if c != "fighter"
            }
        )
        current = current.merge(renamed, on="fighter", how="left")

    current = _attach_record(current, rated_fights)
    current = _attach_recent_division_gender(current, rated_fights)
    current = _attach_activity_adjusted_mu(current, rated_fights["event_date"].max())

    # Opponent context per appearance. Division boards score a fighter inside
    # one weight class from it; the latent skill model does not read it.
    peak_quality = peak_appearance_quality(rated_fights, history)

    # Division-context all-time rows. These are the correct source for
    # divisional leaderboards; they use only bouts fought in that division and
    # shrink short title cameos toward the divisional pool.
    division_resume = division_resume_rows(whr_history, peak_quality)
    division_resume.to_parquet(snapshot_dir / "division_resume.parquet", index=False)
    current = current.drop(
        columns=[
            "primary_division", "primary_division_share", "primary_division_reliability",
            "career_division", "career_division_reliability",
            "current_division", "current_division_reliability",
        ],
        errors="ignore",
    )
    current = current.merge(primary_division_rows(division_resume), on="fighter", how="left")

    # ------------------------------------------------------------------
    # Integrity counts
    counts = confirmed_counts(integrity)
    current = current.merge(counts, on="fighter", how="left")
    for col in ("ped_confirmed_fights", "dq_wins", "missed_weight_wins"):
        if col not in current.columns:
            current[col] = 0
        current[col] = current[col].fillna(0).astype(int)

    # 203 fighters tie on mu_canonical (mostly unrated debutants at the 1500
    # default), and sort_values defaults to a non-stable quicksort, so two
    # identical runs used to emit byte-different row orders. Tie-break on the
    # name so a rebuild is reproducible and can be diffed against its inputs.
    current = current.sort_values(
        ["mu_canonical", "fighter"], ascending=[False, True]
    ).reset_index(drop=True)

    # ------------------------------------------------------------------
    # Persist
    history.to_parquet(snapshot_dir / "ratings_history.parquet", index=False)
    current.to_parquet(snapshot_dir / "ratings_current.parquet", index=False)

    # Audit exports.
    ped_audit_cols = [
        "fight_url", "event_date", "event_name", "fighter_a", "fighter_b",
        "winner", "ped_flagged_fighter", "ped_confirmation_detail",
    ]
    ped_audit = fights[fights["ped_confirmed"]].loc[:, [c for c in ped_audit_cols if c in fights.columns]]
    ped_audit.to_csv(snapshot_dir / "ped_confirmed_bouts.csv", index=False)

    mw_audit_cols = [
        "fight_url", "event_date", "event_name", "fighter_a", "fighter_b",
        "winner", "missed_weight_fighter", "missed_weight_source", "weight_class",
    ]
    mw_audit = fights[fights["missed_weight"]].loc[:, [c for c in mw_audit_cols if c in fights.columns]]
    mw_audit.to_csv(snapshot_dir / "missed_weight_bouts.csv", index=False)

    fight_dom.to_parquet(snapshot_dir / "fight_dominance.parquet", index=False)
    fighter_dom.to_parquet(snapshot_dir / "fighter_dominance.parquet", index=False)

    # Build-time diagnostic tables. The notebook reads these directly.
    fighters_path = snapshot_dir / "canonical_fighters.parquet"
    fighters = pd.read_parquet(fighters_path) if fighters_path.exists() else pd.DataFrame()
    calibration_residual_rows(history, rated_fights, fighters).to_parquet(
        snapshot_dir / "calibration_residuals.parquet",
        index=False,
    )
    division_entropy_rows(history, rated_fights).to_parquet(
        snapshot_dir / "division_entropy.parquet",
        index=False,
    )

    # Remove artifacts a previous pipeline version wrote that this one does not,
    # so a rebuilt snapshot never carries a stale file alongside fresh ones.
    for legacy in (
        "ratings_history_ped_adjusted.parquet",
        "ratings_history_odds_adjusted.parquet",
        "odds_adjustment_distribution.parquet",
        # Retired 2026-08-19: each cost a full smoother pass and nothing read it.
        "ratings_history_whr_integrity.parquet",
        "ratings_history_whr_performance.parquet",
        "ratings_history_whr_integrity_performance.parquet",
        "ratings_history_method_integrity.parquet",
        "ratings_history_method_performance.parquet",
        "ratings_history_method_integrity_performance.parquet",
        "sleeve_attribution.parquet",
    ):
        legacy_path = snapshot_dir / legacy
        if legacy_path.exists():
            try:
                legacy_path.unlink()
            except OSError:
                pass

    # ------------------------------------------------------------------
    # Reporting
    print(f"tau used: {tau}")
    print(f"events processed: {history['event_date'].nunique()}")
    print(f"fighter-event rows in history: {len(history)}")
    print(f"unique fighters rated: {len(current)}")
    print(
        f"integrity flags  PED={int(integrity['ped_confirmed'].fillna(False).sum())} "
        f" DQ={int(integrity['is_dq'].fillna(False).sum())} "
        f" missed_weight={int(integrity['missed_weight'].fillna(False).sum())}"
    )
    cov_rows = int((odds_lines.get('odds_data_quality', pd.Series(dtype=object)).eq('ok')).sum()) if not odds_lines.empty else 0
    print(f"odds-covered fights (ok-quality rows): {cov_rows}")

    print(
        "headline = Symon Career Skill Mass over binary, era-neutral WHR; "
        "Prime and Peak are separate diagnostics."
    )
    _print_top(
        current,
        rating_col="symon_career_skill_mass",
        extra_cols=[
            "symon_career_contributing_years", "symon_career_peak_year_excess",
            "symon_prime_score", "symon_peak_score", "career_division", "rating_periods",
        ],
        title="HEADLINE — Top 25 by Symon Career Skill Mass",
        n=25, min_fights=0,
    )
    _print_top(
        current,
        rating_col="symon_prime_score",
        extra_cols=["symon_prime_raw_mean", "symon_prime_window_fights", "symon_peak_score"],
        title="DIAGNOSTIC — Top 25 ten-year Prime (minimum 13 appearances)",
        n=25, min_fights=0,
    )
    _print_top(
        current,
        rating_col="symon_peak_score",
        extra_cols=["symon_peak_raw_mean", "symon_peak_window_fights", "symon_prime_score"],
        title="DIAGNOSTIC — Top 25 five-year Peak (minimum 8 appearances)",
        n=25, min_fights=0,
    )

    return {
        "history_rows": int(len(history)),
        "current_fighters": int(len(current)),
        "events_processed": int(history["event_date"].nunique()),
        "ped_confirmed_fights": int(integrity["ped_confirmed"].fillna(False).sum()),
        "dq_fights": int(integrity["is_dq"].fillna(False).sum()),
        "missed_weight_fights": int(integrity["missed_weight"].fillna(False).sum()),
        "odds_covered_fights": cov_rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot-dir", required=True, help="data/snapshots/<date>")
    parser.add_argument("--tau", type=float, default=DEFAULT_TAU)
    parser.add_argument("--min-fights", type=int, default=3, help="ranking eligibility threshold")
    parser.add_argument(
        "--mdabbert-csv",
        type=str,
        default=None,
        help="Optional path to mdabbert ufc-master.csv for missed-weight cross-check.",
    )
    parser.add_argument(
        "--experimental-crossorg",
        action="store_true",
        help=(
            "Explicitly include staged cross-org bouts. Research only: current "
            "org weights are not yet cutoff-local."
        ),
    )
    args = parser.parse_args()
    run(
        Path(args.snapshot_dir).resolve(),
        tau=args.tau,
        min_fights=args.min_fights,
        mdabbert_csv=Path(args.mdabbert_csv).resolve() if args.mdabbert_csv else None,
        include_experimental_crossorg=args.experimental_crossorg,
    )


if __name__ == "__main__":
    main()
