"""Division-context resume rankings and home-division identification.

The current fighter table has one row per fighter, but division rankings are
not a one-row-per-fighter problem. A fighter belongs to the divisions where
the bouts happened, and a two-fight title cameo should not inherit a full
legacy from another weight class.

This module produces two artifacts:

* ``division_resume_rows`` — one row per (fighter, division), scored from only
  the bouts in that division and shrunk toward a prior of *division pool mean +
  bounded cross-division pedigree bump*. The bump gives a proven mover a small
  starting credit when they arrive in a new class ("first fight bump"); the
  reliability shrinkage then flattens the score toward their real in-division
  resume as fights accumulate.
* ``primary_division_rows`` — each fighter's home division, picked by the most
  recent UFC title-fight win (permanent moves) and majority-of-career
  otherwise. See ``primary_division_rows`` for the full rule.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ratings.constants import (
    DIVISION_CARRYOVER_CAP,
    DIVISION_CARRYOVER_FRAC,
    DIVISION_HOME_RECENCY_HALFLIFE_DAYS,
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
from ratings.performance_adjustment import DIVISION_WEIGHT_LIMIT_LB


DIVISION_RELIABILITY_K: float = 8.0

# The real, weight-limited UFC divisions a fighter can call "home". Catch Weight,
# Open Weight, and any unparsed label are excluded from home-division candidacy.
REAL_DIVISIONS: frozenset[str] = frozenset(DIVISION_WEIGHT_LIMIT_LB)


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
        "division_last_fight_date",
        "division_last_title_win_date",
        "division_recency_weight",
        "division_score_raw_whr",
        "division_score_reliability",
        "division_carryover_bump",
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

    # Reference date for recency weighting of the home-division pick: the most
    # recent bout in the snapshot. Recent fights weigh ~1, older ones decay on a
    # half-life so a couple of fights up or down a class cannot, on their own,
    # outweigh a long-established division.
    as_of = pd.to_datetime(merged["event_date"], errors="coerce").max()

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
        dates = pd.to_datetime(group["event_date"], errors="coerce")
        last_fight_date = dates.max()
        title_win_dates = dates[title_win.to_numpy()]
        last_title_win_date = title_win_dates.max() if not title_win_dates.empty else pd.NaT
        if pd.notna(as_of):
            days_ago = (as_of - dates).dt.days.clip(lower=0).fillna(0.0).to_numpy()
            recency_weight = float(np.sum(0.5 ** (days_ago / DIVISION_HOME_RECENCY_HALFLIFE_DAYS)))
        else:
            recency_weight = float(len(group))
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
            "division_last_fight_date": last_fight_date,
            "division_last_title_win_date": last_title_win_date,
            "division_recency_weight": recency_weight,
            "division_score_raw_whr": raw_score,
        })

    out = pd.DataFrame(rows)
    if out.empty:
        return pd.DataFrame(columns=columns)

    # Shrink each fighter/division resume toward a prior, scaled by how reliable
    # the in-division sample is (n_eff / (n_eff + K)). The prior is the division
    # pool mean PLUS a bounded cross-division pedigree bump: a proven champion
    # moving up starts a little above the pool rather than at its mediocre
    # average, and the score then flattens toward their real in-division resume
    # as fights accumulate. The bump is capped so it is never a full legacy loan
    # across weight classes — a two-fight cameo cannot inherit another division's
    # reign.
    pool = out.groupby("division")["division_score_raw_whr"].transform("mean")
    fighter_best = out.groupby("fighter")["division_score_raw_whr"].transform("max")
    pedigree = (fighter_best - pool).clip(lower=0.0)
    carryover = np.minimum(DIVISION_CARRYOVER_FRAC * pedigree, DIVISION_CARRYOVER_CAP)
    prior = pool + carryover
    eff = pd.to_numeric(out["division_effective_fights"], errors="coerce").fillna(0.0)
    reliability = eff / (eff + DIVISION_RELIABILITY_K)
    out["division_carryover_bump"] = carryover
    out["division_score_reliability"] = reliability
    out[score_col] = prior + reliability * (out["division_score_raw_whr"] - prior)
    return out[columns].sort_values(["division", score_col], ascending=[True, False]).reset_index(drop=True)


def primary_division_rows(division_resume: pd.DataFrame) -> pd.DataFrame:
    """Pick each fighter's career *and* current division.

    Two divisional concepts, not one — they answer different questions and the
    same fighter often belongs to two different classes by them:

    * ``career_division`` — where the bulk of the UFC career happened. The
      simple majority of effective fights (with recency as a tiebreak). A
      proven WW with one MW cameo is a WW (GSP); a long-tenured LW with one
      WW title win is still a career LW (Makhachev). This is the bucket that
      drives single-division leaderboards: when a user filters by Lightweight,
      Makhachev shows up there, not under his current Welterweight belt.
    * ``current_division`` — where the fighter competes now. The most recent
      UFC title-fight *win* anchors this (winning a belt is the permanent
      move signal); otherwise the most recent fight's division. So Makhachev
      is currently WW (just won the belt), Topuria is currently LW (won the
      LW belt), McGregor is currently LW (his last title-win division).
      Losing a title shot up or down a class never relocates a fighter
      (Volkanovski's LW title losses keep him FW on both labels).

    Catch Weight / Open Weight / unparsed labels are never eligible for
    either label.

    ``career_division_reliability`` / ``current_division_reliability`` are the
    picked division's resume reliability in [0, 1] — how *earned* the label is.
    A long-tenured champion sits near 1.0 on both; a fresh title mover sits
    high on career and low on current.
    """
    columns = [
        "fighter",
        "career_division",
        "career_division_reliability",
        "current_division",
        "current_division_reliability",
    ]
    if division_resume is None or division_resume.empty:
        return pd.DataFrame(columns=columns)
    d = division_resume.copy()
    d["division_effective_fights"] = pd.to_numeric(
        d["division_effective_fights"], errors="coerce"
    ).fillna(0.0)
    d["division_title_wins"] = pd.to_numeric(
        d.get("division_title_wins"), errors="coerce"
    ).fillna(0.0)
    d["division_recency_weight"] = pd.to_numeric(
        d.get("division_recency_weight"), errors="coerce"
    ).fillna(0.0)
    d["division_score_reliability"] = pd.to_numeric(
        d.get("division_score_reliability"), errors="coerce"
    ).fillna(0.0)
    d["division_score_whr"] = pd.to_numeric(d.get("division_score_whr"), errors="coerce")
    last_title_win = pd.to_datetime(d.get("division_last_title_win_date"), errors="coerce")
    # NaT sorts last under ascending=False; use a far-past sentinel so divisions
    # without a title win never win the "most recent title win" tie-break.
    d["_last_title_win"] = last_title_win.fillna(pd.Timestamp.min)

    rows: list[dict] = []
    for fighter, group in d.groupby("fighter", sort=False):
        candidates = group[group["division"].isin(REAL_DIVISIONS)]
        if candidates.empty:
            candidates = group  # catchweight-only resume: fall back to all rows

        # Career: simple majority of effective fights, recency as tiebreak. One
        # cameo up or down a class never displaces a long-tenured division.
        career_pick = candidates.sort_values(
            ["division_effective_fights", "division_recency_weight", "division_score_whr"],
            ascending=[False, False, False],
        ).iloc[0]

        # Current: most recent UFC title-fight win (the permanent-move signal).
        # If the fighter never won a UFC title, there is no permanent move and
        # current collapses to career — the user's principle is that a couple of
        # bouts up or down a class never relocates a non-champion.
        champion = candidates[candidates["division_title_wins"] > 0]
        if not champion.empty:
            current_pick = champion.sort_values(
                ["_last_title_win", "division_effective_fights", "division_score_whr"],
                ascending=[False, False, False],
            ).iloc[0]
        else:
            current_pick = career_pick

        rows.append({
            "fighter": fighter,
            "career_division": career_pick["division"],
            "career_division_reliability": float(career_pick["division_score_reliability"]),
            "current_division": current_pick["division"],
            "current_division_reliability": float(current_pick["division_score_reliability"]),
        })
    return pd.DataFrame(rows, columns=columns)
