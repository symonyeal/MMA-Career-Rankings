"""The Rust WHR backend must return the numpy solver's ratings bit for bit.

``whr_rs`` repeats the numpy passes operation for operation, including numpy's
pairwise summation for the per-pass mean. A tolerance would let a reordered sum
or a fused multiply-add slip in and move a board by one place, so the check is
exact equality. CI builds the extension and sets ``WHR_RS_REQUIRED=1`` so a
missing build fails rather than skips.
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd
import pytest

from ratings.whr import run_whr

if os.environ.get("WHR_RS_REQUIRED") == "1":
    import whr_rs  # noqa: F401
else:
    pytest.importorskip("whr_rs")


def _fights(n: int = 4000, m: int = 600, seed: int = 7) -> tuple[pd.DataFrame, dict[str, pd.Timestamp]]:
    g = np.random.default_rng(seed)
    q = g.normal(0.0, 1.0, m)
    a = g.integers(0, m, n)
    b = (a + g.integers(1, m, n)) % m
    p = 1.0 / (1.0 + np.exp(-(q[a] - q[b])))
    u = g.random(n)
    win = np.where(u < p, a, b)
    draw = g.random(n) < 0.02
    days = np.sort(g.integers(0, 9000, n))
    f = pd.DataFrame({
        "fighter_a": [f"F{i}" for i in a],
        "fighter_b": [f"F{i}" for i in b],
        "winner": [f"F{i}" for i in win],
        "is_draw": draw,
        "event_date": pd.Timestamp("1995-01-01") + pd.to_timedelta(days, unit="D"),
        "event_name": [f"E{d}" for d in days],
        "method_score_winner": g.choice([1.0, 0.95, 0.9, 0.85], n),
        "weight_a": np.repeat(g.choice([1.0, 0.6, 0.88], n // 4), 4)[:n],
    })
    f["weight_b"] = f["weight_a"]
    dob = {f"F{i}": pd.Timestamp("1970-01-01") + pd.Timedelta(days=int(d))
           for i, d in enumerate(g.integers(0, 9000, m)) if i % 5}
    return f, dob


@pytest.mark.parametrize("age_drift", [False, True])
@pytest.mark.parametrize("center", [True, False])
def test_rust_backend_is_bit_identical(age_drift, center):
    f, dob = _fights()
    kw = {"winner_score_col": "method_score_winner", "center_each_pass": center, "iterations": 20,
          "birth_dates": dob if age_drift else None, "age_drift": age_drift, "return_variance": True}
    py = run_whr(f, backend="python", **kw)
    rs = run_whr(f, backend="rust", **kw)
    pd.testing.assert_frame_equal(py, rs, check_exact=True)
    if age_drift:
        assert py.attrs["age_drift_elo_per_year"] == rs.attrs["age_drift_elo_per_year"]


def test_unknown_backend_is_refused():
    f, _ = _fights(n=40, m=10)
    with pytest.raises(ValueError, match="unknown WHR backend"):
        run_whr(f, backend="fortran")
