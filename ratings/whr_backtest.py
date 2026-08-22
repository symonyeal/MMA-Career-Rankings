"""Offline calibration of the WHR drift prior ``WHR_W2_PER_DAY``.

This is a *model-selection* harness, not a user-facing prediction surface. WHR is
a whole-history smoother (it uses look-ahead), so to score a drift value honestly
we evaluate it **prequentially / rolling-origin**: for each held-out event we
re-fit WHR on the fights strictly *before* that event, take each fighter's latest
pre-fight rating, and score the one-step-ahead win probability against what
actually happened. No future information leaks into any prediction.

The drift prior ``w2_per_day`` controls how fast latent skill is allowed to move:
too small and the smoother is too rigid (stale ratings), too large and it chases
noise. We pick the value minimising mean log-loss / Brier over the evaluation
events.

Usage::

    python -m ratings.whr_backtest data/snapshots/2026-06-23 \
        --grid 0.0001,0.0002,0.0004,0.0008,0.0016 --events 25 --iterations 30

The chosen value is reported only; updating ``WHR_W2_PER_DAY`` in
``ratings/constants.py`` and recomputing the snapshot is a deliberate manual step.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from ratings.constants import WHR_ITERATIONS, WHR_W2_PER_DAY
from ratings.whr import _ELO_PER_NAT, run_whr


def elo_win_prob(mu_a: float, mu_b: float,
                 var_a: float = 0.0, var_b: float = 0.0, var_lambda: float = 0.0) -> float:
    """Bradley-Terry win probability for A on the WHR Elo-like display scale.

    ``mu = anchor + r * _ELO_PER_NAT`` (natural rating ``r``), so the natural
    rating gap is ``(mu_a - mu_b) / _ELO_PER_NAT`` and ``P(a) = sigmoid(gap)``.

    With ``var_lambda > 0`` the gap is attenuated by the combined WHR posterior
    variance (natural scale): ``gap / sqrt(1 + var_lambda * (var_a + var_b))``.
    This is the WHR-native analog of Glicko-2's ``g(RD)`` shrinkage — uncertain
    ratings (thin or stale records) pull the prediction toward a coin flip,
    sourced from the smoother's own Hessian rather than a foreign filter.
    """
    gap = (float(mu_a) - float(mu_b)) / _ELO_PER_NAT
    if var_lambda:
        gap = gap / np.sqrt(1.0 + var_lambda * (float(var_a) + float(var_b)))
    return 1.0 / (1.0 + np.exp(-gap))


def _decided_bouts(fights: pd.DataFrame) -> pd.DataFrame:
    """One row per decided (non-draw / non-NC) bout with a clean winner/loser."""
    f = fights.copy()
    if "is_excluded" in f.columns:
        f = f[~f["is_excluded"].fillna(False).astype(bool)]
    for flag in ("is_draw", "is_nc"):
        if flag in f.columns:
            f = f[~f[flag].fillna(False).astype(bool)]
    f = f.dropna(subset=["winner", "fighter_a", "fighter_b"])
    f["event_date"] = pd.to_datetime(f["event_date"], errors="coerce")
    f = f.dropna(subset=["event_date"])
    # Keep only bouts whose winner is one of the two named fighters.
    f = f[f["winner"].eq(f["fighter_a"]) | f["winner"].eq(f["fighter_b"])]
    f["_y_a"] = (f["winner"] == f["fighter_a"]).astype(int)  # 1 if fighter_a won
    return f


def backtest_w2(
    fights: pd.DataFrame,
    w2_grid: list[float],
    *,
    var_lambdas: list[float] | None = None,
    n_eval_events: int = 25,
    iterations: int = WHR_ITERATIONS,
    min_prior_fights: int = 3,
    eps: float = 1e-6,
) -> pd.DataFrame:
    """Rolling-origin one-step-ahead scoring over a ``(w2, var_lambda)`` grid.

    For each of the most recent ``n_eval_events`` events, WHR is re-fit on every
    fight strictly before the event date; each fighter's last pre-fight rating
    (and posterior variance) predicts that event's bouts. Because ``var_lambda``
    only rescales the prediction, every lambda is scored from the same fit — one
    WHR solve per ``(w2, event)``. Returns a frame ``w2, var_lambda, brier,
    log_loss, n`` sorted by ``log_loss`` ascending (best first). Only bouts where
    both fighters have >= ``min_prior_fights`` prior appearances are scored.
    """
    lambdas = list(var_lambdas) if var_lambdas else [0.0]
    need_var = any(value > 0 for value in lambdas)
    bouts = _decided_bouts(fights)
    cols = ["w2", "var_lambda", "brier", "log_loss", "n"]
    if bouts.empty:
        return pd.DataFrame(columns=cols)

    events = (
        bouts[["event_date", "event_name"]]
        .drop_duplicates()
        .sort_values("event_date")
    )
    eval_events = events.tail(n_eval_events)

    appearances = pd.concat([
        bouts[["event_date", "fighter_a"]].rename(columns={"fighter_a": "fighter"}),
        bouts[["event_date", "fighter_b"]].rename(columns={"fighter_b": "fighter"}),
    ], ignore_index=True)

    rows = []
    for w2 in w2_grid:
        # (w2, lambda) -> [sq_err_sum, log_loss_sum, n]
        acc = {lam: [0.0, 0.0, 0] for lam in lambdas}
        for _, ev in eval_events.iterrows():
            d = ev["event_date"]
            train = bouts[bouts["event_date"] < d]
            if train.empty:
                continue
            hist = run_whr(train, w2_per_day=float(w2), iterations=iterations,
                           return_variance=need_var)
            if hist.empty:
                continue
            last = hist.sort_values(["fighter", "event_date"]).groupby("fighter").last()
            mu_map = last["mu_whr"]
            var_map = last["var_whr"] if need_var and "var_whr" in last.columns else None
            prior_counts = appearances[appearances["event_date"] < d].groupby("fighter").size()
            ev_bouts = bouts[(bouts["event_date"] == d) & (bouts["event_name"] == ev["event_name"])]
            for _, b in ev_bouts.iterrows():
                a, c = b["fighter_a"], b["fighter_b"]
                if a not in mu_map.index or c not in mu_map.index:
                    continue
                if prior_counts.get(a, 0) < min_prior_fights or prior_counts.get(c, 0) < min_prior_fights:
                    continue
                va = float(var_map[a]) if var_map is not None else 0.0
                vc = float(var_map[c]) if var_map is not None else 0.0
                y = int(b["_y_a"])
                for lam in lambdas:
                    p = float(np.clip(elo_win_prob(mu_map[a], mu_map[c], va, vc, lam), eps, 1 - eps))
                    acc[lam][0] += (p - y) ** 2
                    acc[lam][1] += -(y * np.log(p) + (1 - y) * np.log(1 - p))
                    acc[lam][2] += 1
        for lam, (sq, ll, n) in acc.items():
            rows.append({
                "w2": float(w2), "var_lambda": float(lam),
                "brier": sq / n if n else float("nan"),
                "log_loss": ll / n if n else float("nan"),
                "n": n,
            })
    return pd.DataFrame(rows).sort_values("log_loss").reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Calibrate WHR_W2_PER_DAY by rolling-origin backtest.")
    parser.add_argument("snapshot_dir", type=Path, help="Snapshot directory with canonical_fights.parquet.")
    parser.add_argument("--grid", default="0.0001,0.0002,0.0004,0.0008,0.0016",
                        help="Comma-separated w2_per_day values to score.")
    parser.add_argument("--var-lambdas", default="0,0.5,1,2",
                        help="Comma-separated Hessian-variance attenuation strengths to score (0 = off).")
    parser.add_argument("--events", type=int, default=25, help="Number of most-recent events to evaluate.")
    parser.add_argument("--iterations", type=int, default=WHR_ITERATIONS, help="WHR coordinate-ascent passes per fit.")
    parser.add_argument("--min-prior-fights", type=int, default=3, help="Min prior appearances per fighter to score a bout.")
    args = parser.parse_args()

    fights = pd.read_parquet(args.snapshot_dir / "canonical_fights.parquet")
    grid = [float(x) for x in args.grid.split(",") if x.strip()]
    lambdas = [float(x) for x in args.var_lambdas.split(",") if x.strip()]
    result = backtest_w2(
        fights, grid, var_lambdas=lambdas, n_eval_events=args.events,
        iterations=args.iterations, min_prior_fights=args.min_prior_fights,
    )
    pd.set_option("display.width", 120)
    print(result.to_string(index=False))
    if not result.empty and result["n"].iloc[0] > 0:
        best = result.iloc[0]
        cur = WHR_W2_PER_DAY
        print(f"\nbest: w2_per_day = {best['w2']:.5g}, var_lambda = {best['var_lambda']:.3g} "
              f"(log_loss={best['log_loss']:.4f}, brier={best['brier']:.4f}, n={int(best['n'])})")
        print(f"current constant WHR_W2_PER_DAY = {cur:.5g}")
        if abs(best["w2"] - cur) > 1e-12:
            print("-> consider updating ratings/constants.py and recomputing the snapshot.")
        else:
            print("-> current w2 is already optimal on this grid.")


if __name__ == "__main__":
    main()
