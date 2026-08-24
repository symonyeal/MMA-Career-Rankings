"""Build the lean rating core and its explicitly separate audit layers.

The production skill model has two views of one binary W/L/D evidence stream:
causal Glicko-2 (``canonical``) and retrospective Whole-History Rating
(``whr``). ``method`` is retained as a zero-extra-pass research diagnostic.
Side-specific performance/integrity sleeves and the era premium are not
production ratings: they either fail to define one paired likelihood or add a
scenario assumption that bout outcomes cannot identify.

The skill career functional is Symon Career Skill Mass: the sum of positive
annual WHR skill above that year's global contender line, with at most one
contribution per active year. The public legacy board adds a separate,
auditable championship resume ledger on top of that skill mass. Five- and
ten-year Symon scores are separate peak diagnostics.
"""
from __future__ import annotations

import argparse
import json
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
    rename_rating_columns,
)
from ratings.diagnostics import (
    calibration_residual_rows,
    division_entropy_rows,
)
from ratings.division_resume import division_resume_rows, primary_division_rows
from ratings.integrity_adjustment import build_integrity_appearances
from ratings.appearance_context import peak_appearance_quality
from ratings.symon_score import (
    DEFAULT_CAREER_REFERENCE,
    career_skill_mass,
    parse_reference,
    symon_peak_score,
    symon_prime_score,
)
from ratings.legacy_resume import public_legacy_score_rows
from ratings.whr import run_whr
from ratings.age import load_birth_dates
from ratings.performance_adjustment import build_performance_appearances
from ratings.performance_adjustment import _group_bounds, normalize_division_label
from loaders.integrity_flags import (
    INTEGRITY_COLUMNS,
    build_integrity_flags,
    confirmed_counts,
)
from loaders.odds_loader import has_odds_artifact, load_odds_lines
from ratings.rules_era import RULES_ERA_WEIGHT, label_rules_era, rules_era_factor
from ratings.scope import (  # noqa: F401
    DEFAULT_PUBLISHED_SCOPE,
    SCOPE_ARTIFACT,
    SCOPES,
    UFC_ONLY,
    merge_scope,
    scope_guard,
)
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


CROSSORG_ARTIFACT = SCOPE_ARTIFACT["fightmatrix"]


def _career_columns(table: pd.DataFrame) -> pd.DataFrame:
    """Give the public career table its stable snapshot column names."""
    return table.rename(
        columns={
            c: ("symon_career_skill_mass" if c == "score" else f"symon_career_{c}")
            for c in table.columns
            if c != "fighter"
        }
    )


def _source_fights_for_public_resume(snapshot_dir: Path, scope: str) -> pd.DataFrame:
    fights = pd.read_parquet(snapshot_dir / "canonical_fights.parquet")
    fights["org_weight"] = 1.0
    if "source" not in fights.columns:
        fights["source"] = "ufc"
    fights = merge_scope(fights, snapshot_dir, scope=scope, label="resume")
    if "is_excluded" in fights.columns:
        fights = fights[~fights["is_excluded"].fillna(False).astype(bool)].copy()
    return fights


def refresh_career_columns(
    snapshot_dir: Path,
    *,
    reference: str | float = DEFAULT_CAREER_REFERENCE,
    scope: str = DEFAULT_PUBLISHED_SCOPE,
) -> dict[str, object]:
    """Recompute only the career functional from an existing WHR history."""
    snapshot_dir = Path(snapshot_dir)
    history = pd.read_parquet(snapshot_dir / "ratings_history_whr.parquet")
    current_path = snapshot_dir / "ratings_current.parquet"
    current = pd.read_parquet(current_path)
    current = current.drop(
        columns=[
            c for c in current.columns
            if c.startswith("symon_career_") or c.startswith("public_legacy_")
        ],
        errors="ignore",
    )
    current = current.merge(
        _career_columns(career_skill_mass(history, reference=reference)),
        on="fighter",
        how="left",
    )
    appearances_path = snapshot_dir / "performance_appearances.parquet"
    appearances = pd.read_parquet(appearances_path) if appearances_path.exists() else pd.DataFrame()
    current = current.merge(
        public_legacy_score_rows(
            current,
            appearances,
            source_fights=_source_fights_for_public_resume(snapshot_dir, scope),
        ),
        on="fighter",
        how="left",
    )
    current = current.sort_values(
        ["mu_canonical", "fighter"], ascending=[False, True]
    ).reset_index(drop=True)
    current.to_parquet(current_path, index=False)

    metadata_path = snapshot_dir / "rating_run.json"
    metadata: dict[str, object] = {}
    if metadata_path.exists():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata.update(
        {
            "scope": scope,
            "career_reference": str(reference),
            "age_drift": True,
            "rated_bouts": int(len(history) // 2),
            "birth_dates": int(len(load_birth_dates(snapshot_dir))),
            "history_rows": int(len(history)),
            "current_fighters": int(len(current)),
            "events_processed": int(history["event_date"].nunique()),
        }
    )
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return metadata


def merge_crossorg_fights(
    fights: pd.DataFrame,
    snapshot_dir: Path,
    *,
    enabled: bool,
    label: str = "rate",
) -> pd.DataFrame:
    """Back-compatible entry point for the FightMatrix cross-org scope.

    Kept because ``--experimental-crossorg`` is a documented flag, but it is one
    scope among several now: see :mod:`ratings.scope`, which is where the scope
    registry, the missing-artifact error and the dedupe guard live.
    """
    return merge_scope(
        fights, snapshot_dir,
        scope="fightmatrix" if enabled else UFC_ONLY,
        label=label,
    )


def attach_bout_weights(
    fights: pd.DataFrame,
    *,
    rules_era_weight: float = RULES_ERA_WEIGHT,
) -> pd.DataFrame:
    """Set the one shared likelihood weight each bout contributes.

    Two factors, and both are the same number on both sides -- WHR needs a
    single bout likelihood, so a side-specific weight is not admissible here.

    ``org_weight``
        1.0 in production. The column is read rather than hard-coded so the
        research sweep can vary it without a second code path; see the
        org-weight note in :func:`run` for why production never does.
    ``rules_era``
        how far a UFC bout fought before the unified rules is allowed to move a
        rating. Defaults to 1.0 -- full admission -- and is a measured quantity,
        not an asserted one. See :mod:`ratings.rules_era`.
    """
    out = fights.copy()
    ow = pd.to_numeric(out.get("org_weight", 1.0), errors="coerce")
    ow = ow.fillna(1.0) if hasattr(ow, "fillna") else pd.Series(1.0, index=out.index)
    weight = ow * rules_era_factor(out, weight=rules_era_weight)
    out["weight_a"] = weight
    out["weight_b"] = weight
    return out


# The name this was called before the rules-era term joined the org weight.
_attach_org_only_weights = attach_bout_weights


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
    experimental_org_weight: bool = False,
    scope: str = DEFAULT_PUBLISHED_SCOPE,
    career_reference: str | float = DEFAULT_CAREER_REFERENCE,
) -> dict:
    snapshot_dir = Path(snapshot_dir).resolve()
    fights = pd.read_parquet(snapshot_dir / "canonical_fights.parquet")
    rounds = pd.read_parquet(snapshot_dir / "canonical_rounds.parquet")
    fights["org_weight"] = 1.0
    if "source" not in fights.columns:
        fights["source"] = "ufc"
    if include_experimental_crossorg and scope == UFC_ONLY:
        scope = "fightmatrix"
    fights = merge_scope(fights, snapshot_dir, scope=scope, label="rate")
    fights["rules_era"] = label_rules_era(fights)
    # No organisation weight. ``compute_fight_weights`` prices a non-UFC bout by
    # both participants' UFC-anchored caliber percentiles, so a 2003 PRIDE bout
    # would be weighted by what those two fighters went on to do years later --
    # future information inside historical evidence. Setting every bout to 1.0
    # dissolves that by construction rather than patching it: there is no weight
    # derived from future careers because there is no weight, and promotion
    # strength becomes an output of the joint fit, read off the fighters who
    # crossed. Measured cost of the removal: none. On held-out UFC bouts with
    # both fighters covered, the cross-org gain is -0.01896 [-0.02376, -0.01397]
    # log-loss weighted and byte-identical unweighted for the Glicko filters,
    # which never read the column at all.
    if not experimental_org_weight:
        staged = pd.to_numeric(fights["org_weight"], errors="coerce").fillna(1.0)
        if not np.allclose(staged.to_numpy(dtype=float), 1.0):
            print(f"[rate] discarding staged org_weight on "
                  f"{int((staged != 1.0).sum()):,} bouts; the joint fit is unweighted")
        fights["org_weight"] = 1.0

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
    birth_dates = load_birth_dates(snapshot_dir)
    whr_history = run_whr(
        _attach_org_only_weights(rated_fights),
        birth_dates=birth_dates,
        age_drift=True,
    )
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
        (career_skill_mass(whr_history, reference=career_reference), "symon_career"),
        (symon_prime_score(whr_history), "symon_prime"),
        (symon_peak_score(whr_history), "symon_peak"),
    )
    for table, prefix in symon_tables:
        renamed = _career_columns(table) if prefix == "symon_career" else table.rename(
            columns={
                c: (f"{prefix}_score" if c == "score" else f"{prefix}_{c}")
                for c in table.columns
                if c != "fighter"
            }
        )
        current = current.merge(renamed, on="fighter", how="left")

    current = current.merge(
        public_legacy_score_rows(current, perf_app, source_fights=rated_fights),
        on="fighter",
        how="left",
    )

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
        "headline = Public Legacy Score: exposure-adjusted Career Skill Mass "
        "plus a transparent championship resume ledger; Prime and Peak are "
        "separate diagnostics."
    )
    _print_top(
        current,
        rating_col="public_legacy_score",
        extra_cols=[
            "public_legacy_skill_mass",
            "public_legacy_skill_score",
            "public_legacy_exposure_factor",
            "public_legacy_title_score",
            "public_legacy_schedule_score",
            "public_legacy_title_wins",
            "public_legacy_title_defenses",
            "public_legacy_title_win_divisions",
            "symon_prime_score",
            "career_division",
            "rating_periods",
        ],
        title="HEADLINE - Top 25 by Public Legacy Score",
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

    summary = {
        "scope": scope,
        "career_reference": str(career_reference),
        "age_drift": True,
        "rated_bouts": int(len(rated_fights)),
        "birth_dates": int(len(birth_dates)),
        "history_rows": int(len(history)),
        "current_fighters": int(len(current)),
        "events_processed": int(history["event_date"].nunique()),
        "ped_confirmed_fights": int(integrity["ped_confirmed"].fillna(False).sum()),
        "dq_fights": int(integrity["is_dq"].fillna(False).sum()),
        "missed_weight_fights": int(integrity["missed_weight"].fillna(False).sum()),
        "odds_covered_fights": cov_rows,
    }
    (snapshot_dir / "rating_run.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot-dir", required=True, help="data/snapshots/<date>")
    parser.add_argument("--tau", type=float, default=DEFAULT_TAU)
    parser.add_argument("--min-fights", type=int, default=3, help="ranking eligibility threshold")
    parser.add_argument(
        "--reference",
        default=str(DEFAULT_CAREER_REFERENCE),
        help="Career bar: contender:N (published), count:N, mean, hybrid:L, or quantile.",
    )
    parser.add_argument(
        "--career-only",
        action="store_true",
        help="Recompute career columns from existing WHR history without refitting ratings.",
    )
    parser.add_argument(
        "--mdabbert-csv",
        type=str,
        default=None,
        help="Optional path to mdabbert ufc-master.csv for missed-weight cross-check.",
    )
    parser.add_argument(
        "--scope", default=DEFAULT_PUBLISHED_SCOPE,
        help=(
            "Which bouts the rating may see. 'majors' is the roster-complete "
            "six-promotion Sherdog corpus; 'fightmatrix' is the bounded "
            "ranked-cohort crawl; 'all' admits both. They move the board in "
            "opposite directions, so nothing merges unless it is named. "
            "Combine explicitly: --scope majors,pre_unified."
        ),
    )
    parser.add_argument(
        "--experimental-crossorg",
        action="store_true",
        help="Deprecated alias for --scope fightmatrix.",
    )
    parser.add_argument(
        "--experimental-org-weight",
        action="store_true",
        help=(
            "Also consume the staged per-bout org_weight. Research only, and it "
            "leaks: those weights are derived from fighters' eventual UFC careers."
        ),
    )
    args = parser.parse_args()
    if args.career_only:
        print(
            refresh_career_columns(
                Path(args.snapshot_dir).resolve(),
                reference=parse_reference(args.reference),
                scope=args.scope,
            )
        )
        return
    run(
        Path(args.snapshot_dir).resolve(),
        tau=args.tau,
        min_fights=args.min_fights,
        mdabbert_csv=Path(args.mdabbert_csv).resolve() if args.mdabbert_csv else None,
        include_experimental_crossorg=args.experimental_crossorg,
        experimental_org_weight=args.experimental_org_weight,
        scope=args.scope,
        career_reference=parse_reference(args.reference),
    )


if __name__ == "__main__":
    main()
