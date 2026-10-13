"""Compare run_whr with the MAP of its stated Bradley--Terry/Wiener model.

INPUT   none; A beats ten distinct one-bout opponents, 90 days apart.
OUTPUT  objective gradients, MAP gap, and effect of a disconnected career.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize

sys.path.insert(0, str(Path(__file__).parents[3]))
from ratings.whr import _ELO_PER_NAT, _build_appearances, run_whr


def fights(a, b, winners, prefix):
    return pd.DataFrame({
        "fighter_a": a, "fighter_b": b, "winner": winners, "is_draw": False,
        "event_date": pd.date_range("2020-01-01", periods=10, freq="90D"),
        "event_name": [f"{prefix}{k}" for k in range(10)],
    })


f = fights(["A"] * 10, [f"B{k}" for k in range(10)], ["A"] * 10, "E")
a, _, t, s, _, _, I = _build_appearances(f)
n = len(a)
c = np.array([1 / len(I[j]) for j in a])
i = np.arange(0, n, 2)


def fg(x):
    """Negative log posterior and gradient; prior_var=8, v=1, w2=0.0004."""
    d = x[i] - x[i + 1]
    p = 1 / (1 + np.exp(-d))
    z = (np.sum(np.logaddexp(0, d) - s[i] * d)
         + np.sum(c * x * x / 16 + c * (np.logaddexp(0, x) - x / 2)))
    g = c * x / 8 + c * (1 / (1 + np.exp(-x)) - .5)
    g[i] += p - s[i]
    g[i + 1] -= p - s[i]
    for J in I.values():
        J = np.array(J)
        if len(J) > 1:
            v = .0004 * np.maximum(np.diff(t[J]), 1)
            d = np.diff(x[J])
            z += np.sum(d * d / (2 * v))
            g[J[:-1]] -= d / v
            g[J[1:]] += d / v
    return z, g


def ordered_ratings(h):
    nodes = pd.DataFrame({
        "fighter": a,
        "event_date": pd.Timestamp("2000-01-01") + pd.to_timedelta(t, unit="D"),
        "node": np.arange(n),
    })
    h = h.merge(nodes, on=["fighter", "event_date"], validate="one_to_one")
    return (h.sort_values("node").mu_whr.to_numpy() - 1500) / _ELO_PER_NAT


h = run_whr(f, iterations=500)
x = ordered_ratings(h)
r = minimize(fg, np.zeros(n), jac=True, method="BFGS", options={"gtol": 1e-10})
f2 = fights(["C"] * 10, ["D"] * 10, ["C", "D"] * 5, "F")
h2 = run_whr(pd.concat([f, f2], ignore_index=True), iterations=500)
x2 = ordered_ratings(h2[h2.fighter.isin(a)])
print(json.dumps({
    "run_whr": {"objective": float(fg(x)[0]),
                "gradient_inf_norm": float(np.max(np.abs(fg(x)[1]))),
                "final_A": float(1500 + x[18] * _ELO_PER_NAT),
                "final_A_minus_B9": float((x[18] - x[19]) * _ELO_PER_NAT)},
    "exact_MAP": {"objective": float(r.fun),
                  "gradient_inf_norm": float(np.max(np.abs(r.jac))),
                  "final_A": float(1500 + r.x[18] * _ELO_PER_NAT),
                  "final_A_minus_B9": float((r.x[18] - r.x[19]) * _ELO_PER_NAT)},
    "disconnected_C_D_added": {
        "final_A": float(1500 + x2[18] * _ELO_PER_NAT),
        "final_A_minus_B9": float((x2[18] - x2[19]) * _ELO_PER_NAT)},
}, indent=2))
