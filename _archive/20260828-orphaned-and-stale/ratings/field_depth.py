"""Division-year field depth, and opponent quality measured against it.

Phase 0 of the whole-sport plan: reporting only. Nothing here feeds the rating
layer, and nothing here is a bonus. The retired era premium was a *monotone*
ladder over year-means, which asserted the sport only ever gets deeper; the
measured record refutes that directly (heavyweight 2025 sits well below
heavyweight 2013, and below lightweight in its own year).

Two objects, both per division-year:

* ``D(d, a)`` — depth: the mean rating of the top-K active fighters.
* ``C(d, a)`` — the contender line: the K-th highest active rating.

And one derived per-appearance column, ``field_pct``: where a fighter sat
inside the contemporaneous field of their own division and year.

``field_pct`` is the column that matters for era talk. Absolute WHR levels
drift upward as the roster grows and the global mean re-anchors, so a raw
rating gap across eras is not by itself a claim about difficulty. A percentile
inside the contemporaneous field is scale-free and survives that drift. Where
this module reports absolute levels it also reports the bridge density behind
them, so the reader can see how much cross-era comparison the data supports.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ratings.performance_adjustment import normalize_division_label

# Top-K defining "the field" of a division-year. Five is the contender shortlist
# a division is usually argued about; the functions take it as an argument so a
# claim can be checked at another K rather than trusting this one.
DEFAULT_TOP_K = 5

# A division-year with fewer active rated fighters than this is reported but
# flagged: a "field" of three is not a field.
MIN_FIELD_SIZE = 8


def appearance_field(
    history: pd.DataFrame,
    fights: pd.DataFrame,
    *,
    mu_col: str = "mu_whr",
) -> pd.DataFrame:
    """One row per fighter-appearance: fighter, date, year, division, rating.

    Division comes from the bout's own weight class, not from a career label, so
    a fighter who moved up is counted in the division they actually fought in.
    """
    hist = history[["fighter", "event_date", mu_col]].copy()
    hist["event_date"] = pd.to_datetime(hist["event_date"])

    live = fights[~fights.get("is_excluded", pd.Series(False, index=fights.index)).fillna(False)]
    long = pd.concat([
        live[["fighter_a", "event_date", "weight_class"]].rename(columns={"fighter_a": "fighter"}),
        live[["fighter_b", "event_date", "weight_class"]].rename(columns={"fighter_b": "fighter"}),
    ], ignore_index=True)
    long["event_date"] = pd.to_datetime(long["event_date"])

    long["division"] = long["weight_class"].map(normalize_division_label)
    out = hist.merge(long.drop(columns=["weight_class"]),
                     on=["fighter", "event_date"], how="left")
    out = out.drop_duplicates(subset=["fighter", "event_date"])
    out["year"] = out["event_date"].dt.year
    out = out.rename(columns={mu_col: "mu"})
    return out.dropna(subset=["mu"]).reset_index(drop=True)


def fighter_division_years(appearances: pd.DataFrame) -> pd.DataFrame:
    """Collapse appearances to one rating per fighter, division and year."""
    g = (appearances.dropna(subset=["division"])
         .groupby(["division", "year", "fighter"], as_index=False)
         .agg(mu=("mu", "mean"), bouts=("mu", "size")))
    return g


def division_year_depth(
    appearances: pd.DataFrame,
    *,
    top_k: int = DEFAULT_TOP_K,
) -> pd.DataFrame:
    """``D(d, a)`` and the contender line ``C(d, a)`` per division-year.

    Non-monotone by construction: each year is measured on its own active
    fighters and nothing is carried forward as a running maximum.
    """
    fdy = fighter_division_years(appearances)
    rows = []
    for (div, year), g in fdy.groupby(["division", "year"]):
        vals = np.sort(g["mu"].to_numpy())[::-1]
        k = min(top_k, len(vals))
        rows.append({
            "division": div,
            "year": int(year),
            "depth": float(vals[:k].mean()),
            "contender_line": float(vals[k - 1]),
            "field_median": float(np.median(vals)),
            "active_fighters": int(len(vals)),
            "thin_field": bool(len(vals) < MIN_FIELD_SIZE),
            "top_k": int(k),
        })
    return pd.DataFrame(rows).sort_values(["division", "year"]).reset_index(drop=True)


def field_percentile(appearances: pd.DataFrame) -> pd.DataFrame:
    """Add ``field_pct``: rank of this rating inside its own division-year.

    Scale-free, so it is comparable across eras in a way a raw rating is not.
    """
    fdy = fighter_division_years(appearances)
    fdy["field_pct"] = (fdy.groupby(["division", "year"])["mu"]
                        .rank(pct=True, method="average"))
    fdy["field_size"] = fdy.groupby(["division", "year"])["mu"].transform("size")
    return fdy


def opponent_quality_timeline(
    fights: pd.DataFrame,
    appearances: pd.DataFrame,
    *,
    fighters: list[str] | None = None,
) -> pd.DataFrame:
    """Per-bout opponent quality, in raw rating *and* in field percentile.

    The two columns disagree in the interesting cases, which is the point: a
    flat raw-rating stretch can be an ascent through a division or a decline
    away from its top, and only the percentile distinguishes them.
    """
    fdy = field_percentile(appearances)
    pct_lookup = {(r.fighter, r.division, r.year): (r.mu, r.field_pct)
                  for r in fdy.itertuples()}

    ratings = (appearances.sort_values(["fighter", "event_date"])
               .groupby("fighter")[["event_date", "mu"]]
               .apply(lambda g: g.to_numpy()).to_dict())

    def rating_at(name: str, when) -> float:
        arr = ratings.get(name)
        if arr is None or len(arr) == 0:
            return np.nan
        dates = np.array([np.datetime64(d) for d in arr[:, 0]])
        idx = int(np.searchsorted(dates, np.datetime64(when), side="right")) - 1
        return float(arr[max(idx, 0), 1])

    live = fights[~fights.get("is_excluded", pd.Series(False, index=fights.index)).fillna(False)].copy()
    live["event_date"] = pd.to_datetime(live["event_date"])
    live["division"] = live["weight_class"].map(normalize_division_label)
    rows = []
    for r in live.itertuples():
        for me, opp, outcome in ((r.fighter_a, r.fighter_b, r.fighter_a_outcome),
                                 (r.fighter_b, r.fighter_a, r.fighter_b_outcome)):
            if fighters is not None and me not in fighters:
                continue
            year = r.event_date.year
            key = (opp, r.division, year)
            opp_mu, opp_pct = pct_lookup.get(key, (np.nan, np.nan))
            if not np.isfinite(opp_mu):
                opp_mu = rating_at(opp, r.event_date)
            rows.append({
                "fighter": me,
                "event_date": r.event_date,
                "year": year,
                "division": r.division,
                "opponent": opp,
                "outcome": outcome,
                "own_mu": rating_at(me, r.event_date),
                "opponent_mu": opp_mu,
                "opponent_field_pct": opp_pct,
                "is_title_fight": bool(getattr(r, "is_title_fight", False)),
            })
    return pd.DataFrame(rows).sort_values(["fighter", "event_date"]).reset_index(drop=True)


