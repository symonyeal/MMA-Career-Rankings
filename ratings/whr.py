"""Whole-History Rating (WHR) — a Bayesian smoother sidecar to the Glicko-2 filter.

Reference: Rémi Coulom (2008), "Whole-History Rating: A Bayesian Rating System
for Players of Time-Varying Strength."

Why this exists
---------------
The production canonical engine is Glicko-2, a *filter*: information flows one
direction (past -> future), so a fighter who debuts in an inflated modern pool
and one who debuted in a compressed early pool are not directly comparable.
WHR is a *smoother*: it computes the joint MAP estimate of every fighter's
whole rating history at once, propagating information both directions, so
ratings are comparable across distant time by construction. ``ratings/peaks.py``
era-normalization is a post-hoc patch for the filtering artifact; WHR addresses
it at the rating layer.

Model
-----
* Dynamic Bradley-Terry likelihood. Each fighter has a latent rating ``r`` at
  each appearance (natural/logistic scale). For a bout the fighter's score
  ``s in {1, 0.5, 0}`` has expected value ``P = sigma(r - r_opp)``.
* Wiener-process prior between a fighter's consecutive appearances: the rating
  change over ``dt`` days is ``N(0, w2_per_day * dt)``.
* A weak Gaussian anchor prior ``r ~ N(0, prior_var)`` pins the global scale
  and regularizes.

Inference
---------
Coordinate ascent: holding all opponents' ratings fixed, each fighter's rating
vector is a concave problem whose Hessian is tridiagonal (temporal-neighbour
coupling from the Wiener prior + per-appearance BT curvature). One Newton step
per fighter per pass, solved in O(k) by the Thomas algorithm; iterate over all
fighters for a fixed number of passes.

The output ``mu_whr`` is mapped to a familiar Elo-like scale
(``1500 + r * 400/ln(10)``) so it slots into the same downstream machinery as
``mu_canonical``. ``w2_per_day`` should ultimately be chosen by predictive
backtest (Brier / log-loss); the default is a reasonable MMA prior.
"""
from __future__ import annotations

from collections import defaultdict

import numpy as np
import pandas as pd

from ratings.constants import (
    WHR_ITERATIONS,
    WHR_PRIOR_VAR,
    WHR_STEP_CLIP,
    WHR_W2_PER_DAY,
)

# Natural-scale rating -> Elo-like display scale.
_ELO_PER_NAT = 400.0 / np.log(10.0)
_ELO_ANCHOR = 1500.0
_EPOCH = pd.Timestamp("2000-01-01")


def _thomas(diag: np.ndarray, off: np.ndarray, rhs: np.ndarray) -> np.ndarray:
    """Solve a symmetric tridiagonal system ``A x = rhs`` in O(n).

    ``diag`` is the main diagonal (length n); ``off`` is the off-diagonal
    (length n-1, used as both sub- and super-diagonal).
    """
    n = len(diag)
    if n == 1:
        return rhs / diag if diag[0] != 0.0 else np.zeros(1)
    c = np.zeros(n - 1)
    d = np.zeros(n)
    beta = diag[0]
    c[0] = off[0] / beta
    d[0] = rhs[0] / beta
    for i in range(1, n - 1):
        beta = diag[i] - off[i - 1] * c[i - 1]
        c[i] = off[i] / beta
        d[i] = (rhs[i] - off[i - 1] * d[i - 1]) / beta
    beta = diag[n - 1] - off[n - 2] * c[n - 2]
    d[n - 1] = (rhs[n - 1] - off[n - 2] * d[n - 2]) / beta
    x = np.zeros(n)
    x[n - 1] = d[n - 1]
    for i in range(n - 2, -1, -1):
        x[i] = d[i] - c[i] * x[i + 1]
    return x


def _build_appearances(
    fights: pd.DataFrame,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict[str, list[int]]]:
    """Explode bouts into appearance nodes.

    Returns ``(app_fighter, app_event, app_day, app_score, app_opp, app_weight, by_fighter)``
    where appearance ``2i`` is fighter_a of bout ``i`` and ``2i+1`` is
    fighter_b. ``app_opp`` maps each node to its bout-paired node.
    ``app_weight`` is the per-node likelihood sleeve weight (1.0 if the fights
    table has no ``weight_a``/``weight_b`` columns). ``by_fighter`` maps a
    fighter to their node ids in chronological order.
    """
    f = fights.copy()
    f["event_date"] = pd.to_datetime(f["event_date"], errors="coerce")
    f = f.dropna(subset=["event_date", "fighter_a", "fighter_b"])
    f = f.sort_values(["event_date", "event_name"]).reset_index(drop=True)

    n = len(f)
    app_fighter = np.empty(2 * n, dtype=object)
    app_event = np.empty(2 * n, dtype=object)
    app_day = np.zeros(2 * n, dtype=float)
    app_score = np.zeros(2 * n, dtype=float)
    app_opp = np.zeros(2 * n, dtype=np.int64)
    app_weight = np.ones(2 * n, dtype=float)

    fighter_a = f["fighter_a"].to_numpy()
    fighter_b = f["fighter_b"].to_numpy()
    winner = f["winner"].to_numpy() if "winner" in f.columns else np.full(n, None)
    is_draw = (
        f["is_draw"].fillna(False).to_numpy()
        if "is_draw" in f.columns
        else np.zeros(n, dtype=bool)
    )
    event_name = f["event_name"].to_numpy() if "event_name" in f.columns else np.full(n, "")
    days = ((f["event_date"] - _EPOCH).dt.days).to_numpy(dtype=float)
    weight_a_arr = f["weight_a"].to_numpy(dtype=float) if "weight_a" in f.columns else np.ones(n, dtype=float)
    weight_b_arr = f["weight_b"].to_numpy(dtype=float) if "weight_b" in f.columns else np.ones(n, dtype=float)
    # Optional per-bout winner-score override. When the canonical fight table
    # carries quality_score_winner (which already folds in the integrity score
    # damp from performance_adjustment.quality_score_winner), the WHR
    # likelihood reads the same downgraded outcome a Glicko-2 method/sleeve
    # stream sees. Falls back to {0, 1} when the column is absent.
    if "quality_score_winner" in f.columns:
        winner_score_arr = pd.to_numeric(f["quality_score_winner"], errors="coerce").to_numpy(dtype=float)
    else:
        winner_score_arr = np.full(n, np.nan, dtype=float)

    for i in range(n):
        na, nb = 2 * i, 2 * i + 1
        app_fighter[na] = fighter_a[i]
        app_fighter[nb] = fighter_b[i]
        app_event[na] = event_name[i]
        app_event[nb] = event_name[i]
        app_day[na] = days[i]
        app_day[nb] = days[i]
        app_opp[na] = nb
        app_opp[nb] = na
        app_weight[na] = weight_a_arr[i]
        app_weight[nb] = weight_b_arr[i]
        if bool(is_draw[i]):
            app_score[na] = app_score[nb] = 0.5
        elif winner[i] == fighter_a[i]:
            s_win = winner_score_arr[i] if not np.isnan(winner_score_arr[i]) else 1.0
            app_score[na] = float(s_win)
            app_score[nb] = float(1.0 - s_win)
        elif winner[i] == fighter_b[i]:
            s_win = winner_score_arr[i] if not np.isnan(winner_score_arr[i]) else 1.0
            app_score[na] = float(1.0 - s_win)
            app_score[nb] = float(s_win)
        else:  # no recorded winner (treated as a draw for rating purposes)
            app_score[na] = app_score[nb] = 0.5

    by_fighter: dict[str, list[int]] = defaultdict(list)
    for node in range(2 * n):  # appended in chronological bout order -> sorted
        by_fighter[app_fighter[node]].append(node)

    return app_fighter, app_event, app_day, app_score, app_opp, app_weight, by_fighter


def run_whr(
    fights: pd.DataFrame,
    *,
    w2_per_day: float = WHR_W2_PER_DAY,
    prior_var: float = WHR_PRIOR_VAR,
    iterations: int = WHR_ITERATIONS,
    step_clip: float = WHR_STEP_CLIP,
    out_col: str = "mu_whr",
) -> pd.DataFrame:
    """Run the WHR smoother over a canonical fight table.

    Required ``fights`` columns: ``fighter_a``, ``fighter_b``, ``winner``,
    ``is_draw``, ``event_date``, ``event_name``.

    Optional columns ``weight_a`` / ``weight_b`` (added by
    ``_attach_appearance_weights``) scale each fight's Bradley-Terry likelihood
    contribution — the Wiener-process and anchor priors are unweighted, so the
    temporal coupling and global scale remain structural constraints. This makes
    the sleeve concept fully modular: the same integrity / performance weight
    tables used for Glicko-2 apply here without modification.

    Returns a per-appearance history frame with columns
    ``fighter``, ``event_date``, ``event_name``, ``out_col`` — the same shape as
    ``ratings_history.parquet`` so it feeds ``ratings.peaks`` unchanged.
    """
    cols = ["fighter", "event_date", "event_name", out_col]
    if fights is None or fights.empty:
        return pd.DataFrame(columns=cols)

    app_fighter, app_event, app_day, app_score, app_opp, app_weight, by_fighter = _build_appearances(fights)
    n_app = len(app_fighter)
    if n_app == 0:
        return pd.DataFrame(columns=cols)

    ratings = np.zeros(n_app, dtype=float)
    inv_prior = 1.0 / float(prior_var)

    # Pre-extract per-fighter node arrays once.
    fighter_node_arrays = {
        fighter: np.asarray(nodes, dtype=np.int64) for fighter, nodes in by_fighter.items()
    }

    for _ in range(int(iterations)):
        for nodes in fighter_node_arrays.values():
            k = len(nodes)
            if k == 0:
                continue
            r = ratings[nodes]
            opp = ratings[app_opp[nodes]]
            s = app_score[nodes]
            w = app_weight[nodes]  # per-fight likelihood sleeve weights

            # Bradley-Terry likelihood — scaled by sleeve weight so each fight
            # contributes w times as much evidence to the global estimation.
            p = 1.0 / (1.0 + np.exp(-(r - opp)))
            g = w * (s - p)
            h_diag = w * (-p * (1.0 - p))

            # Weak Gaussian anchor prior r ~ N(0, prior_var) — unweighted.
            g -= r * inv_prior
            h_diag -= inv_prior

            # Wiener-process prior between consecutive appearances — unweighted.
            if k > 1:
                gaps = np.maximum(app_day[nodes][1:] - app_day[nodes][:-1], 1.0)
                inv_v = 1.0 / (w2_per_day * gaps)
                delta_r = r[1:] - r[:-1]
                g[:-1] += delta_r * inv_v
                g[1:] -= delta_r * inv_v
                h_diag[:-1] -= inv_v
                h_diag[1:] -= inv_v
                off = inv_v  # H[i][i+1]; for the (-H) system this is -inv_v
                a_off = -off
            else:
                a_off = np.zeros(0)

            # Newton step: solve (-H) step = g  (-H is positive-definite).
            a_diag = -h_diag
            step = _thomas(a_diag, a_off, g)
            np.clip(step, -step_clip, step_clip, out=step)
            ratings[nodes] = r + step

        # Re-anchor the global mean to 0 each pass — the BT graph fixes
        # relative ratings; the level is only pinned by the weak prior, so
        # this keeps the scale stable across iterations.
        ratings -= ratings.mean()

    mu_whr = _ELO_ANCHOR + ratings * _ELO_PER_NAT
    out = pd.DataFrame(
        {
            "fighter": app_fighter,
            "event_date": _EPOCH + pd.to_timedelta(app_day, unit="D"),
            "event_name": app_event,
            out_col: mu_whr,
        }
    )
    return out.sort_values(["fighter", "event_date", "event_name"]).reset_index(drop=True)
