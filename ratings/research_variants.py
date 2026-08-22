"""Weighted-evidence variants used only by the research harness.

Production rating is one bout likelihood with one shared weight per bout
(``ratings.rate_snapshot``). The constructions here — side-specific appearance
sleeves, dominance-amplified weights, and the weighted Glicko updater — exist so
``ratings.prequential`` can *test* whether any of them beats that core on
held-out events. They are kept out of the snapshot builder deliberately: a
variant that has not won a held-out comparison must not be reachable from the
code that writes the public board.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ratings.constants import WHR_DOMINANCE_SCORE_SCALE
from ratings.glicko2_engine import WeightedRatingEngine
from ratings.rate_snapshot import _iter_event_bouts


def attach_appearance_weights(
    fights: pd.DataFrame,
    weight_table: pd.DataFrame,
    weight_col: str,
) -> pd.DataFrame:
    """Pivot per-appearance weights back onto bout rows as ``weight_a/weight_b``.

    Side-specific weights break the paired Bradley--Terry likelihood WHR needs,
    so only the weighted Glicko filter may consume the result.
    """
    out = fights.copy()
    w = weight_table[["fight_url", "fighter", weight_col]].copy()
    a = w.rename(columns={"fighter": "fighter_a", weight_col: "weight_a"})
    b = w.rename(columns={"fighter": "fighter_b", weight_col: "weight_b"})
    out = out.merge(a, on=["fight_url", "fighter_a"], how="left")
    out = out.merge(b, on=["fight_url", "fighter_b"], how="left")
    out["weight_a"] = out["weight_a"].fillna(1.0).astype(float)
    out["weight_b"] = out["weight_b"].fillna(1.0).astype(float)
    # Cross-org down-weight scales the whole per-fight update. UFC bouts carry
    # org_weight 1.0, so this is a no-op at the production scope.
    if "org_weight" in out.columns:
        ow = pd.to_numeric(out["org_weight"], errors="coerce").fillna(1.0)
        out["weight_a"] = out["weight_a"] * ow
        out["weight_b"] = out["weight_b"] * ow
    return out


def winner_dominance_level(perf_app: pd.DataFrame) -> dict:
    """Map fight_url -> winner dominance level in [0, 1].

    Uses ``dominance_score_winner`` (signed so the winner is positive) through a
    sigmoid, then folds to a positive-only level. Non-dominant or unknown fights
    map to 0.
    """
    if perf_app is None or perf_app.empty or "dominance_score_winner" not in perf_app.columns:
        return {}
    dom = perf_app[["fight_url", "dominance_score_winner"]].drop_duplicates("fight_url")
    d = pd.to_numeric(dom["dominance_score_winner"], errors="coerce").fillna(0.0)
    level = (
        2.0 / (1.0 + np.exp(-d / max(WHR_DOMINANCE_SCORE_SCALE, 1e-9))) - 1.0
    ).clip(lower=0.0, upper=1.0)
    return dict(zip(dom["fight_url"], level))


def amplify_dominance_weight(
    weighted: pd.DataFrame, dom_level_by_fight: dict, amplitude: float,
) -> pd.DataFrame:
    """Scale BOTH sides' likelihood weight by how dominant the bout was.

    The hypothesis under test: a dominant bout is stronger evidence in both
    directions, so each side's weight is multiplied by
    ``1 + amplitude * dom_level``. Because the factor is shared, the result is
    still one bout likelihood and remains admissible for WHR. A close bout
    (``dom_level`` 0) is unchanged.
    """
    if amplitude <= 0 or not dom_level_by_fight:
        return weighted
    out = weighted.copy()
    lvl = out["fight_url"].map(dom_level_by_fight).fillna(0.0)
    factor = 1.0 + amplitude * lvl
    out["weight_a"] = pd.to_numeric(out["weight_a"], errors="coerce") * factor
    out["weight_b"] = pd.to_numeric(out["weight_b"], errors="coerce") * factor
    return out


def run_weighted_engine(
    fights: pd.DataFrame,
    *,
    tau: float,
    score_mode: str,
) -> WeightedRatingEngine:
    engine = WeightedRatingEngine(tau=tau, score_mode=score_mode)
    cols_needed = [
        "fighter_a", "fighter_b", "winner", "is_draw",
        "method_score_winner", "weight_a", "weight_b",
    ]
    if "quality_score_winner" in fights.columns:
        cols_needed.append("quality_score_winner")
    for event_date, event_name, bouts in _iter_event_bouts(fights, cols_needed):
        engine.process_event(event_date, event_name, bouts)
    return engine
