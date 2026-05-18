"""Glickman 2013 worked example — the canonical Glicko-2 sanity check.

A player at μ=1500, φ=200, σ=0.06 plays three opponents with the following
ratings & outcomes (τ=0.5):

   opponent      μ     φ     outcome
   1            1400  30     W
   2            1550  100    L
   3            1700  300    L

Post-rating-period result per the paper: μ ≈ 1464.05, φ ≈ 151.52, σ ≈ 0.05999.
"""
from ratings._glicko2 import Glicko2, WIN, LOSS


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
