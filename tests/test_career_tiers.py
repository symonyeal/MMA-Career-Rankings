"""Tiers: what the board publishes when it cannot separate two fighters."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ratings.uncertainty import (
    UNRANKED_TIER_LABEL,
    career_mass_bootstrap,
    career_tiers,
    separation_probability,
    tier_summary,
)


def _draws(spec: dict[str, list[float]]) -> pd.DataFrame:
    return pd.DataFrame(spec).T


def _board(masses: dict[str, float]) -> pd.DataFrame:
    return pd.DataFrame({
        "fighter": list(masses),
        "mass": list(masses.values()),
        "mass_lo": [v * 0.5 for v in masses.values()],
        "mass_hi": [v * 1.5 for v in masses.values()],
        "rank": range(1, len(masses) + 1),
    })


def test_separation_is_paired_not_a_comparison_of_marginals():
    """Overlapping marginal intervals can still be a difference of one sign.

    Both careers are reweighted by the same events, so most of what moves them
    moves them together. Comparing marginal intervals throws that away.
    """
    draws = _draws({"A": [100.0, 200.0, 300.0], "B": [90.0, 190.0, 290.0]})
    # The marginals overlap almost completely -- A's range is 100-300, B's 90-290.
    assert draws.loc["A"].min() < draws.loc["B"].max()
    # Paired, A wins every replicate.
    assert separation_probability(draws, "A", "B") == 1.0
    assert separation_probability(draws, "B", "A") == 0.0
    assert np.isnan(separation_probability(draws, "A", "Nobody"))


def test_a_tier_means_nobody_in_it_is_separated_from_its_leader():
    board = _board({"A": 300.0, "B": 290.0, "C": 120.0, "D": 110.0})
    draws = _draws({
        "A": [300.0, 310.0, 305.0, 299.0],
        # B loses to A in half the replicates, so B is not separated from A.
        "B": [305.0, 300.0, 300.0, 280.0],
        # C loses to A every time -- a new tier opens, led by C.
        "C": [120.0, 118.0, 125.0, 121.0],
        # D beats C in half the replicates, so D is not separated from the new
        # leader and joins C's tier rather than opening a third.
        "D": [125.0, 110.0, 130.0, 115.0],
    })

    tiers = career_tiers(board, draws, confidence=0.95, unranked_at_or_below=None)
    by_fighter = tiers.set_index("fighter")

    assert by_fighter.loc["A", "tier"] == by_fighter.loc["B", "tier"] == 1
    assert by_fighter.loc["C", "tier"] == by_fighter.loc["D", "tier"] == 2
    assert by_fighter.loc["C", "tier_leader"] == "C"
    assert by_fighter.loc["D", "tier_leader"] == "C"
    assert by_fighter.loc["C", "p_below_tier_leader"] == 1.0


def test_the_rule_is_anchored_on_the_leader_not_on_neighbours():
    """Chaining pairwise overlaps would merge the whole board into one block.

    B is indistinguishable from A and C is indistinguishable from B, but C is
    separated from A. Anchoring on the leader keeps that a two-tier board;
    chaining would call it one.
    """
    board = _board({"A": 300.0, "B": 200.0, "C": 100.0})
    draws = _draws({
        "A": [300.0, 300.0, 300.0, 300.0],
        "B": [310.0, 290.0, 305.0, 295.0],
        "C": [105.0, 100.0, 95.0, 110.0],
    })

    tiers = career_tiers(board, draws, confidence=0.95, unranked_at_or_below=None)
    by_fighter = tiers.set_index("fighter")["tier"]

    assert by_fighter["A"] == by_fighter["B"] == 1
    assert by_fighter["C"] == 2


def test_the_score_floor_is_unranked_not_a_last_tier():
    board = _board({"A": 300.0, "B": 0.0, "C": 0.0})
    draws = _draws({"A": [300.0, 300.0], "B": [0.0, 0.0], "C": [0.0, 0.0]})

    tiers = career_tiers(board, draws, confidence=0.95, unranked_at_or_below=0.0)
    by_fighter = tiers.set_index("fighter")

    assert by_fighter.loc["A", "tier"] == 1
    for name in ("B", "C"):
        assert pd.isna(by_fighter.loc[name, "tier"])
        assert by_fighter.loc[name, "tier_label"] == UNRANKED_TIER_LABEL

    summary = tier_summary(tiers)
    assert summary.loc[summary["tier_label"].eq(UNRANKED_TIER_LABEL), "fighters"].iloc[0] == 2


def test_confidence_must_be_a_confidence():
    board = _board({"A": 1.0})
    draws = _draws({"A": [1.0]})
    for bad in (0.5, 1.0, 0.2):
        with pytest.raises(ValueError, match="confidence"):
            career_tiers(board, draws, confidence=bad)


def test_bootstrap_returns_draws_aligned_to_the_board():
    fights = pd.DataFrame([
        {"fighter_a": "A", "fighter_b": "B", "winner": "A", "is_draw": False,
         "event_date": pd.Timestamp(f"20{y:02d}-01-01"), "event_name": f"E{y}"}
        for y in range(10, 20)
    ] + [
        {"fighter_a": "C", "fighter_b": "B", "winner": "C", "is_draw": False,
         "event_date": pd.Timestamp(f"20{y:02d}-06-01"), "event_name": f"F{y}"}
        for y in range(10, 20)
    ])

    board, draws = career_mass_bootstrap(
        fights, replicates=4, seed=1, mass_kwargs={"reference": "mean"},
        return_draws=True,
    )

    assert list(draws.index) == board["fighter"].tolist()
    assert draws.shape[1] == 4
    # And the single-return form is unchanged for existing callers.
    only_board = career_mass_bootstrap(
        fights, replicates=4, seed=1, mass_kwargs={"reference": "mean"})
    pd.testing.assert_frame_equal(board, only_board)
