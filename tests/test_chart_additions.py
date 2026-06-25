"""Tests for the 2026-06-23 notebook chart additions (analysis/CHART_PLAN.md).

Synthetic unit tests lock the aggregation logic without a snapshot; a smoke test
exercises every builder against the pinned snapshot when present.
"""
from pathlib import Path

import pandas as pd
import pytest

from analysis.viz import (
    dominance_leaderboard_chart,
    inactivity_table,
    integrity_impact_chart,
    integrity_ledger_table,
    legacy_vs_prime_scatter,
    load_snapshot,
    method_mix_timeline_chart,
    snapshot_movers_chart,
    striking_profile_chart,
    title_lineage_chart,
)

SNAPSHOT_DIR = Path("data/snapshots/2026-05-13")


# --- synthetic unit tests --------------------------------------------------

def test_striking_profile_normalizes_components():
    rounds = pd.DataFrame({
        "fighter": ["A", "A"],
        "head_landed": [6, 4], "body_landed": [0, 0], "leg_landed": [0, 0],
        "distance_landed": [5, 5], "clinch_landed": [0, 0], "ground_landed": [0, 0],
    })
    fig = striking_profile_chart(rounds, "A")
    # 6 traces: head/body/leg + distance/clinch/ground
    assert len(fig.data) == 6
    head = next(t for t in fig.data if t.name == "Head")
    assert head.x[0] == pytest.approx(1.0)  # 10 of 10 landed strikes to the head


def test_striking_profile_unknown_fighter_is_empty_state():
    rounds = pd.DataFrame({"fighter": ["A"], "head_landed": [1], "body_landed": [0],
                           "leg_landed": [0], "distance_landed": [1], "clinch_landed": [0],
                           "ground_landed": [0]})
    fig = striking_profile_chart(rounds, "Nobody")
    assert len(fig.data) == 0
    assert hasattr(fig, "layout")


def test_snapshot_movers_signs_and_empty_branch():
    cur = pd.DataFrame({"fighter": ["A", "B"], "mu_canonical": [1600.0, 1400.0]})
    prev = pd.DataFrame({"fighter": ["A", "B"], "mu_canonical": [1500.0, 1500.0]})
    fig = snapshot_movers_chart(cur, prev, rating_col="mu_canonical", n=5)
    assert len(fig.data) == 1
    xs = list(fig.data[0].x)
    assert min(xs) < 0 < max(xs)  # one riser (+100), one faller (-100)
    # no previous snapshot -> graceful empty state
    assert len(snapshot_movers_chart(cur, None).data) == 0


def test_method_mix_buckets_and_shares():
    fights = pd.DataFrame({
        "event_date": ["2020-01-01"] * 4,
        "weight_class": ["Lightweight Bout"] * 4,
        "method_class": ["KO/TKO", "Submission", "Decision - Unanimous", "Decision - Split"],
        "is_excluded": [False] * 4,
        "fighter_a": ["a", "c", "e", "g"], "fighter_b": ["b", "d", "f", "h"],
    })
    fig = method_mix_timeline_chart(fights)
    names = {t.name for t in fig.data}
    assert names == {"KO/TKO", "Submission", "Decision"}
    decision = next(t for t in fig.data if t.name == "Decision")
    assert decision.y[0] == pytest.approx(0.5)  # 2 of 4 fights went to decision


def test_inactivity_table_window_bounds():
    rc = pd.DataFrame({
        "fighter": ["Old", "Recent", "Active", "LowRated"],
        "months_inactive": [200.0, 30.0, 2.0, 30.0],
        "mu_canonical": [1800.0, 1800.0, 1800.0, 1500.0],
        "activity_mu_penalty": [50.0, 20.0, 0.0, 20.0],
        "mu_canonical_activity_adjusted": [1750.0, 1780.0, 1800.0, 1480.0],
        "last_event_date": ["2008-01-01", "2024-01-01", "2026-05-01", "2024-01-01"],
    })
    out = inactivity_table(rc, n=10)
    names = set(out["fighter"])
    assert "Recent" in names          # within 1-8yr window, highly rated
    assert "Old" not in names         # beyond max_months
    assert "Active" not in names      # below min_months
    assert "LowRated" not in names    # below min_rating


def test_integrity_ledger_and_impact():
    integ = pd.DataFrame({
        "fight_url": ["f1", "f2", "f3"],
        "fighter": ["A", "B", "C"],
        "integrity_factor_ped": [0.8, 1.0, 1.0],
        "integrity_factor_dq": [1.0, 0.92, 1.0],
        "integrity_factor_missed_weight": [1.0, 1.0, 1.0],
        "integrity_weight": [0.8, 0.92, 1.0],
    })
    attr = pd.DataFrame({
        "fight_url": ["f1", "f2"], "fighter": ["A", "B"],
        "event_date": ["2013-01-01", "2014-01-01"], "opponent": ["X", "Y"],
        "integrity_delta": [-49.0, -40.0],
    })
    ledger = integrity_ledger_table(integ, attr, n=10)
    assert set(ledger["reason"]) == {"PED", "DQ"}  # C never fired
    assert ledger.iloc[0]["fighter"] == "A"        # biggest hit first
    fig = integrity_impact_chart(integ, attr)
    assert len(fig.data) == 1


# --- snapshot smoke test ---------------------------------------------------

@pytest.fixture(scope="module")
def snapshot():
    if not SNAPSHOT_DIR.exists():
        pytest.skip(f"snapshot not present: {SNAPSHOT_DIR}")
    return load_snapshot(SNAPSHOT_DIR)


def test_new_builders_smoke(snapshot):
    rc = snapshot["ratings_current"]
    figs = [
        striking_profile_chart(snapshot["rounds"], "Jon Jones"),
        dominance_leaderboard_chart(snapshot["fighter_dominance"], rc, n=15),
        legacy_vs_prime_scatter(rc, n=40),
        method_mix_timeline_chart(snapshot["fights"], divisions=["Lightweight"]),
        title_lineage_chart(snapshot["performance_appearances"], division="Lightweight"),
        integrity_impact_chart(snapshot.get("integrity_appearances", pd.DataFrame()),
                               snapshot.get("sleeve_attribution", pd.DataFrame())),
    ]
    assert all(hasattr(f, "layout") for f in figs)
    assert inactivity_table(rc, n=10) is not None
    assert "reason" in integrity_ledger_table(
        snapshot.get("integrity_appearances", pd.DataFrame()),
        snapshot.get("sleeve_attribution", pd.DataFrame()),
    ).columns
