"""What a win is worth against an opponent who had been away.

The rating model prices an opponent by their rating as at the bout. That rating
charges elapsed time at an age rate and nothing else, so ageing while competing
and ageing while idle cost the same. Stipe Miocic was 35 and active when Daniel
Cormier fought him and 42 with 44 months away when Jon Jones did; the published
trajectory separates those two Stipes by 34 rating points, and the two wins are
priced as near-equivalents.

**This corrects the price of the win, not the opponent's rating.** Putting the
charge in the WHR transition prior was built and measured on 2026-09-03 and
refused: a transition prior constrains the difference between consecutive
nodes, while a fighter's level is pinned by their record, so "you declined
across this gap" is equally satisfiable as "you used to be better". It chose
the latter for gap-heavy careers -- Sean Sherk's 1999 rating rose from 1927 to
2124, Mark Coleman's 1996 peak from 1768 to 1948 -- and because erratic careers
concentrate in the old era it made the all-time board's era skew worse, not
better (Spearman against the previous board 0.895 -> 0.813). That is structural
and cannot be tuned away. See ``docs/DECISIONS.md``.

Applied here instead, the same judgement reaches every published number that
prices a win -- the title ledger, the contender resume, the elite-Prime gate --
and reaches nothing that does not. A fighter's own rating continues to say what
their fights say.

**The unit is an era-normal turnaround, not a year, and that is deliberate.**
A fixed number of days cannot mean "a layoff" across this corpus, because the
sport's rhythm changed underneath it: the 75th-percentile gap between bouts runs
112 days in 1995 and 392 in 2020, since fighters used to compete five times a
year and now fight twice. Charged in days past a fixed grace, a 2020-era gap is
charged 4.8x what a 1995-era one is, which is an era penalty wearing a layoff
costume. Divided by the era's own normal, mean charged excess runs 0.298
turnarounds in 1995 against 0.369 in 2025.
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
