"""Rolling-origin prequential comparison of the lean rating core.

Why this exists
---------------
The production comparison is deliberately small: a causal binary-result
Glicko-2 filter versus a binary-result Whole-History Rating smoother. Both see
the same UFC bouts and outcomes. A separately named research arm may scale a
whole bout's WHR likelihood by dominance-derived precision, but the winner and
loser always receive the same evidence weight.

The cheap part, and why it is cheap
-----------------------------------
The Glicko-2 streams are *filters*: a fighter's rating entering a bout is a
function of that fighter's earlier bouts only. So one chronological sweep over
the whole fight table already contains every one-step-ahead out-of-sample
prediction — the pre-fight rating IS the forecast, and there is nothing to
re-fit. Refitting per fold is reserved for WHR, which is a whole-history
*smoother* and genuinely uses look-ahead: for each held-out event it is re-fit
on the fights strictly before that event.

The other saving is structural. Crawl output, identity resolution, organization
mapping, bout reconciliation, and optional research inputs are invariant to
every rating parameter, so they are built once per snapshot and cached. Period,
peak, division-resume, and board artifacts are not needed for evaluation.

What is deliberately *not* applied here
---------------------------------------
The WHR era premium (``_build_era_premium_by_year``) is a display transform
computed from the whole snapshot's year means. Applying it to a prequential
prediction would let a global statistic touch a held-out forecast, so it is
skipped. It shifts a whole year uniformly and cancels in most matchups, but
"mostly cancels" is not "cannot leak".

Position note
-------------
``fighter_a`` wins 63% of bouts in the canonical table — UFCStats lists the
winner first. Log-loss and Brier are invariant to which side is called "a", so
they are unaffected, but a naive "always pick fighter_a" rule would score 63%
accuracy on row order alone. The naive benchmark here is therefore p = 0.5.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from ratings.constants import SLEEVE_FACTOR_MAX, SLEEVE_FACTOR_MIN, WHR_DOMINANCE_WEIGHT_AMPLITUDE
from ratings.dominance import per_fight_dominance
from ratings.glicko2_engine import DEFAULT_TAU, predict_win_prob_from_ratings
from ratings.integrity_adjustment import build_integrity_appearances
from ratings.performance_adjustment import build_performance_appearances, normalize_division_label
from ratings.rules_era import label_rules_era
from ratings.whr import _ELO_PER_NAT, project_age_rating, run_whr
from ratings.age import load_birth_dates
from ratings import rate_snapshot as RS
from ratings import research_variants as RV
from loaders.integrity_flags import INTEGRITY_COLUMNS, build_integrity_flags
from loaders.combined_fights import build_combined_fights
from loaders.odds_loader import has_odds_artifact, load_odds_lines
from loaders.ufcstats_loader import METHOD_SCORES

DEFAULT_MIN_PRIOR_FIGHTS = 3
EPS = 1e-6

# Bump whenever a change alters what a variant computes, so cached folds from an
# earlier engine are not silently reused. Cache keys are otherwise
# (snapshot, variant, folds, parameters), none of which notice a code change.
#   1 - initial harness
#   2 - market-weighting removal (2026-08-18): performance/combined weights moved
#       on 35 appearance rows, so every variant reading them changed
#   3 - principled core (2026-08-20): reciprocal Glicko forecasts, binary WHR,
#       shared bout-level WHR weights, and UFC-only default scope
#   4 - fixed-mass WHR prior (2026-08-20): virtual games plus per-fighter (not
#       per-appearance) anchor mass, so every WHR rating moved
CACHE_SCHEMA_VERSION = 6


# ---------------------------------------------------------------------------
# Variants


@dataclass(frozen=True)
class Variant:
    """One rating configuration to score.

    ``engine`` picks the updater. ``weight`` is retained only for explicit
    weighted-Glicko research; WHR rejects side-specific appearance sleeves.
    Outcome softening and dominance weighting are opt-in so a base WHR variant
    cannot silently stop being a binary Bradley--Terry model.
    """

    name: str
    engine: str  # "glicko" | "weighted_glicko" | "whr"
    stream: str = "canonical"  # for engine="glicko": "canonical" or "method"
    score_mode: str = "canonical"  # weighted engine scorer
    weight: str | None = None  # None | "integrity" | "performance" | "combined"
    # Opt-IN, because the staged cross-org weights are not outcome-independent:
    # ``compute_fight_weights`` prices a 2003 PRIDE bout by both participants'
    # UFC-anchored caliber percentiles, i.e. by what they went on to do years
    # later. Defaulting this on let a research arm quietly consume future
    # information. Promotion strength is an output of a joint fit, never an
    # input to it, so anything that wants the bridge has to ask for it.
    use_org_weight: bool = False  # cross-organization participant-caliber bridge
    use_dominance: bool = False  # shared bout-level WHR likelihood precision
    use_quality_score: bool = False  # explicit fractional winner score research
    use_age_drift: bool = False  # estimated age-dependent Wiener prior mean
    # A forecast has no appearance node at its cutoff. Project the last fitted
    # WHR mean through that inactive gap under the learned age curve.
    project_age_inactivity: bool = False
    virtual_games: float | None = None  # WHR prior mass; None = engine default

    def key(self) -> str:
        return self.name


def default_variants() -> list[Variant]:
    """The two coherent core estimators plus one labelled research arm."""
    return [
        Variant("canonical", engine="glicko", stream="canonical"),
        Variant(
            "whr",
            engine="whr",
            use_age_drift=True,
            project_age_inactivity=True,
        ),
        Variant(
            "whr_symmetric_dominance_research",
            engine="whr",
            use_dominance=True,
            use_age_drift=True,
            project_age_inactivity=True,
        ),
    ]


# ---------------------------------------------------------------------------
# Invariant inputs — built once per snapshot, cached


@dataclass
class Inputs:
    """Everything downstream of the crawl that no rating parameter changes."""

    snapshot_dir: Path
    fights: pd.DataFrame  # rated bouts, chronological, integrity merged
    history: pd.DataFrame  # canonical Glicko-2 history (drives the weight tables)
    weights: dict[str, pd.DataFrame] = field(default_factory=dict)
    dominance_level: dict = field(default_factory=dict)
    odds: pd.DataFrame = field(default_factory=pd.DataFrame)
    quality_score: pd.DataFrame = field(default_factory=pd.DataFrame)
    birth_dates: dict[str, pd.Timestamp] = field(default_factory=dict)


def load_fight_table(
    snapshot_dir: Path,
    *,
    with_crossorg: bool = False,
    scope: str | None = None,
) -> pd.DataFrame:
    """Load rated bouts for one named scope, defaulting to UFC-only.

    ``scope`` is the current interface (see :mod:`ratings.scope`);
    ``with_crossorg=True`` is the older boolean and means ``scope="fightmatrix"``.
    Either way an unsatisfiable request raises rather than quietly returning the
    UFC-only table, because a joint fit that silently is not one gets believed.
    """
    if scope is None:
        scope = "fightmatrix" if with_crossorg else RS.UFC_ONLY
    snapshot_dir = Path(snapshot_dir)
    fights, _ = build_combined_fights(snapshot_dir, scope=scope, label="prequential")
    fights["rules_era"] = label_rules_era(fights)

    fights["event_date"] = pd.to_datetime(fights["event_date"])
    if "method_class" in fights.columns:
        recalculated = fights["method_class"].map(METHOD_SCORES)
        fights["method_score_winner"] = recalculated.combine_first(
            pd.to_numeric(fights.get("method_score_winner"), errors="coerce")
        )
    fights = fights.sort_values(["event_date", "event_name"]).reset_index(drop=True)

    integrity = build_integrity_flags(fights, mdabbert_csv=None)
    fights = fights.drop(
        columns=[c for c in INTEGRITY_COLUMNS if c != "fight_url" and c in fights.columns],
        errors="ignore",
    )
    fights = fights.merge(integrity, on="fight_url", how="left")
    fights = RS._ensure_integrity_columns(fights)
    if "is_excluded" in fights.columns:
        fights = fights[~fights["is_excluded"]].copy()
    return fights.reset_index(drop=True)


def build_inputs(
    snapshot_dir: Path, *, with_crossorg: bool = False, scope: str | None = None
) -> Inputs:
    """Load the fight table and every rating-parameter-invariant weight table.

    Odds are retained only as an external benchmark and reporting segment. They
    do not alter any rating variant in this harness.
    """
    snapshot_dir = Path(snapshot_dir)
    fights = load_fight_table(snapshot_dir, with_crossorg=with_crossorg, scope=scope)
    base_engine = RS._run_canonical_engine(fights, tau=DEFAULT_TAU)
    history = base_engine.history_df()

    rounds_path = snapshot_dir / "canonical_rounds.parquet"
    rounds = pd.read_parquet(rounds_path) if rounds_path.exists() else pd.DataFrame()
    scorecards_path = snapshot_dir / "datalab_scorecards.parquet"
    scorecards = pd.read_parquet(scorecards_path) if scorecards_path.exists() else None
    fight_dom = per_fight_dominance(rounds, fights, scorecards=scorecards)
    odds = load_odds_lines(snapshot_dir) if has_odds_artifact(snapshot_dir) else pd.DataFrame()

    integrity_app = build_integrity_appearances(fights)
    perf_app = build_performance_appearances(
        fights, history, None, fight_dominance=fight_dom
    )

    def _combined(perf: pd.DataFrame) -> pd.DataFrame:
        out = integrity_app[["fight_url", "fighter", "integrity_weight"]].merge(
            perf[["fight_url", "fighter", "performance_weight"]],
            on=["fight_url", "fighter"], how="outer",
        )
        out["integrity_weight"] = out["integrity_weight"].fillna(1.0)
        out["performance_weight"] = out["performance_weight"].fillna(1.0)
        out["combined_weight"] = (
            out["integrity_weight"] * out["performance_weight"]
        ).clip(lower=SLEEVE_FACTOR_MIN, upper=SLEEVE_FACTOR_MAX)
        return out

    weights = {
        "integrity": integrity_app,
        "performance": perf_app,
        "combined": _combined(perf_app),
    }
    quality_score = (
        perf_app.dropna(subset=["quality_score_winner"])
        .drop_duplicates("fight_url")[["fight_url", "quality_score_winner"]]
    )
    return Inputs(
        snapshot_dir=snapshot_dir,
        fights=fights,
        history=history,
        weights=weights,
        dominance_level=RV.winner_dominance_level(perf_app),
        odds=odds,
        quality_score=quality_score,
        birth_dates=load_birth_dates(snapshot_dir),
    )


WEIGHT_COLUMN = {
    "integrity": "integrity_weight",
    "performance": "performance_weight",
    "combined": "combined_weight",
}


def _weighted_fights(inputs: Inputs, variant: Variant) -> pd.DataFrame:
    """Attach ``weight_a``/``weight_b`` and the score column for one variant."""
    if variant.engine == "whr" and variant.weight is not None:
        raise ValueError(
            "WHR variants require one shared bout weight; "
            "side-specific appearance sleeves are retired"
        )
    fights = inputs.fights
    if variant.use_quality_score:
        fights = fights.merge(inputs.quality_score, on="fight_url", how="left")
    if not variant.use_org_weight:
        fights = fights.copy()
        fights["org_weight"] = 1.0

    if variant.weight is None:
        out = RS._attach_org_only_weights(fights)
    else:
        table = variant.weight
        out = RV.attach_appearance_weights(
            fights, inputs.weights[table], WEIGHT_COLUMN[table]
        )
    if variant.engine == "whr" and variant.use_dominance:
        out = RV.amplify_dominance_weight(
            out, inputs.dominance_level, WHR_DOMINANCE_WEIGHT_AMPLITUDE
        )
    if variant.engine == "whr" and not np.allclose(
        out["weight_a"].to_numpy(dtype=float),
        out["weight_b"].to_numpy(dtype=float),
        rtol=0.0,
        atol=1e-12,
    ):
        raise ValueError("WHR requires equal winner and loser likelihood weights")
    return out


# ---------------------------------------------------------------------------
# Prediction: one sweep for filters, refit-per-fold for the smoother


def _decided(fights: pd.DataFrame) -> pd.DataFrame:
    """Bouts with a clean winner — the only ones a win probability can be scored on."""
    f = fights
    for flag in ("is_draw", "is_nc"):
        if flag in f.columns:
            f = f[~f[flag].fillna(False).astype(bool)]
    f = f.dropna(subset=["winner", "fighter_a", "fighter_b"])
    return f[f["winner"].eq(f["fighter_a"]) | f["winner"].eq(f["fighter_b"])]


def _prefight_table(history: pd.DataFrame, mu_col: str, phi_col: str | None) -> pd.DataFrame:
    """Each history row's rating *entering* that appearance, plus prior fight count."""
    cols = ["fighter", "event_date", "event_name", mu_col]
    if phi_col and phi_col in history.columns:
        cols.append(phi_col)
    h = history[cols].copy()
    h["event_date"] = pd.to_datetime(h["event_date"], errors="coerce")
    h = h.sort_values(["fighter", "event_date", "event_name"], kind="stable")
    h["pre_mu"] = h.groupby("fighter")[mu_col].shift(1).fillna(1500.0)
    if phi_col and phi_col in h.columns:
        h["pre_phi"] = h.groupby("fighter")[phi_col].shift(1).fillna(350.0)
    else:
        h["pre_phi"] = 350.0
    h["prior_fights"] = h.groupby("fighter").cumcount()
    return h[["fighter", "event_date", "event_name", "pre_mu", "pre_phi", "prior_fights"]]


def online_predictions(inputs: Inputs, variant: Variant) -> pd.DataFrame:
    """One-step-ahead predictions for a filter variant, from a single sweep.

    Returns one row per decided bout with ``p_a`` (probability fighter_a wins),
    the pre-fight ratings that produced it, and each side's prior fight count.
    """
    if variant.engine == "glicko":
        engine = RS._run_canonical_engine(inputs.fights, tau=DEFAULT_TAU)
        history = engine.history_df()
        mu_col, phi_col = f"mu_{variant.stream}", f"phi_{variant.stream}"
    elif variant.engine == "weighted_glicko":
        engine = RV.run_weighted_engine(
            _weighted_fights(inputs, variant), tau=DEFAULT_TAU, score_mode=variant.score_mode
        )
        history = engine.history_df()
        mu_col, phi_col = "mu", "phi"
    else:
        raise ValueError(f"{variant.engine} is not an online updater")

    pre = _prefight_table(history, mu_col, phi_col)
    bouts = _decided(inputs.fights)[
        ["fight_url", "event_date", "event_name", "fighter_a", "fighter_b", "winner"]
    ].copy()
    for side in ("a", "b"):
        bouts = bouts.merge(
            pre.rename(columns={
                "fighter": f"fighter_{side}", "pre_mu": f"mu_{side}",
                "pre_phi": f"phi_{side}", "prior_fights": f"prior_{side}",
            }),
            on=[f"fighter_{side}", "event_date", "event_name"], how="left",
        )
    for col, default in (("mu_a", 1500.0), ("mu_b", 1500.0), ("phi_a", 350.0), ("phi_b", 350.0),
                         ("prior_a", 0.0), ("prior_b", 0.0)):
        bouts[col] = pd.to_numeric(bouts[col], errors="coerce").fillna(default)
    bouts["p_a"] = [
        predict_win_prob_from_ratings(ma, pa, mb, pb)
        for ma, pa, mb, pb in zip(bouts["mu_a"], bouts["phi_a"], bouts["mu_b"], bouts["phi_b"])
    ]
    bouts["y_a"] = (bouts["winner"] == bouts["fighter_a"]).astype(int)
    bouts["variant"] = variant.name
    return bouts[["variant", "fight_url", "event_date", "event_name", "fighter_a", "fighter_b",
                  "p_a", "y_a", "prior_a", "prior_b"]]


def whr_predictions(
    inputs: Inputs,
    variant: Variant,
    eval_events: pd.DataFrame,
    *,
    iterations: int | None = None,
    w2_per_day: float | None = None,
    progress: bool = False,
) -> pd.DataFrame:
    """Refit-per-fold predictions for the whole-history smoother.

    WHR uses look-ahead by construction, so for each held-out event it is re-fit
    on the fights strictly before that event and each fighter's last pre-event
    rating makes the forecast. This is the only variant class that pays a refit.
    """
    weighted = _weighted_fights(inputs, variant)
    decided_all = _decided(inputs.fights)
    kwargs = {}
    if iterations is not None:
        kwargs["iterations"] = iterations
    if w2_per_day is not None:
        kwargs["w2_per_day"] = w2_per_day
    if variant.use_quality_score:
        kwargs["winner_score_col"] = "quality_score_winner"
    if variant.virtual_games is not None:
        kwargs["virtual_games"] = float(variant.virtual_games)
    if variant.use_age_drift:
        kwargs["age_drift"] = True
        kwargs["birth_dates"] = inputs.birth_dates

    appearances = pd.concat([
        decided_all[["event_date", "fighter_a"]].rename(columns={"fighter_a": "fighter"}),
        decided_all[["event_date", "fighter_b"]].rename(columns={"fighter_b": "fighter"}),
    ], ignore_index=True)

    rows = []
    for n, (_, ev) in enumerate(eval_events.iterrows(), start=1):
        cutoff = ev["event_date"]
        train = weighted[weighted["event_date"] < cutoff]
        if train.empty:
            continue
        hist = run_whr(train, **kwargs)
        if hist.empty:
            continue
        last_rows = (
            hist.sort_values(["fighter", "event_date"])
            .groupby("fighter", sort=False)
            .tail(1)
            .set_index("fighter")
        )
        last = last_rows["mu_whr"]
        if variant.project_age_inactivity:
            if not variant.use_age_drift:
                raise ValueError("age-inactivity projection requires use_age_drift=True")
            profile = hist.attrs.get("age_drift_elo_per_year")
            if profile is None:
                raise ValueError("age-aware WHR history is missing its learned drift profile")
            last = pd.Series(
                {
                    fighter: project_age_rating(
                        float(row["mu_whr"]),
                        last_date=row["event_date"],
                        target_date=cutoff,
                        birth_date=inputs.birth_dates.get(str(fighter)),
                        drift_elo_per_year=profile,
                    )
                    for fighter, row in last_rows.iterrows()
                }
            )
        prior_counts = appearances[appearances["event_date"] < cutoff].groupby("fighter").size()
        ev_bouts = decided_all[
            (decided_all["event_date"] == cutoff) & (decided_all["event_name"] == ev["event_name"])
        ]
        for _, b in ev_bouts.iterrows():
            a, c = b["fighter_a"], b["fighter_b"]
            mu_a = float(last.get(a, 1500.0))
            mu_b = float(last.get(c, 1500.0))
            last_date_a = (
                pd.to_datetime(last_rows.loc[a, "event_date"], errors="coerce")
                if a in last_rows.index else pd.NaT
            )
            last_date_b = (
                pd.to_datetime(last_rows.loc[c, "event_date"], errors="coerce")
                if c in last_rows.index else pd.NaT
            )
            inactive_days_a = (
                float((cutoff - last_date_a).days) if pd.notna(last_date_a) else np.nan
            )
            inactive_days_b = (
                float((cutoff - last_date_b).days) if pd.notna(last_date_b) else np.nan
            )
            gap = (mu_a - mu_b) / _ELO_PER_NAT
            dob_a = pd.to_datetime(inputs.birth_dates.get(str(a)), errors="coerce")
            dob_b = pd.to_datetime(inputs.birth_dates.get(str(c)), errors="coerce")
            age_a = ((cutoff - dob_a).days / 365.2425) if pd.notna(dob_a) else np.nan
            age_b = ((cutoff - dob_b).days / 365.2425) if pd.notna(dob_b) else np.nan
            rows.append({
                "variant": variant.name,
                "fight_url": b["fight_url"],
                "event_date": cutoff,
                "event_name": ev["event_name"],
                "fighter_a": a,
                "fighter_b": c,
                "p_a": 1.0 / (1.0 + np.exp(-gap)),
                "y_a": int(b["winner"] == a),
                "prior_a": float(prior_counts.get(a, 0)),
                "prior_b": float(prior_counts.get(c, 0)),
                "inactive_days_a": inactive_days_a,
                "inactive_days_b": inactive_days_b,
                "age_a": age_a,
                "age_b": age_b,
                "involves_over_35": bool(
                    (np.isfinite(age_a) and age_a >= 35.0)
                    or (np.isfinite(age_b) and age_b >= 35.0)
                ),
            })
        if progress and n % 5 == 0:
            print(f"    [{variant.name}] fold {n}/{len(eval_events)}", flush=True)
    return pd.DataFrame(rows, columns=[
        "variant", "fight_url", "event_date", "event_name", "fighter_a", "fighter_b",
        "p_a", "y_a", "prior_a", "prior_b", "age_a", "age_b",
        "inactive_days_a", "inactive_days_b", "involves_over_35"])


# ---------------------------------------------------------------------------
# Evaluation events (folds)


def split_calibration_events(
    fights: pd.DataFrame,
    eval_events: pd.DataFrame,
    *,
    n_events: int = 25,
    min_bouts: int = 4,
) -> pd.DataFrame:
    """Events used only to fit the probability scale, all strictly before evaluation.

    Temperature has to be fitted somewhere, and fitting it on the held-out fold
    would be exactly the look-ahead this harness exists to avoid. These are the
    ``n_events`` cards immediately preceding the earliest evaluation card.
    """
    if eval_events.empty:
        return eval_events
    cutoff = eval_events["event_date"].min()
    decided = _decided(fights)
    events = (
        decided[decided["event_date"] < cutoff]
        .groupby(["event_date", "event_name"], sort=True)
        .size().rename("n_bouts").reset_index()
    )
    events = events[events["n_bouts"] >= min_bouts]
    return events.tail(n_events).reset_index(drop=True)


def choose_eval_events(
    fights: pd.DataFrame,
    *,
    n_events: int = 25,
    mode: str = "recent",
    seed: int = 20260818,
    min_bouts: int = 4,
    since_year: int | None = None,
) -> pd.DataFrame:
    """Pick the held-out events.

    ``all`` takes every card from ``since_year`` on. This is the mode to prefer
    for the filter streams: one sweep already contains their predictions, so a
    wider window costs nothing and is the only way to get enough bouts per
    segment to conclude anything. ``recent`` takes the last ``n_events`` cards —
    the operationally relevant window and what ``whr_backtest`` used, and the
    right size when a variant has to be re-fit per fold. ``stratified`` spreads
    ``n_events`` evenly across the calendar span, for claims about the whole
    history rather than the modern era.
    """
    decided = _decided(fights)
    events = (
        decided.groupby(["event_date", "event_name"], sort=True)
        .size().rename("n_bouts").reset_index()
    )
    events = events[events["n_bouts"] >= min_bouts]
    if since_year is not None:
        events = events[events["event_date"].dt.year >= since_year]
    if events.empty:
        return events
    if mode == "all":
        return events.reset_index(drop=True)
    if mode == "recent":
        return events.tail(n_events).reset_index(drop=True)
    if mode == "stratified":
        # One event per equal-width slice of the calendar span, so eras are
        # represented in proportion to time rather than to card volume.
        rng = np.random.default_rng(seed)
        years = events["event_date"].dt.year.to_numpy()
        edges = np.linspace(years.min(), years.max() + 1, n_events + 1)
        picks = []
        for lo, hi in zip(edges[:-1], edges[1:]):
            block = np.flatnonzero((years >= lo) & (years < hi))
            if block.size:
                picks.append(int(rng.choice(block)))
        return events.iloc[sorted(set(picks))].reset_index(drop=True)
    raise ValueError(f"unknown mode {mode!r}")


# ---------------------------------------------------------------------------
# Scoring


def roc_auc(p: np.ndarray, y: np.ndarray) -> float:
    """Rank-based discrimination, invariant to any monotone rescaling of ``p``.

    This is the metric that answers "does this mechanism add *information*",
    separately from whether the probability scale is right — temperature
    scaling cannot move it, so a mechanism that only fixes calibration shows up
    in log-loss and not here.
    """
    y = np.asarray(y, dtype=float)
    pos, neg = y == 1, y == 0
    if not pos.any() or not neg.any():
        return float("nan")
    order = np.argsort(p, kind="stable")
    ranks = np.empty(len(p), dtype=float)
    ranks[order] = np.arange(1, len(p) + 1, dtype=float)
    # Mid-ranks for ties, so a constant predictor scores exactly 0.5.
    sp = p[order]
    i = 0
    while i < len(sp):
        j = i
        while j + 1 < len(sp) and sp[j + 1] == sp[i]:
            j += 1
        if j > i:
            ranks[order[i:j + 1]] = (i + 1 + j + 1) / 2.0
        i = j + 1
    n_pos, n_neg = int(pos.sum()), int(neg.sum())
    return float((ranks[pos].sum() - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg))


def _metrics(p: np.ndarray, y: np.ndarray) -> dict:
    p = np.clip(p, EPS, 1 - EPS)
    return {
        "log_loss": float(np.mean(-(y * np.log(p) + (1 - y) * np.log(1 - p)))),
        "brier": float(np.mean((p - y) ** 2)),
        "accuracy": float(np.mean((p >= 0.5) == (y == 1))),
        "auc": roc_auc(p, y),
        "n": int(len(p)),
    }


def fit_temperature(p: np.ndarray, y: np.ndarray) -> float:
    """Scalar temperature ``T`` minimising log-loss for ``sigmoid(logit(p) / T)``.

    Every variant here shares a badly overconfident probability scale — the
    engine's stored ``calibration_residuals`` shows the same thing — so raw
    log-loss mostly measures that shared defect rather than the mechanism under
    test. Fitting one parameter on data that strictly precedes the held-out
    events removes it without leaking anything.
    """
    p = np.clip(np.asarray(p, dtype=float), EPS, 1 - EPS)
    y = np.asarray(y, dtype=float)
    logit = np.log(p / (1 - p))
    if len(logit) < 50 or not np.isfinite(logit).all():
        return 1.0

    def loss(t: float) -> float:
        q = np.clip(1.0 / (1.0 + np.exp(-logit / t)), EPS, 1 - EPS)
        return float(np.mean(-(y * np.log(q) + (1 - y) * np.log(1 - q))))

    # Unimodal in T over this range; a golden-section search is enough and
    # avoids a scipy dependency.
    lo, hi = 0.25, 12.0
    phi = (np.sqrt(5.0) - 1.0) / 2.0
    a, b = lo, hi
    c, d = b - phi * (b - a), a + phi * (b - a)
    for _ in range(60):
        if loss(c) < loss(d):
            b, d = d, c
            c = b - phi * (b - a)
        else:
            a, c = c, d
            d = a + phi * (b - a)
    return float((a + b) / 2.0)


def apply_temperature(p: np.ndarray, temperature: float) -> np.ndarray:
    p = np.clip(np.asarray(p, dtype=float), EPS, 1 - EPS)
    logit = np.log(p / (1 - p))
    return 1.0 / (1.0 + np.exp(-logit / float(temperature)))


def calibration_curve(p: np.ndarray, y: np.ndarray, *, n_bins: int = 10) -> pd.DataFrame:
    """Reliability table in ``calibration_residuals.parquet`` conventions."""
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    idx = np.clip(np.digitize(p, bins[1:-1], right=False), 0, n_bins - 1)
    rows = []
    for b in range(n_bins):
        m = idx == b
        if not m.any():
            continue
        rows.append({
            "prob_bin": b,
            "predicted_mean": float(p[m].mean()),
            "empirical_win_rate": float(y[m].mean()),
            "residual": float(y[m].mean() - p[m].mean()),
            "brier": float(((p[m] - y[m]) ** 2).mean()),
            "n": int(m.sum()),
        })
    return pd.DataFrame(rows)


def calibration_error(p: np.ndarray, y: np.ndarray, *, n_bins: int = 10) -> float:
    """Sample-weighted mean |empirical - predicted| over the reliability bins (ECE)."""
    curve = calibration_curve(p, y, n_bins=n_bins)
    if curve.empty:
        return float("nan")
    w = curve["n"].to_numpy(dtype=float)
    return float(np.sum(w * curve["residual"].abs().to_numpy()) / w.sum())


def symmetrize_sides(predictions: pd.DataFrame, *, seed: int = 20260818) -> pd.DataFrame:
    """Deterministically relabel a pseudo-random half of the bouts a<->b.

    Every FightMatrix cross-organization row is stored winner-first — all 9,692
    decided bouts in the depth-one complete-edge scope have ``fighter_a`` as the
    winner — so ``y_a`` is constant on that subset and AUC is undefined there.
    Log-loss, Brier and accuracy are exactly invariant to which side is called
    "a" (verified, not assumed), so this changes none of them; it only restores
    a two-class label so the rank metric can be computed.

    The flip is keyed on ``fight_url``, so every variant and benchmark flips the
    same bouts and paired comparisons stay paired.
    """
    if predictions.empty or "fight_url" not in predictions.columns:
        return predictions
    out = predictions.copy()
    salt = str(seed).encode()
    flip = np.array([
        hashlib.sha256(salt + str(u).encode()).digest()[0] & 1 == 1
        for u in out["fight_url"]
    ], dtype=bool)
    for col in ("p_a", "p_a_calibrated"):
        if col in out.columns:
            out[col] = np.where(flip, 1.0 - out[col].to_numpy(dtype=float), out[col])
    out["y_a"] = np.where(flip, 1 - out["y_a"].to_numpy(dtype=int), out["y_a"])
    for left, right in (("fighter_a", "fighter_b"), ("prior_a", "prior_b")):
        if left in out.columns and right in out.columns:
            a, b = out[left].to_numpy().copy(), out[right].to_numpy().copy()
            out[left] = np.where(flip, b, a)
            out[right] = np.where(flip, a, b)
    out["side_flipped"] = flip
    return out


def attach_segments(
    predictions: pd.DataFrame,
    fights: pd.DataFrame,
    *,
    odds: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Add the segment columns every conclusion has to be sliced by."""
    cols = ["fight_url", "weight_class", "method_class", "source", "org", "event_date"]
    meta = fights[[c for c in cols if c in fights.columns]].drop_duplicates("fight_url")
    out = predictions.merge(meta, on="fight_url", how="left", suffixes=("", "_meta"))

    out["division"] = out.get("weight_class", pd.Series(index=out.index)).map(normalize_division_label)
    out["division"] = out["division"].fillna("Unknown")
    year = pd.to_datetime(out["event_date"]).dt.year
    out["era"] = pd.cut(
        year, bins=[0, 2005, 2010, 2015, 2020, 2100],
        labels=["<=2005", "2006-2010", "2011-2015", "2016-2020", "2021+"],
    ).astype(str)
    method = out.get("method_class", pd.Series(index=out.index)).astype(str)
    out["outcome_type"] = np.where(method.isin(["KO/TKO", "Submission"]), "finish", "decision")
    source = out.get("source", pd.Series("ufc", index=out.index)).fillna("ufc").astype(str)
    out["scope"] = np.where(source.eq("ufc"), "ufc_only", "cross_org")

    # Participant-completeness band: the weaker of the two endpoints, which is
    # what the completeness policies actually gate on.
    for side in ("a", "b"):
        col = f"fighter_{side}_completeness"
        if col in fights.columns:
            comp = fights[["fight_url", col]].drop_duplicates("fight_url")
            out = out.merge(comp, on="fight_url", how="left")
    comp_cols = [c for c in ("fighter_a_completeness", "fighter_b_completeness") if c in out.columns]
    if comp_cols:
        weakest = out[comp_cols].apply(pd.to_numeric, errors="coerce").min(axis=1)
        out["completeness_band"] = pd.cut(
            weakest, bins=[-0.01, 0.001, 0.5, 0.8, 1.01],
            labels=["zero", "low", "mid", "complete"],
        ).astype(str)
    else:
        out["completeness_band"] = "n/a"

    if odds is not None and not odds.empty and "implied_prob_a_no_vig" in odds.columns:
        ok = odds[odds.get("odds_data_quality", "ok").eq("ok")] if "odds_data_quality" in odds.columns else odds
        out = out.merge(
            ok[["fight_url", "implied_prob_a_no_vig"]].drop_duplicates("fight_url"),
            on="fight_url", how="left",
        )
        market = pd.to_numeric(out["implied_prob_a_no_vig"], errors="coerce")
        favoured_a = market >= 0.5
        out["role"] = np.where(
            market.isna(), "no_line",
            np.where(favoured_a == (out["y_a"] == 1), "favourite_won", "underdog_won"),
        )
    else:
        out["implied_prob_a_no_vig"] = np.nan
        out["role"] = "no_line"
    return out


SEGMENTS = ["division", "era", "outcome_type", "role", "scope", "completeness_band"]


def score_predictions(
    predictions: pd.DataFrame,
    *,
    min_n: int = 200,
    segments: list[str] | None = None,
    calibrated: bool = False,
) -> pd.DataFrame:
    """Per-variant metrics overall and by segment, with an n-sufficiency flag.

    ``n_sufficient`` is False below ``min_n``; conclusions must not be drawn
    from those rows. The threshold is stated rather than implied.
    """
    segments = segments if segments is not None else SEGMENTS
    prob_col = "p_a_calibrated" if (calibrated and "p_a_calibrated" in predictions.columns) else "p_a"
    rows = []
    for variant, g in predictions.groupby("variant", sort=True):
        def _row(frame: pd.DataFrame, segment_type: str, segment_value: str) -> dict:
            p = frame[prob_col].to_numpy(dtype=float)
            y = frame["y_a"].to_numpy(dtype=float)
            return {"variant": variant, "segment_type": segment_type,
                    "segment_value": segment_value, **_metrics(p, y),
                    "calibration_error": calibration_error(p, y)}

        rows.append(_row(g, "overall", "all"))
        for seg in segments:
            if seg not in g.columns:
                continue
            for value, gg in g.groupby(seg, sort=True, dropna=False):
                if len(gg):
                    rows.append(_row(gg, seg, str(value)))
    out = pd.DataFrame(rows)
    out["prob_column"] = prob_col
    out["n_sufficient"] = out["n"] >= min_n
    return out.sort_values(["segment_type", "segment_value", "log_loss"]).reset_index(drop=True)


def paired_delta(
    predictions: pd.DataFrame,
    baseline: str,
    challenger: str,
    *,
    metric: str = "log_loss",
    n_boot: int = 2000,
    seed: int = 20260818,
    calibrated: bool = False,
) -> dict:
    """Paired per-bout metric difference with a bootstrap interval.

    Both variants are scored on the identical held-out bouts, so the comparison
    is paired and the interval reflects the spread of the *difference*, not the
    spread of two independent means.
    """
    a = predictions[predictions["variant"] == baseline].set_index("fight_url")
    b = predictions[predictions["variant"] == challenger].set_index("fight_url")
    shared = a.index.intersection(b.index)
    if len(shared) == 0:
        return {"baseline": baseline, "challenger": challenger, "n": 0,
                "delta": float("nan"), "lo": float("nan"), "hi": float("nan")}
    a, b = a.loc[shared], b.loc[shared]

    prob_col = "p_a_calibrated" if (calibrated and "p_a_calibrated" in predictions.columns) else "p_a"

    def loss(frame: pd.DataFrame) -> np.ndarray:
        p = np.clip(frame[prob_col].to_numpy(dtype=float), EPS, 1 - EPS)
        y = frame["y_a"].to_numpy(dtype=float)
        if metric == "log_loss":
            return -(y * np.log(p) + (1 - y) * np.log(1 - p))
        if metric == "brier":
            return (p - y) ** 2
        if metric == "accuracy":
            return ((p >= 0.5) == (y == 1)).astype(float)
        if metric == "auc":
            raise ValueError("auc is not a per-bout loss; compare it on the segment table")
        raise ValueError(metric)

    d = loss(b) - loss(a)  # negative = challenger better for losses
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(d), size=(n_boot, len(d)))
    boots = d[idx].mean(axis=1)
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return {
        "baseline": baseline, "challenger": challenger, "metric": metric,
        "n": int(len(d)), "delta": float(d.mean()), "lo": float(lo), "hi": float(hi),
        "favours": ("challenger" if hi < 0 else "baseline" if lo > 0 else "neither")
        if metric != "accuracy"
        else ("challenger" if lo > 0 else "baseline" if hi < 0 else "neither"),
    }


def benchmark_predictions(predictions: pd.DataFrame, inputs: Inputs) -> pd.DataFrame:
    """The two reference forecasts every variant is measured against.

    ``market`` is the hard baseline: closing odds with the vig removed. ``naive``
    is p = 0.5 — genuinely uninformative, and deliberately not "always fighter_a",
    which would score 63% on row order alone.
    """
    base = predictions.drop_duplicates("fight_url")[
        ["fight_url", "event_date", "event_name", "fighter_a", "fighter_b", "y_a",
         "prior_a", "prior_b"]
    ].copy()
    out = []
    naive = base.copy()
    naive["p_a"] = 0.5
    naive["variant"] = "bench_naive"
    out.append(naive)
    if not inputs.odds.empty and "implied_prob_a_no_vig" in inputs.odds.columns:
        ok = inputs.odds
        if "odds_data_quality" in ok.columns:
            ok = ok[ok["odds_data_quality"].eq("ok")]
        market = base.merge(
            ok[["fight_url", "implied_prob_a_no_vig"]].drop_duplicates("fight_url"),
            on="fight_url", how="inner",
        )
        market["p_a"] = pd.to_numeric(market["implied_prob_a_no_vig"], errors="coerce")
        market = market.dropna(subset=["p_a"]).drop(columns=["implied_prob_a_no_vig"])
        market["variant"] = "bench_market"
        out.append(market)
    return pd.concat(out, ignore_index=True, sort=False)


# ---------------------------------------------------------------------------
# Resumable sweep


def _cache_key(snapshot_dir: Path, variant: Variant, extra: dict) -> str:
    payload = {"snapshot": Path(snapshot_dir).name, "variant": variant.__dict__,
               "schema": CACHE_SCHEMA_VERSION, **extra}
    blob = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def run_sweep(
    inputs: Inputs,
    variants: list[Variant],
    eval_events: pd.DataFrame,
    *,
    cache_dir: Path,
    calibration_events: pd.DataFrame | None = None,
    min_prior_fights: int = DEFAULT_MIN_PRIOR_FIGHTS,
    whr_iterations: int | None = None,
    force: bool = False,
    progress: bool = True,
) -> pd.DataFrame:
    """Score every variant on the same held-out events, resuming from cache.

    Results are persisted per ``(variant, folds, parameters)`` so an interrupted
    sweep resumes instead of restarting, and partial results compose.
    """
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    fold_key = hashlib.sha256(
        pd.util.hash_pandas_object(eval_events[["event_date", "event_name"]], index=False)
        .to_numpy().tobytes()
    ).hexdigest()[:12]
    extra = {"folds": fold_key, "min_prior": min_prior_fights, "whr_iterations": whr_iterations}

    if calibration_events is None:
        calibration_events = split_calibration_events(inputs.fights, eval_events)
    extra["calib"] = int(len(calibration_events))

    def _keys(events: pd.DataFrame) -> set:
        return set(zip(events["event_date"], events["event_name"]))

    eval_keys = _keys(eval_events)
    calib_keys = _keys(calibration_events) if not calibration_events.empty else set()

    def _select(preds: pd.DataFrame, keys: set) -> pd.DataFrame:
        if not keys:
            return preds.iloc[:0]
        mask = np.array(
            [(d, n) in keys for d, n in zip(preds["event_date"], preds["event_name"])],
            dtype=bool,
        )
        return preds[mask]

    frames = []
    for variant in variants:
        path = cache_dir / f"{variant.name}__{_cache_key(inputs.snapshot_dir, variant, extra)}.parquet"
        if path.exists() and not force:
            if progress:
                print(f"  [cache] {variant.name}", flush=True)
            frames.append(pd.read_parquet(path))
            continue
        if progress:
            print(f"  [run]   {variant.name} ({variant.engine})", flush=True)
        if variant.engine == "whr":
            eval_preds = whr_predictions(inputs, variant, eval_events,
                                         iterations=whr_iterations, progress=progress)
            calib_preds = whr_predictions(inputs, variant, calibration_events,
                                          iterations=whr_iterations, progress=progress)
        else:
            # One sweep yields every one-step-ahead prediction; the fold sets
            # only choose which of them are read.
            sweep = online_predictions(inputs, variant)
            eval_preds = _select(sweep, eval_keys)
            calib_preds = _select(sweep, calib_keys)

        def _floor(frame: pd.DataFrame) -> pd.DataFrame:
            return frame[
                (frame["prior_a"] >= min_prior_fights) & (frame["prior_b"] >= min_prior_fights)
            ].reset_index(drop=True)

        eval_preds, calib_preds = _floor(eval_preds), _floor(calib_preds)
        temperature = (
            fit_temperature(calib_preds["p_a"].to_numpy(), calib_preds["y_a"].to_numpy())
            if len(calib_preds) else 1.0
        )
        eval_preds = eval_preds.copy()
        eval_preds["temperature"] = temperature
        eval_preds["p_a_calibrated"] = apply_temperature(eval_preds["p_a"].to_numpy(), temperature)
        eval_preds["n_calibration_bouts"] = int(len(calib_preds))
        eval_preds.to_parquet(path, index=False)
        frames.append(eval_preds)

    if not frames:
        return pd.DataFrame()
    allp = pd.concat(frames, ignore_index=True, sort=False)
    # Paired comparison requires the identical bout set for every variant.
    counts = allp.groupby("fight_url")["variant"].nunique()
    complete = set(counts[counts == len(variants)].index)
    return allp[allp["fight_url"].isin(complete)].reset_index(drop=True)
