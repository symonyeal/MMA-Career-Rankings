"""Era-adjusted ratings: every rating read against its own year's contender line.

Let E_g(y) be the contender line of gender g in calendar year y -- the sport-wide year bar
:data:`ratings.symon_score.DEFAULT_CAREER_REFERENCE` over g's fighter-year mean ratings -- and
E_g* = sum_y n_g(y) E_g(y) / sum_y n_g(y) its mean over g's n_g(y) fighter-years. Then

    mu_era = mu_whr - (E_g(y) - E_g*).

The fit is untouched; this is a reading of it. Adding any c(y) to every rating of g in year y
moves E_g(y) by c(y) and mu_era by the constant sum_y n_g(y) c(y) / sum_y n_g(y), so a drift of
the scale over time cannot reach a board that reads mu_era.

Why (docs/DECISIONS.md, "The score reads era-adjusted ratings"): the smoother does not hold the
top of its scale fixed over time. On the 2026-10-14 fit the 60th-best man stood at 1,834 in 2007,
1,865 in 2011 and 1,918 in 2023. The title and skill terms already measure against a
division-year line; the résumé and the Prime gate measured against a fixed 1,750, so a win in
2023 was priced on a scale some 85 points higher than one in 2007.
"""
from __future__ import annotations

import pandas as pd

from ratings.symon_score import DEFAULT_CAREER_REFERENCE, year_reference

ERA_COL = "mu_era"


def era_shift(history: pd.DataFrame, gender: pd.Series, reference: str | float = DEFAULT_CAREER_REFERENCE) -> pd.Series:
    """E_g(y) - E_g* for each row of ``history``; ``gender`` maps fighter -> "M" | "F" (missing reads "M")."""
    y = pd.to_datetime(history["event_date"]).dt.year
    g = history["fighter"].map(gender).eq("F")
    d = pd.Series(0.0, index=history.index)
    for G in (False, True):
        h = history[g == G]
        if h.empty:
            continue
        a = (h.assign(year=y[g == G]).groupby(["fighter", "year"])["mu_whr"].mean()
             .rename("annual_mean").reset_index())
        E, n = year_reference(a, reference), a.groupby("year").size()
        d[g == G] = y[g == G].map(E - (E * n).sum() / n.sum())
    return d


def with_era(history: pd.DataFrame, gender: pd.Series) -> pd.DataFrame:
    """``history`` with the column :data:`ERA_COL` = mu_whr - (E_g(y) - E_g*)."""
    return history.assign(**{ERA_COL: history["mu_whr"] - era_shift(history, gender)})


def era_rated(history: pd.DataFrame) -> pd.DataFrame:
    """``history`` with mu_whr replaced by :data:`ERA_COL`, for the code that reads mu_whr."""
    return history.assign(mu_whr=history[ERA_COL])
