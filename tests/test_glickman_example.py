"""Glickman 2013 worked example — the canonical Glicko-2 sanity check.

A player at μ=1500, φ=200, σ=0.06 plays three opponents with the following
ratings & outcomes (τ=0.5):

   opponent      μ     φ     outcome
   1            1400  30     W
   2            1550  100    L
   3            1700  300    L

Post-rating-period result per the paper: μ ≈ 1464.05, φ ≈ 151.52, σ ≈ 0.05999.
"""
import pytest

from ratings._glicko2 import Glicko2, WIN, LOSS
from ratings.glicko2_engine import predict_win_prob_from_ratings


def test_glickman_paper_example():
    env = Glicko2(tau=0.5)
    p = env.create_rating(1500, 200, 0.06)
    o1 = env.create_rating(1400, 30)
    o2 = env.create_rating(1550, 100)
    o3 = env.create_rating(1700, 300)

    rated = env.rate(p, [(WIN, o1), (LOSS, o2), (LOSS, o3)])

    assert round(rated.mu, 2) == 1464.05, f"μ mismatch: {rated.mu}"
    assert round(rated.phi, 2) == 151.52, f"φ mismatch: {rated.phi}"
    # Paper's published σ is 0.05999 (truncation). Actual is 0.0599959... which
    # round-to-5-places gives 0.06000; assert closeness instead of round-equality.
    assert abs(rated.sigma - 0.05999) < 1e-4, f"σ mismatch: {rated.sigma}"


def test_match_prediction_is_reciprocal_with_unequal_uncertainty():
    """Swapping the two fighters must complement, not change, the forecast."""
    p_ab = predict_win_prob_from_ratings(1700.0, 50.0, 1500.0, 350.0)
    p_ba = predict_win_prob_from_ratings(1500.0, 350.0, 1700.0, 50.0)

    assert p_ab + p_ba == pytest.approx(1.0, abs=1e-14)
    assert predict_win_prob_from_ratings(1500.0, 40.0, 1500.0, 300.0) == pytest.approx(0.5)


def test_joint_uncertainty_moves_prediction_toward_even_money():
    certain = predict_win_prob_from_ratings(1700.0, 50.0, 1500.0, 50.0)
    uncertain = predict_win_prob_from_ratings(1700.0, 350.0, 1500.0, 350.0)

    assert 0.5 < uncertain < certain < 1.0
