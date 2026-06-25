"""Tests for the WHR (Legacy) dominance likelihood-weight reward."""
import numpy as np
import pandas as pd
import pytest

from ratings.rate_snapshot import _amplify_dominance_weight, _winner_dominance_level


def test_winner_dominance_level_maps_to_unit_interval():
    perf = pd.DataFrame({
        "fight_url": ["f1", "f1", "f2", "f2", "f3", "f3"],
        "dominance_score_winner": [8.0, 8.0, 0.0, 0.0, -5.0, -5.0],  # dominant / neutral / (winner not dominant)
    })
    lvl = _winner_dominance_level(perf)
    assert lvl["f1"] > 0.8        # lopsided win -> near 1
    assert lvl["f2"] == pytest.approx(0.0)   # neutral -> 0
    assert lvl["f3"] == pytest.approx(0.0)   # negative folds to 0 (positive-only)


def test_amplify_scales_both_sides():
    # Two-sided: a dominant bout is stronger evidence for the winner AND against
    # the blown-out loser, so both per-fight weights scale by 1 + amp*level.
    weighted = pd.DataFrame({
        "fight_url": ["f1"],
        "fighter_a": ["A"], "fighter_b": ["B"], "winner": ["A"],
        "weight_a": [1.0], "weight_b": [1.0],
    })
    out = _amplify_dominance_weight(weighted, {"f1": 1.0}, amplitude=0.30)
    assert out.loc[0, "weight_a"] == pytest.approx(1.30)   # winner boosted
    assert out.loc[0, "weight_b"] == pytest.approx(1.30)   # loser pushed down harder too


def test_amplify_partial_level_and_preexisting_weight():
    # Factor folds onto whatever sleeve/org weight is already present.
    weighted = pd.DataFrame({
        "fight_url": ["f1"],
        "fighter_a": ["A"], "fighter_b": ["B"], "winner": ["A"],
        "weight_a": [0.9], "weight_b": [1.1],
    })
    out = _amplify_dominance_weight(weighted, {"f1": 0.5}, amplitude=0.30)
    assert out.loc[0, "weight_a"] == pytest.approx(0.9 * 1.15)
    assert out.loc[0, "weight_b"] == pytest.approx(1.1 * 1.15)


def test_amplify_noop_when_disabled_or_empty():
    weighted = pd.DataFrame({
        "fight_url": ["f1"], "fighter_a": ["A"], "fighter_b": ["B"],
        "winner": ["A"], "weight_a": [1.0], "weight_b": [1.0],
    })
    assert _amplify_dominance_weight(weighted, {"f1": 1.0}, 0.0).equals(weighted)
    assert _amplify_dominance_weight(weighted, {}, 0.30).equals(weighted)
