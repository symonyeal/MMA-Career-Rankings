"""The ranked window is a share of the division, not a fixed fifteen.

A rank is a position in a field. This corpus pools every promotion into one
division, so the fields differ by a factor of three and a fixed top-15 window
says something different in each of them -- 40% of women's strawweight against
13% of featherweight. See the note above ``RANK_CONTEXT_TOP_SHARE``.
"""
from __future__ import annotations

import pandas as pd
import pytest

from ratings.constants import (
    RANK_CONTEXT_MIN_WINDOW,
    RANK_CONTEXT_TOP_N,
    RANK_CONTEXT_TOP_SHARE,
)
from ratings.opponent_quality import rank_context_quality_level


def _level(ranks, pool=None):
    return rank_context_quality_level(
        pd.Series(ranks, dtype="float64"),
        None,
        None,
        None if pool is None else pd.Series(pool, dtype="float64"),
    )


def test_no_pool_reproduces_the_fixed_window():
    ranks = [1.0, 8.0, 15.0, 16.0, 40.0]
    fixed = _level(ranks)
    assert fixed.iloc[0] == pytest.approx(1.0)
    assert fixed.iloc[2] == pytest.approx(1.0 / RANK_CONTEXT_TOP_N)
    assert fixed.iloc[3] == 0.0
    assert fixed.iloc[4] == 0.0


def test_the_same_share_of_two_different_fields_scores_the_same():
    """The defect in one assertion: #8 of 37 and #24 of 119 are the same claim."""
    small_pool, large_pool = 37.0, 119.0
    small_rank = round(RANK_CONTEXT_TOP_SHARE * small_pool)   # 7
    large_rank = round(RANK_CONTEXT_TOP_SHARE * large_pool)   # 24 -> capped at 15

    # Under the fixed window the small-division fighter is credited and the
    # large-division fighter is not, for the identical positional achievement.
    fixed = _level([small_rank, large_rank])
    assert fixed.iloc[0] > 0.0
    assert fixed.iloc[1] == 0.0

    # Scaled to the field, the top of each field scores alike.
    scaled = _level([1.0, 1.0], [small_pool, large_pool])
    assert scaled.iloc[0] == pytest.approx(scaled.iloc[1])

    # And so does the bottom of each ranked window.
    edge = _level(
        [round(RANK_CONTEXT_TOP_SHARE * small_pool), RANK_CONTEXT_TOP_N],
        [small_pool, large_pool],
    )
    assert edge.iloc[0] > 0.0
    assert edge.iloc[1] > 0.0


def test_window_never_exceeds_the_fixed_convention_or_falls_below_the_floor():
    # A very large pooled field would otherwise stretch the window past the
    # sport's own top-15 convention.
    huge = _level([RANK_CONTEXT_TOP_N + 1.0], [1000.0])
    assert huge.iloc[0] == 0.0

    # A tiny field still has a top few rather than a top zero.
    tiny = _level([float(RANK_CONTEXT_MIN_WINDOW)], [6.0])
    assert tiny.iloc[0] > 0.0
    assert _level([RANK_CONTEXT_MIN_WINDOW + 1.0], [6.0]).iloc[0] == 0.0


def test_an_unknown_pool_falls_back_to_the_fixed_window():
    unknown = _level([15.0, 16.0], [float("nan"), float("nan")])
    assert unknown.iloc[0] == pytest.approx(1.0 / RANK_CONTEXT_TOP_N)
    assert unknown.iloc[1] == 0.0


def test_champion_signal_still_dominates_any_window():
    level = rank_context_quality_level(
        pd.Series([40.0]), pd.Series([True]), pd.Series([False]), pd.Series([119.0])
    )
    assert level.iloc[0] == pytest.approx(1.0)
