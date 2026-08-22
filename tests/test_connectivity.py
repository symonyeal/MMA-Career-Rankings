"""Abstention is decided by independent paths, not by bout count."""
from __future__ import annotations

import pandas as pd

from ratings.connectivity import bridge_summary, connectivity


def _bouts(pairs: list[tuple[str, str]]) -> pd.DataFrame:
    return pd.DataFrame(pairs, columns=["fighter_a_id", "fighter_b_id"])


CORE = {"C1", "C2", "C3"}
CORE_BOUTS = {"C1": 10, "C2": 10, "C3": 10}


def test_repeated_bouts_against_one_bridge_are_one_path():
    """Twelve bouts with the same crossover fighter is a single anchor."""
    bouts = _bouts([("Y", "C1")] * 12)
    out = connectivity(bouts, CORE, core_bout_counts=CORE_BOUTS, fighters=["Y"])
    row = out.loc[out["fighter_id"].eq("Y")].iloc[0]
    assert row["disjoint_paths"] == 1
    assert row["verdict"] == "unranked - insufficiently connected"


def test_multi_hop_paths_still_reach_the_core():
    """A fighter who never met the core directly is anchored through his opponents."""
    bouts = _bouts([
        ("X", "B1"), ("X", "B2"), ("X", "B3"),
        ("B1", "C1"), ("B2", "C2"), ("B3", "C3"),
    ])
    out = connectivity(bouts, CORE, core_bout_counts=CORE_BOUTS, fighters=["X"])
    row = out.loc[out["fighter_id"].eq("X")].iloc[0]
    assert row["disjoint_paths"] == 3
    assert row["rankable"]
    # Reached at depth two, so he has no *direct* core opponents at all.
    assert row["bridge_opponents"] == 0


def test_an_isolated_component_abstains():
    out = connectivity(_bouts([("Z", "W")]), CORE, core_bout_counts=CORE_BOUTS,
                       fighters=["Z"])
    row = out.loc[out["fighter_id"].eq("Z")].iloc[0]
    assert row["disjoint_paths"] == 0
    assert not row["rankable"]


def test_a_thin_bridge_does_not_anchor():
    """A crossover opponent with a two-bout record is not evidence of scale."""
    bouts = _bouts([("X", "C1"), ("X", "C2"), ("X", "C3")])
    thin = {"C1": 1, "C2": 1, "C3": 1}
    out = connectivity(bouts, CORE, core_bout_counts=thin, fighters=["X"])
    row = out.loc[out["fighter_id"].eq("X")].iloc[0]
    assert row["bridge_opponents"] == 0
    assert not row["rankable"]


def test_core_members_are_always_rankable():
    bouts = _bouts([("C1", "C2")])
    out = connectivity(bouts, CORE, core_bout_counts=CORE_BOUTS)
    assert out.loc[out["fighter_id"].eq("C1"), "rankable"].all()


def test_bridge_summary_counts_distinct_opponents():
    bouts = _bouts([("X", "C1"), ("X", "C1"), ("X", "C2")])
    summary = bridge_summary(bouts, CORE, core_bout_counts=CORE_BOUTS)
    row = summary.loc[summary["fighter_id"].eq("X")].iloc[0]
    assert row["opponents"] == 2
    assert row["bridge_opponents"] == 2
