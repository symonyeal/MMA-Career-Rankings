"""Price a win over an opponent returning from a long absence.

The adjustment lowers the opponent value used by the title, contender and
Prime achievement calculations; it never changes either fighter's rating. Its
unit is the era's normal turnaround rather than a fixed number of days, which
keeps the rule comparable as fight schedules change. The policy evidence and
rejected rating-layer alternative are recorded in ``docs/DECISIONS.md``.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# The era's normal turnaround, read off the schedule rather than asserted.
NORMAL_TURNAROUND_QUANTILE = 0.75
MIN_TURNAROUND_SAMPLE = 200
FALLBACK_TURNAROUND_DAYS = 270.0

# The charge is capped, because a gap is not proof of absence: it is equally the
# shape of a fight the corpus does not hold. Whole-career coverage is 99.8% for
# the 1,825 fighters with three or more UFC bouts -- the only ones who can move
# a published board -- and thinner outside them. Under-charging a genuine long
# absence is the mistake worth making, because it errs toward the rating the
# fights themselves support.
MAX_EXCESS_TURNAROUNDS = 4.0

# Elo removed from an opponent's price per era-normal turnaround of absence
# beyond the first. Stated policy in the sense CONTENDER_LINE_MU is, set by the
# project owner on 2026-09-03, and not fitted: the transitions that would
# identify it are the ones the corpus is worst at holding, because a fighter who
# returns badly often does not fight again, so the decline never becomes an
# observed change. The same survivorship flattens the measured age curve after
# 39 -- see docs/DECISIONS.md.
OPPONENT_LAYOFF_ELO_PER_TURNAROUND = -90.0

LAYOFF_COLUMNS = ["fighter", "event_date", "layoff_excess"]


def era_normal_turnaround(appearances: pd.DataFrame) -> pd.Series:
    """Calendar year -> the normal gap between bouts in that year, in days.

    Years with too few transitions to estimate one take the corpus-wide value,
    so a thin early year cannot invent an implausibly short normal.
    """
    frame = appearances[["fighter", "event_date"]].copy()
    frame["event_date"] = pd.to_datetime(frame["event_date"], errors="coerce")
    frame = frame.dropna(subset=["fighter", "event_date"]).sort_values(
        ["fighter", "event_date"]
    )
    if frame.empty:
        return pd.Series(dtype="float64")
    frame["gap"] = frame.groupby("fighter")["event_date"].diff().dt.days
    gaps = frame.dropna(subset=["gap"])
    if gaps.empty:
        return pd.Series(dtype="float64")
    corpus = float(gaps["gap"].quantile(NORMAL_TURNAROUND_QUANTILE))
    by_year = gaps.groupby(gaps["event_date"].dt.year)["gap"]
    normal = by_year.quantile(NORMAL_TURNAROUND_QUANTILE)
    thin = by_year.size() < MIN_TURNAROUND_SAMPLE
    normal[thin.reindex(normal.index).fillna(True)] = corpus
    return normal.clip(lower=1.0)


def appearance_layoff_excess(appearances: pd.DataFrame) -> pd.DataFrame:
    """How far past a normal turnaround each appearance followed the last one.

    Returned in era-normal turnarounds, capped, and zero for a fighter's first
    recorded bout -- an absence before a career started is not an absence.
    """
    frame = appearances[["fighter", "event_date"]].copy()
    frame["event_date"] = pd.to_datetime(frame["event_date"], errors="coerce")
    frame = frame.dropna(subset=["fighter", "event_date"])
    if frame.empty:
        return pd.DataFrame(columns=LAYOFF_COLUMNS)
    frame = frame.drop_duplicates(["fighter", "event_date"]).sort_values(
        ["fighter", "event_date"]
    )
    normal = era_normal_turnaround(frame)
    gap = frame.groupby("fighter")["event_date"].diff().dt.days
    reference = (
        frame["event_date"].dt.year.map(normal).fillna(FALLBACK_TURNAROUND_DAYS)
    )
    excess = np.clip(gap / reference - 1.0, 0.0, MAX_EXCESS_TURNAROUNDS)
    frame["layoff_excess"] = excess.fillna(0.0)
    return frame[LAYOFF_COLUMNS].reset_index(drop=True)


def discount_opponent_mu(
    opponent_mu: pd.Series,
    layoff_excess: pd.Series,
    *,
    elo_per_turnaround: float = OPPONENT_LAYOFF_ELO_PER_TURNAROUND,
) -> pd.Series:
    """Price an opponent at what they were on the night, not at their level.

    Additive on the rating scale, where the quantity lives. The result is what a
    win over them is measured against; it is never written back to the
    opponent's own rating.
    """
    mu = pd.to_numeric(opponent_mu, errors="coerce")
    excess = (
        pd.to_numeric(layoff_excess, errors="coerce")
        .reindex(mu.index)
        .fillna(0.0)
        .clip(lower=0.0, upper=MAX_EXCESS_TURNAROUNDS)
    )
    return mu + float(elo_per_turnaround) * excess


def attach_opponent_layoff(
    priced: pd.DataFrame,
    appearances: pd.DataFrame,
    *,
    opponent_col: str = "opponent",
    mu_col: str = "opponent_mu",
    elo_per_turnaround: float = OPPONENT_LAYOFF_ELO_PER_TURNAROUND,
) -> pd.DataFrame:
    """Add ``layoff_excess`` and replace ``mu_col`` with the discounted price.

    One join, so every ledger that prices an opponent does it the same way.
    """
    if priced.empty or mu_col not in priced.columns:
        return priced
    excess = appearance_layoff_excess(appearances).rename(
        columns={"fighter": opponent_col}
    )
    out = priced.merge(
        excess, on=[opponent_col, "event_date"], how="left", validate="many_to_one"
    )
    out["layoff_excess"] = pd.to_numeric(
        out["layoff_excess"], errors="coerce"
    ).fillna(0.0)
    out[mu_col] = discount_opponent_mu(
        out[mu_col], out["layoff_excess"], elo_per_turnaround=elo_per_turnaround
    )
    return out
