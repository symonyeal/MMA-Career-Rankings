"""Per-appearance opponent context for the division resume boards.

This module builds one row per fighter appearance carrying who the opponent
was, how good they were entering the bout, and whether a title was on the line.
``ratings.division_resume`` consumes it to score a fighter inside one weight
class.

It does **not** produce an all-time or period rating. The rolling five- and
ten-year "peak" scores that used to live here were retired on 2026-08-20: they
re-counted opponent quality, title status, activity volume and era position on
top of a latent skill estimate that already reflects those results, and they
carried roughly twenty hand-set constants to do it. The public period views are
now fixed windows over the WHR trajectory in ``ratings.symon_score``, and
opponent quality is counted once, where it belongs — in the rating itself.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ratings.constants import (
    HEADLINE_RESUME_BONUS_CAP,
    HEADLINE_RESUME_RATE,
    PERIOD_CHAMPION_WIN_BONUS,
    PERIOD_DRAW_PENALTY,
    PERIOD_INTERIM_CHAMPION_WIN_BONUS,
    PERIOD_INTERIM_TITLE_WIN_BONUS,
    PERIOD_LOSS_PENALTY,
    PERIOD_P4P_TOP15_WIN_BONUS,
    PERIOD_P4P_TOP5_WIN_BONUS,
    PERIOD_TITLE_FIGHT_BONUS,
    PERIOD_TITLE_FIGHT_WEIGHT_MULT,
    PERIOD_TITLE_WIN_BONUS,
    PERIOD_TOP10_WIN_BONUS,
    PERIOD_TOP15_WIN_BONUS,
    PERIOD_TOP5_WIN_BONUS,
    PERIOD_WIN_BONUS,
)
from ratings.opponent_quality import (
    combined_opponent_quality_level,
    peak_opponent_weight_from_level,
)
from ratings.performance_adjustment import (
    DIVISION_WEIGHT_LIMIT_LB,
    normalize_division_label,
    prefight_ranking_context,
)


PEAK_APPEARANCE_COLUMNS = [
    "fight_url",
    "event_date",
    "event_name",
    "fighter",
    "opponent",
    "opponent_prefight_mu",
    "opponent_quality_level",
    "opp_weight",
    "actual_score",
    "opponent_prefight_division_rank",
    "opponent_prefight_p4p_rank",
    "opponent_entered_as_champion",
    "opponent_entered_as_interim_champion",
    "fighter_entered_as_champion",
    "fighter_entered_as_interim_champion",
    "is_championship_bout",
    "is_interim_title_bout",
    "division",
    "division_weight_limit_lb",
]


def _prefight_mu_table(canonical_history: pd.DataFrame) -> pd.DataFrame:
    if canonical_history is None or canonical_history.empty:
        return pd.DataFrame(columns=["fighter", "event_date", "event_name", "prefight_mu"])
    h = canonical_history[["fighter", "event_date", "event_name", "mu_canonical"]].copy()
    h["event_date"] = pd.to_datetime(h["event_date"], errors="coerce")
    h = h.sort_values(["fighter", "event_date", "event_name"]).reset_index(drop=True)
    h["prefight_mu"] = h.groupby("fighter")["mu_canonical"].shift(1).fillna(1500.0)
    return h[["fighter", "event_date", "event_name", "prefight_mu"]]


def peak_appearance_quality(
    canonical_fights: pd.DataFrame,
    canonical_history: pd.DataFrame,
) -> pd.DataFrame:
    """Return one opponent-quality row per actual fighter appearance."""
    if canonical_fights is None or canonical_fights.empty:
        return pd.DataFrame(columns=PEAK_APPEARANCE_COLUMNS)

    f = canonical_fights.copy()
    f["event_date"] = pd.to_datetime(f["event_date"], errors="coerce")
    context = prefight_ranking_context(f, canonical_history)
    f = f.merge(context, on="fight_url", how="left")
    f["division"] = f.get("weight_class", pd.Series(index=f.index)).map(normalize_division_label)
    f["division_weight_limit_lb"] = f["division"].map(DIVISION_WEIGHT_LIMIT_LB)

    prior = _prefight_mu_table(canonical_history)
    prior_a = prior.rename(columns={"fighter": "fighter_a", "prefight_mu": "prefight_mu_a"})
    prior_b = prior.rename(columns={"fighter": "fighter_b", "prefight_mu": "prefight_mu_b"})
    f = f.merge(prior_a, on=["fighter_a", "event_date", "event_name"], how="left")
    f = f.merge(prior_b, on=["fighter_b", "event_date", "event_name"], how="left")
    for col in ("prefight_mu_a", "prefight_mu_b"):
        f[col] = pd.to_numeric(f[col], errors="coerce").fillna(1500.0)

    common = [
        "fight_url",
        "event_date",
        "event_name",
        "fighter_a",
        "fighter_b",
        "winner",
        "is_draw",
        "is_championship_bout",
        "is_interim_title_bout",
        "division",
        "division_weight_limit_lb",
    ]
    a = f[common + [
        "prefight_mu_b",
        "fighter_b_prefight_division_rank",
        "fighter_b_prefight_p4p_rank",
        "fighter_b_entered_as_champion",
        "fighter_b_entered_as_interim_champion",
        "fighter_a_entered_as_champion",
        "fighter_a_entered_as_interim_champion",
    ]].rename(columns={
        "fighter_a": "fighter",
        "fighter_b": "opponent",
        "prefight_mu_b": "opponent_prefight_mu",
        "fighter_b_prefight_division_rank": "opponent_prefight_division_rank",
        "fighter_b_prefight_p4p_rank": "opponent_prefight_p4p_rank",
        "fighter_b_entered_as_champion": "opponent_entered_as_champion",
        "fighter_b_entered_as_interim_champion": "opponent_entered_as_interim_champion",
        "fighter_a_entered_as_champion": "fighter_entered_as_champion",
        "fighter_a_entered_as_interim_champion": "fighter_entered_as_interim_champion",
    })
    b = f[common + [
        "prefight_mu_a",
        "fighter_a_prefight_division_rank",
        "fighter_a_prefight_p4p_rank",
        "fighter_a_entered_as_champion",
        "fighter_a_entered_as_interim_champion",
        "fighter_b_entered_as_champion",
        "fighter_b_entered_as_interim_champion",
    ]].rename(columns={
        "fighter_b": "fighter",
        "fighter_a": "opponent",
        "prefight_mu_a": "opponent_prefight_mu",
        "fighter_a_prefight_division_rank": "opponent_prefight_division_rank",
        "fighter_a_prefight_p4p_rank": "opponent_prefight_p4p_rank",
        "fighter_a_entered_as_champion": "opponent_entered_as_champion",
        "fighter_a_entered_as_interim_champion": "opponent_entered_as_interim_champion",
        "fighter_b_entered_as_champion": "fighter_entered_as_champion",
        "fighter_b_entered_as_interim_champion": "fighter_entered_as_interim_champion",
    })
    out = pd.concat([a, b], ignore_index=True, sort=False)
    out["opponent_quality_level"] = combined_opponent_quality_level(
        opponent_mu=out["opponent_prefight_mu"],
        opponent_rank=out["opponent_prefight_division_rank"],
        opponent_p4p_rank=out["opponent_prefight_p4p_rank"],
        opponent_champion=out["opponent_entered_as_champion"],
        opponent_interim=out["opponent_entered_as_interim_champion"],
        is_title=out["is_championship_bout"],
        is_interim_title=out["is_interim_title_bout"],
    )
    out["opp_weight"] = peak_opponent_weight_from_level(out["opponent_quality_level"])
    # Title bouts weigh more in the window mean — win or lose. Opponent quality
    # is the first-priority signal and a title fight is the clearest marker of
    # it (a GSP title-fight decision outweighs a finish over a mid-ranker).
    title_bout = (
        out["is_championship_bout"].fillna(False).astype(bool)
        | out["is_interim_title_bout"].fillna(False).astype(bool)
    )
    out.loc[title_bout, "opp_weight"] = (
        out.loc[title_bout, "opp_weight"] * PERIOD_TITLE_FIGHT_WEIGHT_MULT
    )
    out["actual_score"] = np.select(
        [
            out["is_draw"].fillna(False).astype(bool),
            out["winner"].eq(out["fighter"]),
        ],
        [0.5, 1.0],
        default=0.0,
    )
    return out[PEAK_APPEARANCE_COLUMNS].copy()


def _result_adjustment(actual_score: pd.Series) -> pd.Series:
    score = pd.to_numeric(actual_score, errors="coerce").fillna(0.0)
    return pd.Series(
        np.select(
            [score >= 1.0, score == 0.5],
            [PERIOD_WIN_BONUS, -PERIOD_DRAW_PENALTY],
            default=-PERIOD_LOSS_PENALTY,
        ),
        index=score.index,
        dtype="float64",
    )


def _context_adjustment(window: pd.DataFrame) -> pd.Series:
    """Per-fight win-context bonus — the single strongest "who you beat" signal.

    The title-win, champion-win, divisional-rank and P4P-rank bonuses all
    describe the same underlying fact: *you won against elite opposition*.
    They are therefore DEDUPLICATED VIA ``max`` — only the strongest applicable
    bonus contributes, not their sum. Previously they were summed, so a title
    win over a top-5 / P4P-top-5 reigning champion stacked
    ``8 + 55 + 35 + 25 + 25 = 148`` mu of bonus on a single fight; that
    multiple-counting floated title-reign-then-decline resumes (Benson
    Henderson, Chris Weidman). The ``max`` matches how
    ``combined_opponent_quality_level`` and the performance sleeve already
    handle overlapping opponent-quality signals.

    Title-fight *participation* (``PERIOD_TITLE_FIGHT_BONUS``) stays a small
    separate additive term — it applies win OR lose, so it is not part of the
    win-context dedup group.
    """
    score = pd.to_numeric(window["actual_score"], errors="coerce").fillna(0.0)
    won = score >= 1.0
    title = window["is_championship_bout"].fillna(False).astype(bool)
    interim_title = window["is_interim_title_bout"].fillna(False).astype(bool)
    opp_champ = window["opponent_entered_as_champion"].fillna(False).astype(bool)
    opp_interim = window["opponent_entered_as_interim_champion"].fillna(False).astype(bool)
    opp_rank = pd.to_numeric(window["opponent_prefight_division_rank"], errors="coerce")
    opp_p4p = pd.to_numeric(window["opponent_prefight_p4p_rank"], errors="coerce")

    idx = window.index
    components: list[pd.Series] = []

    def _component(mask: pd.Series, value: float) -> None:
        s = pd.Series(0.0, index=idx, dtype="float64")
        s.loc[mask] = value
        components.append(s)

    _component(won & title, PERIOD_TITLE_WIN_BONUS)
    _component(won & interim_title, PERIOD_INTERIM_TITLE_WIN_BONUS)
    _component(won & opp_champ, PERIOD_CHAMPION_WIN_BONUS)
    _component(won & opp_interim, PERIOD_INTERIM_CHAMPION_WIN_BONUS)
    _component(won & opp_rank.between(1, 5), PERIOD_TOP5_WIN_BONUS)
    _component(won & opp_rank.between(6, 10), PERIOD_TOP10_WIN_BONUS)
    _component(won & opp_rank.between(11, 15), PERIOD_TOP15_WIN_BONUS)
    _component(won & opp_p4p.between(1, 5), PERIOD_P4P_TOP5_WIN_BONUS)
    _component(won & opp_p4p.between(6, 15), PERIOD_P4P_TOP15_WIN_BONUS)

    # Deduplicated: the single strongest applicable win-context bonus.
    win_context = (
        pd.concat(components, axis=1).max(axis=1)
        if components
        else pd.Series(0.0, index=idx, dtype="float64")
    )
    # Title-fight participation — small, separate, applies win or lose.
    participation = pd.Series(0.0, index=idx, dtype="float64")
    participation.loc[title] = PERIOD_TITLE_FIGHT_BONUS
    return win_context + participation


def _title_ladder_parts(window: pd.DataFrame) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Return title-appearance, title-win, and title-defense masks."""
    idx = window.index
    title = (
        window.get("is_championship_bout", pd.Series(False, index=idx)).fillna(False).astype(bool)
        | window.get("is_interim_title_bout", pd.Series(False, index=idx)).fillna(False).astype(bool)
    )
    won = pd.to_numeric(
        window.get("actual_score", pd.Series(0.0, index=idx)),
        errors="coerce",
    ).fillna(0.0).ge(1.0)
    entered_champ = (
        window.get("fighter_entered_as_champion", pd.Series(False, index=idx)).fillna(False).astype(bool)
        | window.get("fighter_entered_as_interim_champion", pd.Series(False, index=idx)).fillna(False).astype(bool)
    )
    defense = title & won & entered_champ
    return title, title & won, defense


def _resume_bonus(window_opp_weight_sum: float, title_ladder_mass: float = 0.0) -> float:
    """Headline proven-resume bonus with title-ladder mass, capped at cap."""
    if window_opp_weight_sum is None or np.isnan(window_opp_weight_sum):
        return float("nan")
    ladder = 0.0 if title_ladder_mass is None or np.isnan(title_ladder_mass) else float(title_ladder_mass)
    raw = HEADLINE_RESUME_RATE * (float(window_opp_weight_sum) + ladder)
    return float(np.clip(raw, 0.0, HEADLINE_RESUME_BONUS_CAP))


