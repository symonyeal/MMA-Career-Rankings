"""Run the Glicko-2 engine over a canonical snapshot and persist results.

Five rating streams are emitted into ``ratings_current.parquet``:

* ``canonical``   — strict Glicko-2 on W/L/D scoring. Never sleeved.
* ``method``      — method-bonus winner score in [0.7, 1.0]. Never sleeved.
* ``method_integrity``             — method + integrity sleeve (PED + DQ + MW).
* ``method_performance``           — method + performance sleeve (quality + odds).
* ``method_integrity_performance`` — method + both sleeves.

The canonical and method ratings are produced by a single ``RatingEngine``
pass (canonical / method evolve side-by-side). Each method-sleeve stream is
produced by a separate ``WeightedRatingEngine`` pass over the same fight
table with per-(fight, fighter) update weights attached.

Career-peak (2-year), five-year, and ten-year period metrics are emitted for
every stream, each with a headline proven-resume-adjusted variant. Window mu
is era/division normalized before scoring (see ``ratings/peaks.py``).
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

from ratings.glicko2_engine import DEFAULT_TAU, RatingEngine, WeightedRatingEngine
from ratings.dominance import per_fight_dominance, per_fighter_dominance
from ratings.constants import (
    ACTIVITY_MU_PENALTY_CAP,
    ACTIVITY_MU_PENALTY_FULL_MONTHS,
    ACTIVITY_MU_PENALTY_START_MONTHS,
    FIVE_YEAR_PEAK_MIN_FIGHTS,
    SLEEVE_FACTOR_MAX,
    SLEEVE_FACTOR_MIN,
    SUSTAINED_PEAK_MIN_FIGHTS,
    SUSTAINED_PEAK_WINDOW_LABEL,
    FIVE_YEAR_PEAK_WINDOW_LABEL,
    WHR_STREAM,
    WHR_SLEEVE_STREAMS,
    rating_label,
    rename_rating_columns,
)
from ratings.diagnostics import (
    calibration_residual_rows,
    division_entropy_rows,
    sleeve_attribution_rows,
)
from ratings.division_resume import division_resume_rows, primary_division_rows
from ratings.integrity_adjustment import build_integrity_appearances
from ratings.peaks import five_year_peak, peak_appearance_quality, sustained_peak
from ratings.whr import run_whr
from ratings.performance_adjustment import build_performance_appearances
from ratings.performance_adjustment import normalize_division_label
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


def _run_canonical_engine(fights: pd.DataFrame, tau: float) -> RatingEngine:
    engine = RatingEngine(tau=tau)
    f = fights.sort_values(["event_date", "event_name"]).reset_index(drop=True)
    for (event_date, event_name), group in f.groupby(["event_date", "event_name"], sort=False):
        bouts = group[[
            "fighter_a", "fighter_b", "winner", "is_draw", "method_score_winner",
        ]].to_dict(orient="records")
        engine.process_event(event_date, event_name, bouts)
    return engine


def _attach_appearance_weights(
    fights: pd.DataFrame,
    weight_table: pd.DataFrame,
    weight_col: str,
) -> pd.DataFrame:
    """Pivot per-appearance weights back onto bout rows as ``weight_a/weight_b``."""
    out = fights.copy()
    w = weight_table[["fight_url", "fighter", weight_col]].copy()
    a = w.rename(columns={"fighter": "fighter_a", weight_col: "weight_a"})
    b = w.rename(columns={"fighter": "fighter_b", weight_col: "weight_b"})
    out = out.merge(a, on=["fight_url", "fighter_a"], how="left")
    out = out.merge(b, on=["fight_url", "fighter_b"], how="left")
    out["weight_a"] = out["weight_a"].fillna(1.0).astype(float)
    out["weight_b"] = out["weight_b"].fillna(1.0).astype(float)
    # Cross-org down-weight: a non-UFC bout updates ratings at a bridge-
    # calibrated percentile of a UFC bout. UFC bouts carry org_weight 1.0, so
    # this is a no-op for them. Applied on top of the sleeve weight so it
    # scales the whole per-fight update in both the weighted Glicko engine and
    # the WHR likelihood.
    if "org_weight" in out.columns:
        ow = pd.to_numeric(out["org_weight"], errors="coerce").fillna(1.0)
        out["weight_a"] = out["weight_a"] * ow
        out["weight_b"] = out["weight_b"] * ow
    return out


def _attach_org_only_weights(fights: pd.DataFrame) -> pd.DataFrame:
    """Set ``weight_a``/``weight_b`` to the per-fight ``org_weight`` only.

    Used for the base (sleeve-free) WHR headline so cross-org bouts are
    down-weighted there too; UFC bouts (org_weight 1.0) are unaffected.
    """
    out = fights.copy()
    ow = pd.to_numeric(out.get("org_weight", 1.0), errors="coerce")
    ow = ow.fillna(1.0) if hasattr(ow, "fillna") else 1.0
    out["weight_a"] = ow
    out["weight_b"] = ow
    return out


def _attach_quality_scores(fights: pd.DataFrame, perf_appearances: pd.DataFrame) -> pd.DataFrame:
    """Carry ``quality_score_winner`` to bout rows for the quality_method scorer."""
    out = fights.copy()
    qs = (
        perf_appearances.dropna(subset=["quality_score_winner"])
        .drop_duplicates("fight_url")[["fight_url", "quality_score_winner"]]
    )
    out = out.merge(qs, on="fight_url", how="left")
    return out


def _run_weighted_engine(
    fights: pd.DataFrame,
    *,
    tau: float,
    score_mode: str,
) -> WeightedRatingEngine:
    engine = WeightedRatingEngine(tau=tau, score_mode=score_mode)
    f = fights.sort_values(["event_date", "event_name"]).reset_index(drop=True)
    cols_needed = [
        "fighter_a", "fighter_b", "winner", "is_draw",
        "method_score_winner", "weight_a", "weight_b",
    ]
    if "quality_score_winner" in f.columns:
        cols_needed.append("quality_score_winner")
    for (event_date, event_name), group in f.groupby(["event_date", "event_name"], sort=False):
        bouts = group[cols_needed].to_dict(orient="records")
        engine.process_event(event_date, event_name, bouts)
    return engine


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
) -> dict:
    snapshot_dir = Path(snapshot_dir).resolve()
    fights = pd.read_parquet(snapshot_dir / "canonical_fights.parquet")
    rounds = pd.read_parquet(snapshot_dir / "canonical_rounds.parquet")
    excluded_path = snapshot_dir / "_excluded_bouts.csv"
    excluded = pd.read_csv(excluded_path) if excluded_path.exists() else pd.DataFrame()

    # UFC bouts are the elite reference: org_weight 1.0. Cross-org bouts (if a
    # crossorg_fights.parquet was staged) carry their own bridge-calibrated
    # org_weight < 1.0 and are concatenated into the canonical fight table so
    # they flow through every stream, sleeve, and period score.
    fights["org_weight"] = 1.0
    if "source" not in fights.columns:
        fights["source"] = "ufc"
    crossorg_path = snapshot_dir / "crossorg_fights.parquet"
    if crossorg_path.exists():
        crossorg = pd.read_parquet(crossorg_path)
        if not crossorg.empty:
            if "org_weight" not in crossorg.columns:
                crossorg["org_weight"] = 1.0
            fights = pd.concat([fights, crossorg], ignore_index=True, sort=False)
            print(f"[rate] merged {len(crossorg):,} cross-org bouts "
                  f"(orgs: {sorted(crossorg.get('org', pd.Series(dtype=str)).dropna().unique())})")

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
    # Merge flags onto the fight rows so sleeves can pick them up.
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
    # Sleeves: integrity, performance, integrity+performance
    integrity_app = build_integrity_appearances(rated_fights)

    odds_lines = load_odds_lines(snapshot_dir) if has_odds_artifact(snapshot_dir) else pd.DataFrame()
    fight_dom = per_fight_dominance(rounds, rated_fights)
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

    combined_app = integrity_app[["fight_url", "fighter", "integrity_weight"]].merge(
        perf_app[["fight_url", "fighter", "performance_weight"]],
        on=["fight_url", "fighter"],
        how="outer",
    )
    combined_app["integrity_weight"] = combined_app["integrity_weight"].fillna(1.0)
    combined_app["performance_weight"] = combined_app["performance_weight"].fillna(1.0)
    combined_app["combined_weight"] = (
        combined_app["integrity_weight"] * combined_app["performance_weight"]
    ).clip(lower=SLEEVE_FACTOR_MIN, upper=SLEEVE_FACTOR_MAX)

    # Attach quality_score_winner onto fights for quality_method scoring.
    rated_with_qs = _attach_quality_scores(rated_fights, perf_app)

    sleeve_specs: list[dict] = [
        {
            # 2026-05-15: read quality_score_winner so the integrity score
            # damp applied in performance_adjustment.quality_score_winner
            # flows into the Glicko-2 integrity stream (PED win ~ 0.55
            # instead of 1.0). The weight column still applies the legacy
            # update-weight damp on top, as an additional softener.
            "suffix": "method_integrity",
            "score_mode": "quality_method",
            "weight_source": integrity_app,
            "weight_col": "integrity_weight",
        },
        {
            "suffix": "method_performance",
            "score_mode": "quality_method",
            "weight_source": perf_app,
            "weight_col": "performance_weight",
        },
        {
            "suffix": "method_integrity_performance",
            "score_mode": "quality_method",
            "weight_source": combined_app,
            "weight_col": "combined_weight",
        },
    ]

    sleeve_histories: dict[str, pd.DataFrame] = {}
    for spec in sleeve_specs:
        suffix = spec["suffix"]
        weighted = _attach_appearance_weights(rated_with_qs, spec["weight_source"], spec["weight_col"])
        eng = _run_weighted_engine(weighted, tau=tau, score_mode=spec["score_mode"])
        sleeve_hist = eng.history_df()
        sleeve_histories[suffix] = sleeve_hist
        stream_current = _stream_current_columns(eng.current_table(), sleeve_hist, suffix=suffix)
        current = current.merge(stream_current, on="fighter", how="left")
        current = _attach_rank_and_delta(
            current, suffix=suffix, baseline_col="mu_method", min_fights=min_fights,
        )

    # ------------------------------------------------------------------
    # WHR sidecar - a Bayesian smoother over the whole fight history (Coulom
    # 2008). Unlike the Glicko-2 filter, it estimates every fighter's rating
    # history jointly, so ratings are comparable across eras at the rating
    # layer. Persisted as its own history + period columns.
    #
    # 2026-05-15: the bout table fed to WHR also carries quality_score_winner,
    # so PED / DQ / missed-weight wins are downgraded at the score layer in
    # WHR identically to how they are downgraded in the Glicko-2 method
    # streams. The canonical method/integrity Glicko stream remains binary;
    # the integrity penalty here is the WHR analog of the Glicko-2 method
    # stream's quality_score_winner damp.
    # Base (sleeve-free) WHR is the headline ranking — down-weight cross-org
    # bouts here too via org-only weights (UFC stays 1.0).
    whr_history = run_whr(_attach_org_only_weights(rated_with_qs))
    whr_history.to_parquet(snapshot_dir / "ratings_history_whr.parquet", index=False)
    whr_current = (
        whr_history.sort_values(["fighter", "event_date"])
        .groupby("fighter")["mu_whr"]
        .last()
        .reset_index()
    )
    current = current.merge(whr_current, on="fighter", how="left")

    # ------------------------------------------------------------------
    # WHR sleeved variants. The sleeve weight scales each fight's Bradley-Terry
    # likelihood contribution (g *= w, h_diag *= w); the Wiener-process and
    # anchor priors are left unweighted so temporal coupling and global scale
    # remain structural constraints. Same weight tables as Glicko-2 sleeves.
    _whr_sleeve_specs = [
        ("whr_integrity", integrity_app, "integrity_weight"),
        ("whr_performance", perf_app, "performance_weight"),
        ("whr_integrity_performance", combined_app, "combined_weight"),
    ]
    whr_sleeve_histories: dict[str, tuple[pd.DataFrame, str]] = {}
    for whr_suffix, weight_source, weight_col in _whr_sleeve_specs:
        # Use rated_with_qs so the WHR sleeve sees the integrity score damp at
        # the score layer as well as the sleeve update-weight at the
        # likelihood layer.
        weighted_fights = _attach_appearance_weights(rated_with_qs, weight_source, weight_col)
        mu_col_name = f"mu_{whr_suffix}"
        slv_hist = run_whr(weighted_fights, out_col=mu_col_name)
        slv_hist.to_parquet(snapshot_dir / f"ratings_history_{whr_suffix}.parquet", index=False)
        whr_sleeve_histories[whr_suffix] = (slv_hist, mu_col_name)
        slv_current = (
            slv_hist.sort_values(["fighter", "event_date"])
            .groupby("fighter")[mu_col_name]
            .last()
            .reset_index()
        )
        current = current.merge(slv_current, on="fighter", how="left")

    current = _attach_recent_division_gender(current, rated_fights)
    current = _attach_activity_adjusted_mu(current, rated_fights["event_date"].max())

    # ------------------------------------------------------------------
    # Five-year and ten-year period scores. Each call emits both the raw
    # column (``*_mu_<stream>``) and the headline proven-resume-adjusted
    # column (``*_headline_mu_<stream>``).
    peak_quality = peak_appearance_quality(rated_fights, history)
    # (peak function, prefix) pairs — five-year and ten-year period windows.
    peak_specs = (
        (five_year_peak, "five_year_peak"),
        (sustained_peak, "sustained_peak"),
    )
    # Base streams: (source history, mu column, label). WHR lives in its own
    # history frame; canonical/method share the Glicko-2 history. Sleeved WHR
    # variants use the same peak machinery with their own history frames.
    base_peak_sources = (
        (history, "mu_canonical", "canonical"),
        (history, "mu_method", "method"),
        (whr_history, "mu_whr", WHR_STREAM),
        *((hist, mu_col, suffix) for suffix, (hist, mu_col) in whr_sleeve_histories.items()),
    )
    for peak_fn, prefix in peak_specs:
        for src_hist, mu_col, base in base_peak_sources:
            current = current.merge(
                peak_fn(
                    src_hist, history, rated_fights,
                    mu_col=mu_col, out_col=f"{prefix}_mu_{base}",
                    headline_col=f"{prefix}_headline_mu_{base}",
                    appearance_quality=peak_quality,
                ),
                on="fighter", how="left",
            )
        for suffix, sleeve_hist in sleeve_histories.items():
            out_col = f"{prefix}_mu_{suffix}"
            headline_col = f"{prefix}_headline_mu_{suffix}"
            current = current.drop(columns=[out_col, headline_col], errors="ignore")
            current = current.merge(
                peak_fn(
                    sleeve_hist, history, rated_fights,
                    mu_col="mu", out_col=out_col,
                    headline_col=headline_col,
                    appearance_quality=peak_quality,
                ),
                on="fighter", how="left",
            )

    # Division-context all-time rows. These are the correct source for
    # divisional leaderboards; they use only bouts fought in that division and
    # shrink short title cameos toward the divisional pool.
    division_resume = division_resume_rows(whr_history, peak_quality)
    division_resume.to_parquet(snapshot_dir / "division_resume.parquet", index=False)
    current = current.drop(columns=["primary_division", "primary_division_share"], errors="ignore")
    current = current.merge(primary_division_rows(division_resume), on="fighter", how="left")

    # ------------------------------------------------------------------
    # Integrity counts
    counts = confirmed_counts(integrity)
    current = current.merge(counts, on="fighter", how="left")
    for col in ("ped_confirmed_fights", "dq_wins", "missed_weight_wins"):
        if col not in current.columns:
            current[col] = 0
        current[col] = current[col].fillna(0).astype(int)

    current = current.sort_values("mu_canonical", ascending=False).reset_index(drop=True)

    # ------------------------------------------------------------------
    # Persist
    history.to_parquet(snapshot_dir / "ratings_history.parquet", index=False)
    for suffix, hist in sleeve_histories.items():
        out_hist = hist.rename(columns={
            "mu": f"mu_{suffix}",
            "phi": f"phi_{suffix}",
            "sigma": f"sigma_{suffix}",
        })
        out_hist.to_parquet(snapshot_dir / f"ratings_history_{suffix}.parquet", index=False)
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
    sleeve_attribution_rows(
        history,
        sleeve_histories,
        integrity_app,
        perf_app,
    ).to_parquet(snapshot_dir / "sleeve_attribution.parquet", index=False)
    division_entropy_rows(history, rated_fights).to_parquet(
        snapshot_dir / "division_entropy.parquet",
        index=False,
    )

    # Remove legacy artifacts produced by the pre-consolidation pipeline.
    for legacy in (
        "ratings_history_ped_adjusted.parquet",
        "ratings_history_odds_adjusted.parquet",
        "odds_adjustment_distribution.parquet",
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

    # The WHR sidecar (Bayesian smoother) is the DEFAULT HEADLINE ranking — it
    # is comparable across eras at the rating layer, so it does not carry the
    # era-inflation / career-shape artifacts of the windowed Glicko-2 streams.
    # The method_integrity_performance stream is kept as a comparison print.
    print("headline = WHR (Whole-History Rating smoother); period scores are proven-resume-adjusted.")
    _print_top(
        current,
        rating_col="sustained_peak_headline_mu_whr",
        extra_cols=["five_year_peak_headline_mu_whr", "primary_division", "sustained_peak_mu_whr", "rating_periods"],
        title=f"HEADLINE — Top 25 by whr_rating ({SUSTAINED_PEAK_WINDOW_LABEL}, min {SUSTAINED_PEAK_MIN_FIGHTS})",
        n=25, min_fights=0,
    )
    _print_top(
        current,
        rating_col="five_year_peak_headline_mu_whr",
        extra_cols=["sustained_peak_headline_mu_whr", "five_year_peak_mu_whr", "rating_periods"],
        title=f"HEADLINE — Top 25 by whr_rating (5-yr) ({FIVE_YEAR_PEAK_WINDOW_LABEL}, min {FIVE_YEAR_PEAK_MIN_FIGHTS})",
        n=25, min_fights=0,
    )
    _print_top(
        current,
        rating_col="sustained_peak_headline_mu_method_integrity_performance",
        extra_cols=[
            "five_year_peak_headline_mu_method_integrity_performance",
            "sustained_peak_mu_method_integrity_performance",
            "rating_periods",
        ],
        title=f"comparison — Top 25 by method_full ({SUSTAINED_PEAK_WINDOW_LABEL}, min {SUSTAINED_PEAK_MIN_FIGHTS})",
        n=25, min_fights=SUSTAINED_PEAK_MIN_FIGHTS,
    )
    _print_top(
        current,
        rating_col="sustained_peak_headline_mu_whr_integrity_performance",
        extra_cols=[
            "five_year_peak_headline_mu_whr_integrity_performance",
            "sustained_peak_headline_mu_whr",
            "rating_periods",
        ],
        title=f"whr_full — Top 25 sustained ({SUSTAINED_PEAK_WINDOW_LABEL}, min {SUSTAINED_PEAK_MIN_FIGHTS})",
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
    args = parser.parse_args()
    run(
        Path(args.snapshot_dir).resolve(),
        tau=args.tau,
        min_fights=args.min_fights,
        mdabbert_csv=Path(args.mdabbert_csv).resolve() if args.mdabbert_csv else None,
    )


if __name__ == "__main__":
    main()
