"""Whole-History Rating smoother (ratings/whr.py)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from ratings.whr import _thomas, run_whr


def _chain_fights(n_events: int = 15) -> pd.DataFrame:
    """A always beats B, B always beats C, repeated over many events."""
    base = pd.Timestamp("2015-01-01")
    rows = []
    for i in range(n_events):
        d = base + pd.Timedelta(days=120 * i)
        rows.append(dict(fighter_a="A", fighter_b="B", winner="A", is_draw=False,
                         event_date=d, event_name=f"E{i}a"))
        rows.append(dict(fighter_a="B", fighter_b="C", winner="B", is_draw=False,
                         event_date=d, event_name=f"E{i}b"))
    return pd.DataFrame(rows)


def test_thomas_solves_tridiagonal_system():
    # A symmetric tridiagonal system with a known solution.
    diag = np.array([2.0, 3.0, 2.0])
    off = np.array([1.0, 1.0])
    x_true = np.array([1.0, -1.0, 2.0])
    # rhs = A @ x_true
    rhs = np.array([
        diag[0] * x_true[0] + off[0] * x_true[1],
        off[0] * x_true[0] + diag[1] * x_true[1] + off[1] * x_true[2],
        off[1] * x_true[1] + diag[2] * x_true[2],
    ])
    x = _thomas(diag, off, rhs)
    assert np.allclose(x, x_true, atol=1e-9)


def test_whr_recovers_monotonic_ordering():
    hist = run_whr(_chain_fights(), iterations=60)
    last = hist.sort_values("event_date").groupby("fighter")["mu_whr"].last()
    assert last["A"] > last["B"] > last["C"]


def test_whr_history_shape_matches_rating_history_contract():
    hist = run_whr(_chain_fights())
    assert list(hist.columns) == ["fighter", "event_date", "event_name", "mu_whr"]
    # one row per fighter-appearance: 2 fighters per bout, 30 bouts.
    assert len(hist) == 60
    assert hist["mu_whr"].notna().all()


def test_whr_smoother_is_stable_across_late_career():
    """A dominant fighter's rating should plateau, not drift, once established."""
    hist = run_whr(_chain_fights(20), iterations=60)
    a_traj = hist[hist["fighter"] == "A"].sort_values("event_date")["mu_whr"].to_numpy()
    # last third of the career should be near-flat
    tail = a_traj[len(a_traj) // 3:]
    assert tail.std() < 5.0


def test_whr_empty_input_returns_empty_frame():
    out = run_whr(pd.DataFrame())
    assert list(out.columns) == ["fighter", "event_date", "event_name", "mu_whr"]
    assert out.empty
