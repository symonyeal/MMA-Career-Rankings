"""Probability scores and calibration, independent of folds and rating engines."""
from __future__ import annotations

import numpy as np
import pandas as pd

EPS = 1e-6


def losses(p: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Per-observation log loss and Brier score, with the published probability clip."""
    p = np.clip(p, EPS, 1 - EPS)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p)), (p - y) ** 2


def roc_auc(p: np.ndarray, y: np.ndarray) -> float:
    """Rank-based discrimination, invariant to any monotone rescaling of ``p``.

    This is the metric that answers "does this mechanism add *information*",
    separately from whether the probability scale is right — temperature
    scaling cannot move it, so a mechanism that only fixes calibration shows up
    in log-loss and not here.
    """
    y = np.asarray(y, dtype=float)
    pos, neg = y == 1, y == 0
    if not pos.any() or not neg.any():
        return float("nan")
    order = np.argsort(p, kind="stable")
    ranks = np.empty(len(p), dtype=float)
    ranks[order] = np.arange(1, len(p) + 1, dtype=float)
    # Mid-ranks for ties, so a constant predictor scores exactly 0.5.
    sp = p[order]
    i = 0
    while i < len(sp):
        j = i
        while j + 1 < len(sp) and sp[j + 1] == sp[i]:
            j += 1
        if j > i:
            ranks[order[i:j + 1]] = (i + 1 + j + 1) / 2.0
        i = j + 1
    n_pos, n_neg = int(pos.sum()), int(neg.sum())
    return float((ranks[pos].sum() - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg))



def metrics(p: np.ndarray, y: np.ndarray) -> dict:
    p = np.clip(p, EPS, 1 - EPS)
    ll, br = losses(p, y)
    return {
        "log_loss": float(np.mean(ll)),
        "brier": float(np.mean(br)),
        "accuracy": float(np.mean((p >= 0.5) == (y == 1))),
        "auc": roc_auc(p, y),
        "n": len(p),
    }



def fit_temperature(p: np.ndarray, y: np.ndarray) -> float:
    """Scalar temperature ``T`` minimising log-loss for ``sigmoid(logit(p) / T)``.

    Every variant here shares a badly overconfident probability scale — the
    engine's stored ``calibration_residuals`` shows the same thing — so raw
    log-loss mostly measures that shared defect rather than the mechanism under
    test. Fitting one parameter on data that strictly precedes the held-out
    events removes it without leaking anything.
    """
    p = np.clip(np.asarray(p, dtype=float), EPS, 1 - EPS)
    y = np.asarray(y, dtype=float)
    logit = np.log(p / (1 - p))
    if len(logit) < 50 or not np.isfinite(logit).all():
        return 1.0

    def loss(t: float) -> float:
        q = np.clip(1.0 / (1.0 + np.exp(-logit / t)), EPS, 1 - EPS)
        return float(np.mean(-(y * np.log(q) + (1 - y) * np.log(1 - q))))

    # Unimodal in T over this range; a golden-section search is enough and
    # avoids a scipy dependency.
    lo, hi = 0.25, 12.0
    phi = (np.sqrt(5.0) - 1.0) / 2.0
    a, b = lo, hi
    c, d = b - phi * (b - a), a + phi * (b - a)
    for _ in range(60):
        if loss(c) < loss(d):
            b, d = d, c
            c = b - phi * (b - a)
        else:
            a, c = c, d
            d = a + phi * (b - a)
    return float((a + b) / 2.0)



def apply_temperature(p: np.ndarray, temperature: float) -> np.ndarray:
    p = np.clip(np.asarray(p, dtype=float), EPS, 1 - EPS)
    logit = np.log(p / (1 - p))
    return 1.0 / (1.0 + np.exp(-logit / float(temperature)))



def calibration_curve(p: np.ndarray, y: np.ndarray, *, n_bins: int = 10) -> pd.DataFrame:
    """Reliability table in ``calibration_residuals.parquet`` conventions."""
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    idx = np.clip(np.digitize(p, bins[1:-1], right=False), 0, n_bins - 1)
    rows = []
    for b in range(n_bins):
        m = idx == b
        if not m.any():
            continue
        rows.append({
            "prob_bin": b,
            "predicted_mean": float(p[m].mean()),
            "empirical_win_rate": float(y[m].mean()),
            "residual": float(y[m].mean() - p[m].mean()),
            "brier": float(((p[m] - y[m]) ** 2).mean()),
            "n": int(m.sum()),
        })
    return pd.DataFrame(rows)



def calibration_error(p: np.ndarray, y: np.ndarray, *, n_bins: int = 10) -> float:
    """Sample-weighted mean |empirical - predicted| over the reliability bins (ECE)."""
    curve = calibration_curve(p, y, n_bins=n_bins)
    if curve.empty:
        return float("nan")
    w = curve["n"].to_numpy(dtype=float)
    return float(np.sum(w * curve["residual"].abs().to_numpy()) / w.sum())
