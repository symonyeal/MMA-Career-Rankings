"""The five career-functional charts must render, and must degrade politely.

Each one exists to make a specific claim checkable by eye: the rank interval,
the years-vs-height decomposition, the bar sensitivity, the evidence ladder,
and one fighter's own contribution receipt.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from analysis.viz import (
    career_bar_ladder_chart,
    career_contribution_chart,
    career_rank_interval_chart,
    career_shape_scatter,
    evidence_vs_rating_chart,
)
from ratings.symon_score import career_mass_family


def _uncertainty() -> pd.DataFrame:
    return pd.DataFrame({
        "fighter": ["A", "B", "C"],
        "mass": [900.0, 700.0, 650.0],
        "mass_lo": [820.0, 500.0, 300.0],
        "mass_hi": [980.0, 900.0, 1100.0],
        "mass_sd": [40.0, 100.0, 220.0],
        "rank": [1, 2, 3],
        "rank_lo": [1, 2, 2],
        "rank_hi": [1, 6, 30],
        "replicates_present": [50, 50, 50],
        "replicates": [50, 50, 50],
    })


def _current() -> pd.DataFrame:
    return pd.DataFrame({
        "fighter": ["A", "B", "C", "D"],
        "symon_career_skill_mass": [900.0, 700.0, 650.0, np.nan],
        "symon_career_active_years": [12, 5, 9, 2],
        "rating_periods": [25, 8, 19, 2],
        "mu_whr": [1700.0, 1660.0, 1640.0, 1520.0],
        "losses": [3, 0, 6, 1],
    })


def _history() -> pd.DataFrame:
    rows = []
    for fighter, level in (("A", 1700.0), ("B", 1600.0), ("C", 1500.0), ("D", 1450.0)):
        for year in range(2015, 2021):
            rows.append({
                "fighter": fighter,
                "event_date": pd.Timestamp(f"{year}-05-01"),
                "event_name": f"E{year}",
                "mu_whr": level + (year - 2015) * 5.0,
            })
    return pd.DataFrame(rows)


def test_rank_interval_chart_draws_a_band_and_a_point_per_fighter():
    fig = career_rank_interval_chart(_uncertainty(), n=3)
    # one band per fighter plus one marker trace for all of them
    assert len(fig.data) == 4
    assert list(fig.data[-1].y) == ["A", "B", "C"]
    assert fig.layout.yaxis.autorange == "reversed"


def test_rank_interval_chart_asks_for_the_artifact_when_missing():
    fig = career_rank_interval_chart(pd.DataFrame())
    assert "build_uncertainty" in fig.layout.annotations[0].text


def test_shape_scatter_puts_mass_over_years_on_the_y_axis():
    fig = career_shape_scatter(_current(), n=3)
    points = fig.data[-1]
    assert set(points.text) == {"A", "B", "C"}
    # mean yearly excess = mass / active years
    assert points.y[list(points.text).index("A")] == 900.0 / 12


def test_shape_scatter_without_the_columns_says_so():
    fig = career_shape_scatter(pd.DataFrame({"fighter": ["A"]}))
    assert "unavailable" in fig.layout.annotations[0].text


def test_bar_ladder_traces_one_line_per_fighter_across_the_family():
    fam = career_mass_family(_history(), references=("mean", 0.5, 0.9))
    fig = career_bar_ladder_chart(fam, n=2)
    assert len(fig.data) == 2
    assert list(fig.data[0].x) == ["mean", "0.5", "0.9"]


def test_evidence_chart_separates_undefeated_fighters():
    fig = evidence_vs_rating_chart(_current())
    names = {trace.name for trace in fig.data}
    assert names == {"has a loss", "undefeated"}
    unbeaten = next(t for t in fig.data if t.name == "undefeated")
    assert list(unbeaten.text) == ["B"]


def test_contribution_chart_totals_the_credited_excess():
    fig = career_contribution_chart(_history(), "A")
    credited = next(t for t in fig.data if t.name == "credited excess")
    assert (np.asarray(credited.y) >= 0).all()
    assert f"{np.asarray(credited.y).sum():.0f}" in fig.layout.title.text


def test_contribution_chart_handles_an_unknown_fighter():
    fig = career_contribution_chart(_history(), "Nobody")
    assert "no rated years" in fig.layout.annotations[0].text
