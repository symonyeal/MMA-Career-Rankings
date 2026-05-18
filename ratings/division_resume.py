"""Division-context resume rankings.

The current fighter table has one row per fighter, but division rankings are
not a one-row-per-fighter problem. A fighter belongs to the divisions where
the bouts happened, and a two-fight title cameo should not inherit a full
legacy from another weight class.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ratings.constants import (
    PERIOD_DRAW_BASE_WEIGHT,
    PERIOD_LOSS_BASE_WEIGHT,
    PERIOD_LOSS_QUALITY_SCALE,
    PERIOD_WIN_BASE_WEIGHT,
)
from ratings.peaks import (
    _context_adjustment,
    _resume_bonus,
    _result_adjustment,
    _title_effective_count,
    _title_ladder_mass,
    _title_ladder_parts,
)


DIVISION_RELIABILITY_K: float = 8.0


def _appearance_weights(group: pd.DataFrame) -> pd.Series:
    score = pd.to_numeric(group["actual_score"], errors="coerce").fillna(0.0).to_numpy()
    opp_w = pd.to_numeric(group["opp_weight"], errors="coerce").fillna(0.0).to_numpy()
    level = (
        pd.to_numeric(group["opponent_quality_level"], errors="coerce")
        .fillna(0.0)
        .clip(0.0, 1.0)
        .to_numpy()
    )
    is_win = score >= 1.0
    is_draw = (score > 0.0) & (score < 1.0)
    weights = np.where(
        is_win,
        PERIOD_WIN_BASE_WEIGHT + opp_w,
        np.where(
            is_draw,
            PERIOD_DRAW_BASE_WEIGHT + 0.5 * opp_w,
            PERIOD_LOSS_BASE_WEIGHT + PERIOD_LOSS_QUALITY_SCALE * (1.0 - level),
        ),
    )
    return pd.Series(weights, index=group.index, dtype="float64")


def division_resume_rows(
    rating_history: pd.DataFrame,
    appearance_quality: pd.DataFrame,
    *,
    mu_col: str = "mu_whr",
    score_col: str = "division_score_whr",
) -> pd.DataFrame:
    """Return one all-time resume row per fighter/division.

    The score uses only appearances in that division. It then shrinks short
    samples toward the division pool by ``n_eff / (n_eff + K)`` so small
    title cameos are rewarded but cannot dominate a long divisional reign.
    """
    columns = [
        "fighter",
        "division",
        "gender",
        "division_fights",
        "division_effective_fights",
        "division_wins",
        "division_losses",
        "division_draws",
        "division_title_fights",
        "division_title_wins",
        "division_title_defenses",
        "division_opp_weight_sum",
        "division_title_ladder_mass",
        "division_score_raw_whr",
        "division_score_reliability",
        score_col,
    ]
    if (
        rating_history is None
        or rating_history.empty
        or appearance_quality is None
        or appearance_quality.empty
        or mu_col not in rating_history.columns
    ):
        return pd.DataFrame(columns=columns)

    h = rating_history[["fighter", "event_date", "event_name", mu_col]].copy()
    h["event_date"] = pd.to_datetime(h["event_date"], errors="coerce")
    q_cols = [
        "fighter",
        "event_date",
        "event_name",
        "division",
        "opp_weight",
        "opponent_quality_level",
        "actual_score",
        "opponent_prefight_division_rank",
        "opponent_prefight_p4p_rank",
        "opponent_entered_as_champion",
        "opponent_entered_as_interim_champion",
        "fighter_entered_as_champion",
        "fighter_entered_as_interim_champion",
        "is_championship_bout",
        "is_interim_title_bout",
    ]
    available = [c for c in q_cols if c in appearance_quality.columns]
    q = appearance_quality[available].copy()
    q["event_date"] = pd.to_datetime(q["event_date"], errors="coerce")
    merged = h.merge(q, on=["fighter", "event_date", "event_name"], how="inner")
    merged = merged.dropna(subset=["fighter", "division", mu_col])
    if merged.empty:
        return pd.DataFrame(columns=columns)

    for col in (
        "is_championship_bout",
        "is_interim_title_bout",
        "opponent_entered_as_champion",
        "opponent_entered_as_interim_champion",
        "fighter_entered_as_champion",
        "fighter_entered_as_interim_champion",
    ):
        if col not in merged.columns:
            merged[col] = False
        merged[col] = merged[col].fillna(False).astype(bool)
    for col in ("opp_weight", "opponent_quality_level", "actual_score"):
        merged[col] = pd.to_numeric(merged[col], errors="coerce").fillna(0.0)

    rows: list[dict] = []
    for (fighter, division), group in merged.groupby(["fighter", "division"], sort=False):
        group = group.sort_values(["event_date", "event_name"]).copy()
        weights = _appearance_weights(group)
        adjusted_mu = (
            pd.to_numeric(group[mu_col], errors="coerce")
            + _result_adjustment(group["actual_score"])
            + _context_adjustment(group)
        )
        valid = weights.gt(0.0) & adjusted_mu.notna()
        if not valid.any():
            continue
        w_sum = float(weights.loc[valid].sum())
        if w_sum <= 0.0:
            continue
        base = float((weights.loc[valid] * adjusted_mu.loc[valid]).sum() / w_sum)
        title, title_win, title_defense = _title_ladder_parts(group)
        opp_sum = float(pd.to_numeric(group["opp_weight"], errors="coerce").fillna(0.0).sum())
        title_mass = _title_ladder_mass(group)
        raw_score = base + _resume_bonus(opp_sum, title_mass)
        actual = pd.to_numeric(group["actual_score"], errors="coerce").fillna(0.0)
        rows.append({
            "fighter": fighter,
            "division": division,
            "gender": "F" if str(division).startswith("Women's") else "M",
            "division_fights": int(len(group)),
            "division_effective_fights": _title_effective_count(group),
            "division_wins": int(actual.ge(1.0).sum()),
            "division_losses": int(actual.eq(0.0).sum()),
            "division_draws": int(((actual > 0.0) & (actual < 1.0)).sum()),
            "division_title_fights": int(title.sum()),
            "division_title_wins": int(title_win.sum()),
            "division_title_defenses": int(title_defense.sum()),
            "division_opp_weight_sum": opp_sum,
            "division_title_ladder_mass": title_mass,
            "division_score_raw_whr": raw_score,
        })

    out = pd.DataFrame(rows)
    if out.empty:
        return pd.DataFrame(columns=columns)

    pool = out.groupby("division")["division_score_raw_whr"].transform("mean")
    eff = pd.to_numeric(out["division_effective_fights"], errors="coerce").fillna(0.0)
    reliability = eff / (eff + DIVISION_RELIABILITY_K)
    out["division_score_reliability"] = reliability
    out[score_col] = pool + reliability * (out["division_score_raw_whr"] - pool)
    return out[columns].sort_values(["division", score_col], ascending=[True, False]).reset_index(drop=True)


def primary_division_rows(division_resume: pd.DataFrame) -> pd.DataFrame:
    """Pick the division most responsible for each fighter's UFC resume."""
    columns = ["fighter", "primary_division", "primary_division_share"]
    if division_resume is None or division_resume.empty:
        return pd.DataFrame(columns=columns)
    d = division_resume.copy()
    total = d.groupby("fighter")["division_effective_fights"].transform("sum")
    d["primary_division_share"] = (
        pd.to_numeric(d["division_effective_fights"], errors="coerce").fillna(0.0)
        / total.replace(0.0, np.nan)
    )
    d = d.sort_values(
        [
            "fighter",
            "division_effective_fights",
            "division_title_fights",
            "division_score_whr",
        ],
        ascending=[True, False, False, False],
    )
    out = d.groupby("fighter", as_index=False).first()
    return out.rename(columns={"division": "primary_division"})[
        ["fighter", "primary_division", "primary_division_share"]
    ]
