"""The one place that decides which population a ranking is over.

Men's and women's bouts are **disjoint components of the bout graph**. Measured
on the 2026-08-13 snapshot: of 80,697 rated bouts, **zero** join a man to a
woman and the two sides share **zero** opponents. Adding a constant to every
rating in the women's component therefore changes no modelled bout probability
-- the offset between the two levels is set by the prior, not by evidence.

It is not a small effect on a board. 2026-08-25 measured total female career
mass running from 0 at -200 Elo to 45,382 at +200, moving Zhang Weili from rank
30 with zero mass to rank 13 with 886. So a mixed ranking publishes an
unidentified gauge as if it were a result, and it does so at whatever value the
prior happened to leave it.

Ranks **within** each component are identified, and are the only ranking this
engine can defend. Every surface that orders fighters -- the published boards,
the snapshot's headline prints, the bootstrap tiers, the notebook leaderboard --
partitions here first, so there is one rule and not five.

This module deliberately holds no policy about *display*: it returns the two
populations and lets each surface decide how to show them. What it does fix is
that "all-time" or "prime" without a gender means **men's**, which is the
published default.
"""
from __future__ import annotations

import pandas as pd

# Ordered so that iterating a partition puts the published default first.
GENDERS: tuple[str, ...] = ("M", "F")
GENDER_LABEL = {"M": "men's", "F": "women's"}
# Artifact/column suffix. The men's board keeps the unsuffixed name because it
# is the default anyone asking for "the board" means.
GENDER_SUFFIX = {"M": "", "F": "_women"}
DEFAULT_GENDER = "M"

GENDER_GAUGE_NOTE = (
    "Men and women do not compete against each other, so the engine publishes "
    "separate boards and each rank applies only within its own board."
)


def female_mask(frame: pd.DataFrame) -> pd.Series:
    """``True`` where the row is a woman, ``False`` where it is not or unknown.

    An unlabelled fighter is **not** asserted into the women's component. The
    gender column is produced by ``rate_snapshot._attach_recent_division_gender``,
    which propagates across these same disjoint components and is guarded by a
    majority test on gendered billings; a blank there means the inference found
    no gendered billing to read, which is an abstention, not a female label.
    """
    if frame is None or "gender" not in getattr(frame, "columns", ()):
        return pd.Series(False, index=getattr(frame, "index", pd.Index([])))
    label = frame["gender"].astype(str).str.upper().str.strip()
    return label.str.startswith("F") & ~label.str.startswith("M")


def partition_by_gender(frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Split a fighter-keyed frame into the two bout-graph components.

    Returns ``{"M": ..., "F": ...}`` in that order. A frame with no ``gender``
    column gets one entry under ``"M"`` -- a single mixed population -- rather
    than a silent claim to have separated something. Callers that must know the
    difference can test for the ``"F"`` key.
    """
    if frame is None or len(frame) == 0 or "gender" not in getattr(frame, "columns", ()):
        return {DEFAULT_GENDER: frame}
    female = female_mask(frame)
    return {"M": frame[~female].copy(), "F": frame[female].copy()}


def select_gender(frame: pd.DataFrame, gender: str | None) -> pd.DataFrame:
    """One population by name; ``None`` means the published default.

    Raises on an unknown label rather than quietly returning everybody, for the
    same reason ``ratings.scope`` raises: silently widening a population and
    calling it the requested one is how an unidentified comparison gets
    published as a result.
    """
    if gender is None:
        gender = DEFAULT_GENDER
    if gender not in GENDERS:
        raise ValueError(
            f"unknown gender {gender!r}; expected one of {', '.join(GENDERS)}"
        )
    partition = partition_by_gender(frame)
    if gender not in partition:
        return frame.iloc[0:0] if frame is not None else frame
    return partition[gender]


def select_component_fights(
    fights: pd.DataFrame,
    population: pd.DataFrame,
) -> pd.DataFrame:
    """Keep only bouts wholly inside a selected fighter population.

    Bootstrap event weights must be drawn inside the same disconnected bout
    graph that is being ranked. Otherwise unrelated cards in another component
    change the Dirichlet weights and therefore the reported interval even
    though they cannot change the component's point estimate.
    """
    if fights is None or fights.empty:
        return fights
    if population is None or population.empty or "fighter" not in population.columns:
        return fights.iloc[0:0].copy()
    required = {"fighter_a", "fighter_b"}
    if not required.issubset(fights.columns):
        raise ValueError(
            "cannot select a bout-graph component without fighter_a and fighter_b"
        )
    fighters = set(population["fighter"].dropna().astype(str))
    inside = (
        fights["fighter_a"].astype(str).isin(fighters)
        & fights["fighter_b"].astype(str).isin(fighters)
    )
    return fights.loc[inside].copy().reset_index(drop=True)
