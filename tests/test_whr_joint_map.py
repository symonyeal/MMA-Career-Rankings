"""Certify the joint posterior and independence of disconnected fight graphs."""
import numpy as np
import pandas as pd
import pytest

from ratings.whr import run_whr


def _fights(score):
    return pd.DataFrame({
        "fighter_a": ["A"] * 10, "fighter_b": [f"B{k}" for k in range(10)],
        "winner": ["A"] * 10, "is_draw": False, "method_score_winner": score,
        "event_date": pd.date_range("2020-01-01", periods=10, freq="90D"),
        "event_name": [f"E{k}" for k in range(10)],
    })


@pytest.mark.parametrize("score", [1.0, 0.9])
def test_whr_satisfies_joint_posterior_stationarity(score):
    """The Gaussian/virtual priors fix location; recentering violates stationarity."""
    f = _fights(score)
    h = run_whr(f, iterations=500, winner_score_col="method_score_winner")
    a = h[h.fighter.eq("A")].sort_values("event_date").mu_whr.to_numpy()
    b = h[~h.fighter.eq("A")].sort_values("event_date").mu_whr.to_numpy()
    x = (np.column_stack([a, b]).ravel() - 1500) * np.log(10) / 400
    c = np.tile([0.1, 1.0], 10)
    p = 1 / (1 + np.exp(-(x[::2] - x[1::2])))
    g = c * x / 8 + c * (1 / (1 + np.exp(-x)) - 0.5)
    g[::2] += p - score
    g[1::2] -= p - score
    d = np.diff(x[::2]) / (0.0004 * 90)
    g[:-2:2] -= d
    g[2::2] += d
    assert np.max(np.abs(g)) < 1e-7


def test_disconnected_fights_do_not_change_existing_whr_ratings():
    f = _fights(1.0)
    u = f.assign(fighter_a="C", fighter_b="D", winner=["C", "D"] * 5,
                 event_name=[f"F{k}" for k in range(10)])
    h = run_whr(f, iterations=100)
    q = run_whr(pd.concat([f, u], ignore_index=True), iterations=100)
    q = q[q.fighter.isin(h.fighter)].reset_index(drop=True)
    pd.testing.assert_frame_equal(h, q, check_exact=False, atol=1e-8, rtol=0)
