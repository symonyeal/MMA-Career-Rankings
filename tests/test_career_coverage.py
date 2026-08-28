"""The coverage gate must fail on the corpus shape that broke the top 100.

Two fighters with identical UFC records, one of whom passed through a crawled
promotion and therefore has their pre-UFC regional record in the corpus while
the other does not. That is not a hypothetical: measured on the 2026-08-13
snapshot, the median recorded pre-UFC bout count was 12 for the fighters whose
Sherdog career page had been read and 1 for the fighters whose had not.
"""
from __future__ import annotations

import pandas as pd

from loaders.career_coverage import (
    coverage_rows,
    coverage_summary,
    is_coverage_symmetric,
)


def _ufc_bouts(names: list[str], per_fighter: int = 5) -> pd.DataFrame:
    rows = []
    for name in names:
        for i in range(per_fighter):
            rows.append({
                "fighter_a": name,
                "fighter_b": f"{name} opponent {i}",
                "event_date": pd.Timestamp("2020-01-01") + pd.Timedelta(days=90 * i),
            })
    return pd.DataFrame(rows)


def _regional_bouts(name: str, count: int) -> pd.DataFrame:
    return pd.DataFrame([
        {
            "fighter_a": name,
            "fighter_b": f"{name} regional {i}",
            "event_date": pd.Timestamp("2016-01-01") + pd.Timedelta(days=60 * i),
        }
        for i in range(count)
    ])


def test_asymmetric_coverage_is_reported_and_fails_the_gate():
    canonical = _ufc_bouts(["Covered", "Truncated"])
    corpus = pd.concat([canonical, _regional_bouts("Covered", 12)], ignore_index=True)

    rows = coverage_rows(
        canonical,
        corpus,
        sherdog_ids={"Covered": "1", "Truncated": "2"},
        read_ids={"1"},
    )
    by_fighter = rows.set_index("fighter")
    assert by_fighter.loc["Covered", "pre_ufc_bouts"] == 12
    assert by_fighter.loc["Truncated", "pre_ufc_bouts"] == 0
    assert bool(by_fighter.loc["Covered", "career_page_read"]) is True
    assert bool(by_fighter.loc["Truncated", "career_page_read"]) is False

    summary = coverage_summary(rows, min_ufc_bouts=3)
    assert summary["eligible"] == 2
    assert summary["career_page_share"] == 0.5
    assert summary["pre_ufc_bouts_gap"] == 12.0
    assert not is_coverage_symmetric(summary)


def test_symmetric_coverage_passes_the_gate():
    canonical = _ufc_bouts(["Covered", "AlsoCovered"])
    corpus = pd.concat(
        [canonical, _regional_bouts("Covered", 12), _regional_bouts("AlsoCovered", 9)],
        ignore_index=True,
    )
    rows = coverage_rows(
        canonical,
        corpus,
        sherdog_ids={"Covered": "1", "AlsoCovered": "2"},
        read_ids={"1", "2"},
    )
    summary = coverage_summary(rows, min_ufc_bouts=3)
    assert summary["career_page_share"] == 1.0
    # With one rule there is no second group, so the statistic has nothing to
    # measure -- which is the point, not a coincidence.
    assert summary["pre_ufc_bouts_gap"] == 0.0
    assert is_coverage_symmetric(summary)


def test_fighters_below_the_ufc_floor_do_not_decide_the_gate():
    canonical = pd.concat(
        [_ufc_bouts(["Ranked"], per_fighter=5), _ufc_bouts(["Debutant"], per_fighter=1)],
        ignore_index=True,
    )
    corpus = pd.concat([canonical, _regional_bouts("Ranked", 10)], ignore_index=True)
    rows = coverage_rows(
        canonical,
        corpus,
        sherdog_ids={"Ranked": "1", "Debutant": "2"},
        read_ids={"1"},
    )
    summary = coverage_summary(rows, min_ufc_bouts=3)
    assert summary["eligible"] == 1
    assert is_coverage_symmetric(summary)


def test_missing_cache_reports_no_pages_read_rather_than_raising():
    canonical = _ufc_bouts(["Covered"])
    rows = coverage_rows(canonical, canonical)
    assert not rows["career_page_read"].any()
    summary = coverage_summary(rows, min_ufc_bouts=3)
    assert summary["eligible"] == 1  # the five one-bout opponents are below the floor
    assert summary["career_page_share"] == 0.0
    assert not is_coverage_symmetric(summary)
