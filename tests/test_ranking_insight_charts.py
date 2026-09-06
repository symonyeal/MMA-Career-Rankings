"""Focused contracts for the notebook's ranking-explanation visual."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from analysis.viz import all_time_score_anatomy_chart
from ratings.legacy_resume import (
    LEGACY_ACHIEVEMENT_WEIGHT,
    LEGACY_QUALITY_SKILL_SHARE,
    PUBLIC_LEGACY_DISPLAY_SCALE,
)


def _fixture() -> pd.DataFrame:
    title = pd.Series([9.0, 6.0, 2.0, 4.0])
    skill = pd.Series([8.0, 12.0, 4.0, 7.0])
    resume = pd.Series([11.0, 8.0, 5.0, 6.0])

    def normalise(values: pd.Series) -> pd.Series:
        return values / values.mean()

    quality_weight = 1.0 - LEGACY_ACHIEVEMENT_WEIGHT
    score = PUBLIC_LEGACY_DISPLAY_SCALE * (
        LEGACY_ACHIEVEMENT_WEIGHT * normalise(title)
        + quality_weight * LEGACY_QUALITY_SKILL_SHARE * normalise(skill)
        + quality_weight * (1.0 - LEGACY_QUALITY_SKILL_SHARE) * normalise(resume)
    )
    return pd.DataFrame({
        "fighter": ["Alpha", "Bravo", "Charlie", "Delta"],
        "gender": ["M", "M", "M", "F"],
        "career_division": ["Lightweight", "Lightweight", "Welterweight", "Flyweight"],
        "rating_periods": [20, 18, 16, 17],
        "public_legacy_score": score,
        "public_legacy_title_score": title,
        "public_legacy_skill_score": skill,
        "public_legacy_resume_score": resume,
        "public_legacy_qualifying_title_wins": [7, 4, 1, 3],
        "symon_career_contributing_years": [10, 9, 7, 8],
        "public_legacy_contender_wins": [12, 9, 6, 8],
    })


def test_all_time_score_anatomy_reconstructs_the_published_total():
    current = _fixture()
    fig = all_time_score_anatomy_chart(current, n=3, gender="M")

    assert [trace.name for trace in fig.data[:3]] == [
        "Championships · 30%",
        "Career skill · 17.5%",
        "Contender résumé · 52.5%",
    ]
    stacked = np.sum(
        [np.asarray(trace.x, dtype=float) for trace in fig.data[:3]], axis=0
    )
    totals = np.asarray(fig.data[3].x, dtype=float)
    assert stacked == pytest.approx(totals)
    assert all(str(label).startswith("#") for label in fig.data[0].y)


def test_all_time_score_anatomy_honours_filters_and_separate_pools():
    current = _fixture()
    fig = all_time_score_anatomy_chart(
        current, n=10, gender="M", division="Lightweight", min_fights=19
    )
    assert list(fig.data[0].y) == ["#1  Alpha"]

    mixed = all_time_score_anatomy_chart(current, gender="both")
    assert not mixed.data
    assert "Choose Men or Women" in mixed.layout.annotations[0].text
