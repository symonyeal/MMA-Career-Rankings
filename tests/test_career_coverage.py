"""The coverage gate must fail on the corpus shape that broke the top 100.

Two fighters with identical UFC records, one of whom passed through a crawled
promotion and therefore has their pre-UFC regional record in the corpus while
the other does not. The gate measures rows incorporated, not merely pages
cached, because a cached but unmerged page still leaves the rated record short.
"""
from __future__ import annotations

import pandas as pd
import pytest

from loaders.career_coverage import (
    cached_page_ids,
    coverage_rows,
    coverage_summary,
    incorporated_page_ids,
    is_coverage_symmetric,
    record_incorporated_page_ids,
)
from loaders.page_cache import open_cache
from ratings.rate_snapshot import _require_career_coverage


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
        merged_ids={"1"},
    )
    by_fighter = rows.set_index("fighter")
    assert by_fighter.loc["Covered", "pre_ufc_bouts"] == 12
    assert by_fighter.loc["Truncated", "pre_ufc_bouts"] == 0
    assert bool(by_fighter.loc["Covered", "whole_career_merged"]) is True
    assert bool(by_fighter.loc["Truncated", "whole_career_merged"]) is False

    summary = coverage_summary(rows, min_ufc_bouts=3)
    assert summary["eligible"] == 2
    assert summary["whole_career_share"] == 0.5
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
        merged_ids={"1", "2"},
    )
    summary = coverage_summary(rows, min_ufc_bouts=3)
    assert summary["whole_career_share"] == 1.0
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
        merged_ids={"1"},
    )
    summary = coverage_summary(rows, min_ufc_bouts=3)
    assert summary["eligible"] == 1
    assert is_coverage_symmetric(summary)


def test_missing_extension_reports_no_careers_merged_rather_than_raising():
    canonical = _ufc_bouts(["Covered"])
    rows = coverage_rows(canonical, canonical)
    assert not rows["whole_career_merged"].any()
    summary = coverage_summary(rows, min_ufc_bouts=3)
    assert summary["eligible"] == 1  # the five one-bout opponents are below the floor
    assert summary["whole_career_share"] == 0.0
    assert not is_coverage_symmetric(summary)


def test_cached_page_ids_reads_the_shared_store(tmp_path):
    cache = open_cache(tmp_path)
    cache.put("fighters", "17", "fighter page")
    cache.put("events", "23", "event page")
    cache.close()

    assert cached_page_ids(tmp_path) == {"17"}


def test_manifest_covers_a_page_with_only_duplicate_rows(tmp_path):
    event_bouts = pd.DataFrame(
        {"fighter_a_id": ["17"], "source": ["event_page"]}
    )
    assert incorporated_page_ids(tmp_path, event_bouts) == set()

    record_incorporated_page_ids(tmp_path, {"17"})

    assert incorporated_page_ids(tmp_path, event_bouts) == {"17"}


def test_majors_rating_requires_a_passing_coverage_audit(tmp_path):
    with pytest.raises(ValueError, match="requires a career-coverage audit"):
        _require_career_coverage(tmp_path, "majors")

    pd.DataFrame(
        {
            "fighter": ["Covered", "Truncated"],
            "ufc_bouts": [5, 5],
            "corpus_bouts": [17, 5],
            "pre_ufc_bouts": [12, 0],
            "sherdog_id": ["1", "2"],
            "whole_career_merged": [True, False],
        }
    ).to_parquet(tmp_path / "career_coverage.parquet", index=False)

    with pytest.raises(ValueError, match="asymmetric whole-career coverage"):
        _require_career_coverage(tmp_path, "majors")
    assert _require_career_coverage(tmp_path, "ufc")["symmetric"] is False


def test_legacy_page_only_audit_cannot_certify_a_majors_run(tmp_path):
    pd.DataFrame(
        {
            "fighter": ["Cached"],
            "ufc_bouts": [5],
            "corpus_bouts": [5],
            "pre_ufc_bouts": [0],
            "sherdog_id": ["1"],
            "career_page_read": [True],
        }
    ).to_parquet(tmp_path / "career_coverage.parquet", index=False)

    with pytest.raises(ValueError, match="predates the merged-row audit"):
        _require_career_coverage(tmp_path, "majors")
