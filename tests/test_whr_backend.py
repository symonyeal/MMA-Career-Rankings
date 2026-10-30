"""Rust-only fitting checked against results captured at 5f53271."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

from ratings.whr import run_whr

CAPTURE = json.loads((Path(__file__).parent / "fixtures/rating_results.json").read_text())


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


@pytest.mark.parametrize("case", CAPTURE["whr"])
def test_rust_fit_matches_captured_weighted_ratings_and_variances(case):
    f, dob = _fights(n=40, m=10)
    actual = run_whr(f, winner_score_col="method_score_winner", center_each_pass=case["center"],
                     iterations=20, birth_dates=dob if case["age"] else None,
                     age_drift=case["age"], return_variance=True)
    np.testing.assert_allclose(actual.mu_whr, case["mu"], rtol=1e-13)
    np.testing.assert_allclose(actual.var_whr, case["variance"], rtol=1e-12)
    if case["age"]:
        np.testing.assert_allclose(actual.attrs["age_drift_elo_per_year"], case["drift"], atol=1e-12)


@pytest.mark.parametrize("extension, module", [("whr_rs", "ratings.whr"), ("rating_rs", "ratings._glicko2")])
def test_missing_native_extension_fails_without_fallback(extension, module):
    source = f"import sys; sys.modules[{extension!r}] = None; __import__({module!r})"
    result = subprocess.run([sys.executable, "-c", source], capture_output=True, text=True, check=False)
    assert result.returncode != 0
    assert "ModuleNotFoundError" in result.stderr and extension in result.stderr
