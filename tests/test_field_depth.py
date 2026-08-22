"""Field depth must be per-division, non-monotone, and scale-free where claimed."""
from __future__ import annotations

import pandas as pd

from ratings.field_depth import (
    appearance_field,
    division_year_depth,
    field_percentile,
    opponent_quality_timeline,
)


def _fixture() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Two divisions, three years. Heavyweight dips in the middle year."""
    rows = []
    levels = {
        ("Heavyweight", 2013): [1800, 1780, 1760, 1740, 1720],
        ("Heavyweight", 2014): [1600, 1580, 1560, 1540, 1520],
        ("Heavyweight", 2015): [1810, 1790, 1770, 1750, 1730],
        ("Lightweight", 2013): [1700, 1690, 1680, 1670, 1660],
        ("Lightweight", 2014): [1710, 1700, 1690, 1680, 1670],
        ("Lightweight", 2015): [1720, 1710, 1700, 1690, 1680],
    }
    for (div, year), mus in levels.items():
        for i, mu in enumerate(mus):
            rows.append({
                "fighter": f"{div[:2]}{i}",
                "event_date": pd.Timestamp(f"{year}-06-01"),
                "event_name": f"{div} {year}",
                "mu_whr": float(mu),
                "weight_class": f"{div} Bout",
            })
    frame = pd.DataFrame(rows)
    history = frame[["fighter", "event_date", "event_name", "mu_whr"]]

    fights = []
    for (div, year), mus in levels.items():
        fights.append({
            "fighter_a": f"{div[:2]}0", "fighter_b": f"{div[:2]}1",
            "event_date": pd.Timestamp(f"{year}-06-01"),
            "weight_class": f"{div} Bout",
            "fighter_a_outcome": "W", "fighter_b_outcome": "L",
            "is_excluded": False, "is_title_fight": False,
        })
    # Every fighter needs an appearance row, so pair the rest off too.
    for (div, year), mus in levels.items():
        fights.append({
            "fighter_a": f"{div[:2]}2", "fighter_b": f"{div[:2]}3",
            "event_date": pd.Timestamp(f"{year}-06-01"),
            "weight_class": f"{div} Bout",
            "fighter_a_outcome": "W", "fighter_b_outcome": "L",
            "is_excluded": False, "is_title_fight": False,
        })
        fights.append({
            "fighter_a": f"{div[:2]}4", "fighter_b": f"{div[:2]}0",
            "event_date": pd.Timestamp(f"{year}-06-01"),
            "weight_class": f"{div} Bout",
            "fighter_a_outcome": "L", "fighter_b_outcome": "W",
            "is_excluded": False, "is_title_fight": False,
        })
    return history, pd.DataFrame(fights)


def test_depth_is_per_division_and_non_monotone():
    history, fights = _fixture()
    depth = division_year_depth(appearance_field(history, fights))
    hw = depth[depth["division"].eq("Heavyweight")].set_index("year")["depth"]
    lw = depth[depth["division"].eq("Lightweight")].set_index("year")["depth"]

    # The 2014 heavyweight dip survives: nothing is carried forward as a maximum.
    assert hw[2014] < hw[2013]
    assert hw[2014] < hw[2015]
    # Divisions are measured separately in the same year.
    assert hw[2013] > lw[2013]
    assert hw[2014] < lw[2014]


def test_weight_class_labels_are_normalized_to_a_division():
    history, fights = _fixture()
    fights.loc[0, "weight_class"] = "UFC Heavyweight Title Bout"
    depth = division_year_depth(appearance_field(history, fights))
    assert set(depth["division"]) == {"Heavyweight", "Lightweight"}


def test_field_percentile_is_scale_free_across_a_shifted_era():
    """Adding a constant to a whole division-year must not move its percentiles."""
    history, fights = _fixture()
    shifted = history.copy()
    mask = shifted["event_date"].dt.year.eq(2014)
    shifted.loc[mask, "mu_whr"] += 400.0

    base = field_percentile(appearance_field(history, fights))
    moved = field_percentile(appearance_field(shifted, fights))
    key = ["division", "year", "fighter"]
    merged = base.merge(moved, on=key, suffixes=("_base", "_moved"))
    assert (merged["field_pct_base"] - merged["field_pct_moved"]).abs().max() < 1e-12


def test_opponent_timeline_reports_both_raw_and_field_relative_quality():
    history, fights = _fixture()
    appearances = appearance_field(history, fights)
    timeline = opponent_quality_timeline(fights, appearances, fighters=["He0"])
    assert not timeline.empty
    assert timeline["opponent_field_pct"].notna().all()
    assert timeline["opponent_mu"].notna().all()
    # 2014 opponents are far weaker in raw rating but sit in the same field.
    by_year = timeline.groupby("year")[["opponent_mu", "opponent_field_pct"]].mean()
    assert by_year.loc[2014, "opponent_mu"] < by_year.loc[2013, "opponent_mu"] - 100
    assert abs(by_year.loc[2014, "opponent_field_pct"]
               - by_year.loc[2013, "opponent_field_pct"]) < 1e-9
