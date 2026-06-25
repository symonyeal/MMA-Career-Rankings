"""Tests for the 2026-06-25 dominance + era-premium upgrades (U1/U2/U3).

Covers: per-minute exposure normalization, the finish floor, the decision
scorecard "round win gap" component (U2), the data-driven monotone era premium
curve (U3), and the WHR era-de-trend exemption flag (U1).
"""
import numpy as np
import pandas as pd
import pytest

from ratings.constants import DOMINANCE_FINISH_FLOOR_Z
from ratings.dominance import per_fight_dominance
from ratings.peaks import _era_division_normalized_mu
from ratings.rate_snapshot import _build_era_premium_by_year


def _rounds(rows):
    cols = ["fight_url", "fighter", "round_num", "sig_str_landed", "sub_att", "ctrl_seconds"]
    return pd.DataFrame(rows, columns=cols)


def _fights(rows):
    cols = ["fight_url", "fighter_a", "fighter_b", "winner", "is_draw",
            "method_class", "end_round", "end_time_seconds", "event_date"]
    return pd.DataFrame(rows, columns=cols)


def test_finish_floor_lifts_low_stat_ko():
    # A KO win with almost no accumulated stats must still read as dominant.
    rounds = _rounds([
        ["f_ko", "A", 1, 2, 0, 5],     # winner barely out-struck before the KO
        ["f_ko", "B", 1, 1, 0, 0],
        ["f_dec", "C", 1, 50, 0, 200], ["f_dec", "D", 1, 10, 0, 0],
        ["f_dec2", "E", 1, 30, 0, 100], ["f_dec2", "F", 1, 25, 0, 60],
    ])
    fights = _fights([
        ["f_ko", "A", "B", "A", False, "KO/TKO", 1, 30, "2020-01-01"],
        ["f_dec", "C", "D", "C", False, "Decision - Unanimous", 3, 300, "2020-01-01"],
        ["f_dec2", "E", "F", "E", False, "Decision - Split", 3, 300, "2020-01-01"],
    ])
    fd = per_fight_dominance(rounds, fights).set_index("fight_url")["dominance_a"]
    assert fd["f_ko"] >= DOMINANCE_FINISH_FLOOR_Z - 1e-9   # floored, not ~0


def test_per_minute_normalization_rewards_pace():
    # Identical winner totals, different durations: the shorter (higher-pace)
    # fight is the more dominant per-minute performance.
    rounds = _rounds([
        ["fast", "A", 1, 100, 0, 200], ["fast", "B", 1, 5, 0, 0],
        ["slow", "C", 1, 100, 0, 200], ["slow", "D", 1, 5, 0, 0],
    ])
    fights = _fights([
        ["fast", "A", "B", "A", False, "Decision - Unanimous", 1, 300, "2020-01-01"],   # 5 min
        ["slow", "C", "D", "C", False, "Decision - Unanimous", 5, 300, "2020-01-01"],   # 25 min
    ])
    fd = per_fight_dominance(rounds, fights).set_index("fight_url")["dominance_a"]
    assert fd["fast"] > fd["slow"]


def test_scorecard_round_gap_separates_decisions():
    # Same stats; a 50-45 sweep must out-dominate a 48-47 squeaker via the gap.
    rounds = _rounds([
        ["sweep", "A", 1, 40, 0, 100], ["sweep", "B", 1, 35, 0, 80],
        ["close", "C", 1, 40, 0, 100], ["close", "D", 1, 35, 0, 80],
    ])
    fights = _fights([
        ["sweep", "A", "B", "A", False, "Decision - Unanimous", 5, 300, "2020-01-01"],
        ["close", "C", "D", "C", False, "Decision - Unanimous", 5, 300, "2020-01-01"],
    ])
    scorecards = pd.DataFrame({
        "red_fighter_name": ["A", "C"],
        "blue_fighter_name": ["B", "D"],
        "event_date": pd.to_datetime(["2020-01-01", "2020-01-01"]),
        "red_fighter_total_pts": ["50 50 50", "48 48 48"],
        "blue_fighter_total_pts": ["45 45 45", "47 47 47"],
    })
    fd = per_fight_dominance(rounds, fights, scorecards=scorecards).set_index("fight_url")["dominance_a"]
    assert fd["sweep"] > fd["close"]


def test_era_premium_curve_monotone_and_zeroed_at_reference():
    rng = np.random.default_rng(0)
    rows = []
    for year, level in [(2005, 1580), (2010, 1640), (2015, 1660), (2020, 1685)]:
        for _ in range(60):  # > 40-row reliability floor
            rows.append({"event_date": pd.Timestamp(f"{year}-06-01"),
                         "mu_canonical": level + rng.normal(0, 5)})
    hist = pd.DataFrame(rows)
    prem = _build_era_premium_by_year(hist)
    years = sorted(prem)
    assert all(prem[years[i]] <= prem[years[i + 1]] + 1e-9 for i in range(len(years) - 1))
    assert prem[2010] == pytest.approx(0.0, abs=1e-6)   # reference year is the zero point
    assert prem[2020] > prem[2005]                       # modern era carries a premium


def test_era_detrend_flag_preserves_year_structure():
    # Build a cross-era field (fighters spanning years => bridges identifiable).
    rng = np.random.default_rng(1)
    rows = []
    for fid in range(150):  # > ERA_NORM_MIN_POPULATION (200 rows) so the normalizer runs
        for year in (2005, 2015):
            rows.append({
                "mu": (1500 if year == 2005 else 1650) + rng.normal(0, 20),
                "event_date": pd.Timestamp(f"{year}-06-01"),
                "division": "LW" if fid % 2 else "WW",
                "fighter": f"f{fid}",
            })
    merged = pd.DataFrame(rows)

    detr = _era_division_normalized_mu(merged, "mu", detrend_era=True)
    keep = _era_division_normalized_mu(merged, "mu", detrend_era=False)
    yr = merged["event_date"].dt.year

    def year_gap(series):
        return series[yr == 2015].mean() - series[yr == 2005].mean()

    # De-trending compresses the cross-era gap; the exemption leaves it intact.
    assert year_gap(keep) > year_gap(detr)
