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
ratings are comparable across distant time by construction, which is why the
era-normalisation patches that used to sit downstream of the filter were
retired: the smoother addresses the artifact at the rating layer.

Model
-----
* Dynamic Bradley-Terry likelihood. Each fighter has a latent rating ``r`` at
  each appearance (natural/logistic scale). For a bout the fighter's score
  ``s in {1, 0.5, 0}`` has expected value ``P = sigma(r - r_opp)``.
* Wiener-process prior between a fighter's consecutive appearances: the rating
  change over ``dt`` days is ``N(0, w2_per_day * dt)``.
* A weak Gaussian anchor prior ``r ~ N(0, prior_var)`` pins the global scale.
* ``virtual_games`` bouts of prior evidence against an average opponent, half
  won and half lost. Both priors carry a *fixed mass per fighter*, spread over
  that fighter's appearances, so prior strength does not grow with career
  length the way the likelihood does.

Why the prior mass is fixed per fighter
---------------------------------------
An undefeated fighter has no interior maximum-likelihood rating: the
Bradley--Terry gradient ``sum_j (1 - sigma(r - r_j))`` is positive for every
finite ``r``, so only the prior stops the climb. If the prior is applied once
per appearance, its mass grows with career length at the same rate as the
likelihood and the stopping point becomes a constant independent of the
evidence. That is a real failure, not a corner case: before ``virtual_games``
existed, the highest rating in the UFC database belonged to a fighter with a
single bout, and 56 fighters at 1-0 averaged above the 98th percentile of the
roster. With fixed prior mass ``v``, an undefeated fighter with ``k`` wins over
average opposition settles at ``sigma(r) = (k + v/2) / (k + v)``, which rises
with ``k`` as it must.

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
    WHR_VIRTUAL_GAMES,
    WHR_W2_PER_DAY,
    WHR_WINNER_SCORE_COL,
)

# Natural-scale rating -> Elo-like display scale.
_ELO_PER_NAT = 400.0 / np.log(10.0)
_ELO_ANCHOR = 1500.0
_EPOCH = pd.Timestamp("2000-01-01")
AGE_BIN_EDGES = np.array([24.0, 27.0, 30.0, 33.0, 36.0, 39.0, 42.0])
AGE_BIN_LABELS = ("<24", "24-27", "27-30", "30-33", "33-36", "36-39", "39-42", "42+")
_DAYS_PER_YEAR = 365.2425


def project_age_rating(
    mu: float,
    *,
    last_date: object,
    target_date: object,
    birth_date: object,
    drift_elo_per_year: np.ndarray | list[float] | tuple[float, ...],
) -> float:
    """Project one last-observed rating through an inactive aging gap.

    ``run_whr(age_drift=True)`` learns a piecewise-constant population drift
    curve.  Its transition prior applies that curve between observed
    appearances; a forecast has no target appearance node, so it must integrate
    the same curve from the last observation to the forecast date explicitly.

    Unknown dates, unknown birth date, ages outside the model's 14--65 support,
    and backward projections are neutral.  Crossing an age-bin boundary is
    integrated piecewise rather than charging the whole gap at the last bin.
    """
    start = pd.to_datetime(last_date, errors="coerce")
    end = pd.to_datetime(target_date, errors="coerce")
    birth = pd.to_datetime(birth_date, errors="coerce")
    rates = np.asarray(drift_elo_per_year, dtype=float)
    if (
        pd.isna(start)
        or pd.isna(end)
        or pd.isna(birth)
        or end <= start
        or len(rates) != len(AGE_BIN_LABELS)
        or not np.isfinite(rates).all()
    ):
        return float(mu)

    start_age = (pd.Timestamp(start) - pd.Timestamp(birth)).days / _DAYS_PER_YEAR
    end_age = (pd.Timestamp(end) - pd.Timestamp(birth)).days / _DAYS_PER_YEAR
    if end_age <= start_age:
        return float(mu)

    projected = float(mu)
    cursor = max(start_age, 14.0)
    stop = min(end_age, 65.0)
    while cursor < stop:
        bucket = int(np.digitize(cursor, AGE_BIN_EDGES))
        upper = AGE_BIN_EDGES[bucket] if bucket < len(AGE_BIN_EDGES) else 65.0
        segment_end = min(stop, float(upper))
        if segment_end <= cursor:
            break
        projected += float(rates[bucket]) * (segment_end - cursor)
        cursor = segment_end
    return projected


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


def _tridiag_inv_diag(a_diag: np.ndarray, a_off: np.ndarray) -> np.ndarray:
    """Diagonal of the inverse of an SPD symmetric tridiagonal matrix ``A``.

    ``a_diag`` is the main diagonal (length k); ``a_off`` the off-diagonal
    (length k-1). Uses Meurant's forward (LU) / backward (UL) pivot recurrences:
    ``(A^{-1})_{ii} = 1 / (delta_i + lambda_i - a_diag_i)`` where ``delta`` are
    the forward pivots and ``lambda`` the backward pivots. Stable and O(k); this
    gives each WHR rating's posterior variance from the per-fighter Hessian.
    """
    k = len(a_diag)
    if k == 0:
        return np.zeros(0)
    if k == 1:
        return 1.0 / a_diag
    b2 = a_off ** 2
    delta = np.empty(k)
    delta[0] = a_diag[0]
    for i in range(1, k):
        delta[i] = a_diag[i] - b2[i - 1] / delta[i - 1]
    lam = np.empty(k)
    lam[k - 1] = a_diag[k - 1]
    for i in range(k - 2, -1, -1):
        lam[i] = a_diag[i] - b2[i] / lam[i + 1]
    return 1.0 / (delta + lam - a_diag)


def _build_appearances(
    fights: pd.DataFrame,
    *,
    winner_score_col: str | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict[str, list[int]]]:
    """Explode bouts into appearance nodes.

    Returns ``(app_fighter, app_event, app_day, app_score, app_opp, app_weight, by_fighter)``
    where appearance ``2i`` is fighter_a of bout ``i`` and ``2i+1`` is
    fighter_b. ``app_opp`` maps each node to its bout-paired node.
    ``app_weight`` repeats one shared bout-likelihood weight on both nodes
    (1.0 when the fight table has no weight columns). A paired Bradley--Terry
    likelihood cannot coherently give its winner and loser different evidence
    weights. ``by_fighter`` maps a fighter to chronological node ids.
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
    has_weight_a, has_weight_b = "weight_a" in f.columns, "weight_b" in f.columns
    if has_weight_a != has_weight_b:
        raise ValueError("WHR requires both weight_a and weight_b, or neither")
    if has_weight_a:
        weight_a_arr = pd.to_numeric(f["weight_a"], errors="coerce").to_numpy(dtype=float)
        weight_b_arr = pd.to_numeric(f["weight_b"], errors="coerce").to_numpy(dtype=float)
        if (not np.isfinite(weight_a_arr).all() or not np.isfinite(weight_b_arr).all()
                or (weight_a_arr <= 0.0).any() or (weight_b_arr <= 0.0).any()):
            raise ValueError("WHR likelihood weights must be finite and positive")
        if not np.allclose(weight_a_arr, weight_b_arr, rtol=0.0, atol=1e-12):
            raise ValueError(
                "WHR requires one shared likelihood weight per bout; "
                "side-specific weight_a/weight_b values are not a joint model"
            )
        bout_weight = weight_a_arr
    else:
        bout_weight = np.ones(n, dtype=float)

    # Binary/draw scoring is the default. Fractional winner scores must be
    # requested explicitly so an audit column cannot silently change the model.
    if winner_score_col is not None:
        if winner_score_col not in f.columns:
            raise ValueError(f"winner score column not found: {winner_score_col}")
        winner_score_arr = pd.to_numeric(
            f[winner_score_col], errors="coerce"
        ).to_numpy(dtype=float)
        valid_scores = winner_score_arr[np.isfinite(winner_score_arr)]
        if ((valid_scores < 0.5) | (valid_scores > 1.0)).any():
            raise ValueError("winner scores must lie in [0.5, 1.0]")
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
        app_weight[na] = app_weight[nb] = bout_weight[i]
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


def production_score_kwargs(fights: pd.DataFrame | None) -> dict[str, str]:
    """The winner-score argument every **published** WHR fit has to pass.

    ``run_whr`` still defaults to binary scoring, because a column appearing in
    a frame must never change the model on its own -- that is the guard the
    explicit ``winner_score_col`` exists to provide. This helper is the single
    place that names :data:`WHR_WINNER_SCORE_COL`, so the snapshot fit, the
    prequential gate and the bootstrap refits cannot drift apart into three
    different models.

    Raises rather than falling back when the column is absent: a published fit
    silently reverting to binary is exactly the failure this guards.
    """
    if WHR_WINNER_SCORE_COL is None:
        return {}
    columns = getattr(fights, "columns", ())
    if WHR_WINNER_SCORE_COL not in columns:
        raise ValueError(
            "a published WHR fit needs the winner-score column "
            f"{WHR_WINNER_SCORE_COL!r}; stage it, or set "
            "ratings.constants.WHR_WINNER_SCORE_COL to None for a binary fit"
        )
    return {"winner_score_col": WHR_WINNER_SCORE_COL}


def run_whr(
    fights: pd.DataFrame,
    *,
    w2_per_day: float = WHR_W2_PER_DAY,
    prior_var: float = WHR_PRIOR_VAR,
    virtual_games: float = WHR_VIRTUAL_GAMES,
    iterations: int = WHR_ITERATIONS,
    step_clip: float = WHR_STEP_CLIP,
    out_col: str = "mu_whr",
    return_variance: bool = False,
    winner_score_col: str | None = None,
    birth_dates: dict[str, object] | pd.Series | None = None,
    age_drift: bool = False,
) -> pd.DataFrame:
    """Run the WHR smoother over a canonical fight table.

    Required ``fights`` columns: ``fighter_a``, ``fighter_b``, ``winner``,
    ``is_draw``, ``event_date``, ``event_name``.

    Optional ``weight_a`` / ``weight_b`` columns scale each bout's
    Bradley--Terry likelihood contribution. They must be equal within every
    bout: one likelihood has one evidence weight. The Wiener-process and anchor
    priors remain unweighted. Binary/draw scoring is always used unless an
    explicit ``winner_score_col`` is supplied.

    Returns a per-appearance history frame with columns
    ``fighter``, ``event_date``, ``event_name``, ``out_col`` — the same shape as
    ``ratings_history.parquet`` so every downstream consumer reads one shape.

    With ``return_variance=True`` an extra ``var_<stream>`` column carries each
    rating's conditional block-curvature variance on the natural scale. It
    holds opponents fixed and is useful only as an experimental attenuation
    feature; it is not a marginal posterior variance or a rank interval.

    With ``age_drift=True``, a neutral fit first estimates the population mean
    trajectory in age buckets, then the model is refit under that fixed curve.
    Only differences from the under-24 bucket are used: the common negative
    offset in observed career changes is not identified as aging. Fighters
    without a birth date retain the zero-drift prior.
    """
    cols = ["fighter", "event_date", "event_name", out_col]
    if fights is None or fights.empty:
        return pd.DataFrame(columns=cols)

    app_fighter, app_event, app_day, app_score, app_opp, app_weight, by_fighter = (
        _build_appearances(fights, winner_score_col=winner_score_col)
    )
    n_app = len(app_fighter)
    if n_app == 0:
        return pd.DataFrame(columns=cols)

    ratings = np.zeros(n_app, dtype=float)
    inv_prior = 1.0 / float(prior_var)
    vg_total = float(virtual_games)
    if vg_total < 0.0:
        raise ValueError("virtual_games must be non-negative")

    # Pre-extract per-fighter node arrays once.
    fighter_node_arrays = {
        fighter: np.asarray(nodes, dtype=np.int64) for fighter, nodes in by_fighter.items()
    }

    app_age = np.full(n_app, np.nan, dtype=float)
    transition_bins: dict[object, np.ndarray] = {}
    drift_per_day = np.zeros(len(AGE_BIN_LABELS), dtype=float)
    if age_drift:
        if birth_dates is None:
            raise ValueError("age_drift requires birth_dates")
        dob_map = dict(birth_dates)
        for fighter, nodes in fighter_node_arrays.items():
            dob = pd.to_datetime(dob_map.get(str(fighter)), errors="coerce")
            if pd.isna(dob):
                transition_bins[fighter] = np.full(max(len(nodes) - 1, 0), -1, dtype=int)
                continue
            birth_day = float((pd.Timestamp(dob) - _EPOCH).days)
            app_age[nodes] = (app_day[nodes] - birth_day) / _DAYS_PER_YEAR
            if len(nodes) > 1:
                mid_age = (app_age[nodes][1:] + app_age[nodes][:-1]) / 2.0
                bins = np.digitize(mid_age, AGE_BIN_EDGES).astype(int)
                bins[(mid_age < 14.0) | (mid_age > 65.0)] = -1
                transition_bins[fighter] = bins
            else:
                transition_bins[fighter] = np.zeros(0, dtype=int)

    fit_passes = int(iterations)
    total_passes = fit_passes * (2 if age_drift else 1)
    for pass_index in range(total_passes):
        for fighter, nodes in fighter_node_arrays.items():
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

            # Priors carry a fixed mass per fighter, spread over the career, so
            # they do not scale with career length the way the likelihood does.
            anchor = inv_prior / k
            g -= r * anchor
            h_diag -= anchor

            # Virtual games against an average opponent (rating 0): half won,
            # half lost. Unbiased at r = 0, and the only term that gives an
            # undefeated record a finite maximum that grows with the evidence.
            if vg_total > 0.0:
                vg = vg_total / k
                p0 = 1.0 / (1.0 + np.exp(-r))
                g += vg * (0.5 - p0)
                h_diag -= vg * p0 * (1.0 - p0)

            # Wiener-process prior between consecutive appearances — unweighted.
            if k > 1:
                gaps = np.maximum(app_day[nodes][1:] - app_day[nodes][:-1], 1.0)
                inv_v = 1.0 / (w2_per_day * gaps)
                residual = r[1:] - r[:-1]
                if age_drift:
                    bins = transition_bins[fighter]
                    known = bins >= 0
                    expected = np.zeros_like(gaps)
                    expected[known] = drift_per_day[bins[known]] * gaps[known]
                    residual = residual - expected
                g[:-1] += residual * inv_v
                g[1:] -= residual * inv_v
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

        if age_drift and pass_index == fit_passes - 1:
            change_sum = np.zeros(len(AGE_BIN_LABELS), dtype=float)
            day_sum = np.zeros(len(AGE_BIN_LABELS), dtype=float)
            for fighter, nodes in fighter_node_arrays.items():
                if len(nodes) < 2:
                    continue
                bins = transition_bins[fighter]
                gaps = np.maximum(app_day[nodes][1:] - app_day[nodes][:-1], 1.0)
                changes = ratings[nodes][1:] - ratings[nodes][:-1]
                for bucket in range(len(AGE_BIN_LABELS)):
                    take = bins == bucket
                    if take.any():
                        change_sum[bucket] += float(changes[take].sum())
                        day_sum[bucket] += float(gaps[take].sum())
            raw = np.divide(
                change_sum,
                day_sum,
                out=np.zeros_like(change_sum),
                where=day_sum > 0,
            )
            # The common offset is confounded with scale and roster churn. Age
            # is identified by the difference from the youngest observed bin.
            baseline = raw[0] if day_sum[0] > 0 else 0.0
            target = raw - baseline
            target[day_sum == 0] = 0.0
            limit = 25.0 / (_ELO_PER_NAT * _DAYS_PER_YEAR)
            drift_per_day = np.clip(target, -limit, limit)
            # Refit from the neutral initialization under the now-estimated
            # prior mean. Re-estimating from the already drifted trajectory
            # creates positive feedback and is not a valid empirical prior.
            ratings.fill(0.0)

    mu_whr = _ELO_ANCHOR + ratings * _ELO_PER_NAT
    data = {
        "fighter": app_fighter,
        "event_date": _EPOCH + pd.to_timedelta(app_day, unit="D"),
        "event_name": app_event,
        out_col: mu_whr,
    }
    if age_drift:
        app_bins = np.digitize(app_age, AGE_BIN_EDGES).astype(int)
        valid_age = np.isfinite(app_age) & (app_age >= 14.0) & (app_age <= 65.0)
        prior_drift = np.full(n_app, np.nan, dtype=float)
        prior_drift[valid_age] = (
            drift_per_day[app_bins[valid_age]] * _ELO_PER_NAT * _DAYS_PER_YEAR
        )
        data["age_years"] = app_age
        data["prior_drift_elo_per_year"] = prior_drift

    if return_variance:
        # Conditional per-fighter block curvature on the NATURAL scale. The full
        # WHR Hessian also couples opponents, so this is deliberately not called
        # a marginal posterior variance.
        variances = np.zeros(n_app, dtype=float)
        for nodes in fighter_node_arrays.values():
            k = len(nodes)
            if k == 0:
                continue
            r = ratings[nodes]
            opp = ratings[app_opp[nodes]]
            w = app_weight[nodes]
            p = 1.0 / (1.0 + np.exp(-(r - opp)))
            h_diag = w * (-p * (1.0 - p)) - inv_prior / k
            if vg_total > 0.0:
                p0 = 1.0 / (1.0 + np.exp(-r))
                h_diag -= (vg_total / k) * p0 * (1.0 - p0)
            if k > 1:
                gaps = np.maximum(app_day[nodes][1:] - app_day[nodes][:-1], 1.0)
                inv_v = 1.0 / (w2_per_day * gaps)
                h_diag[:-1] -= inv_v
                h_diag[1:] -= inv_v
                a_off = -inv_v
            else:
                a_off = np.zeros(0)
            variances[nodes] = _tridiag_inv_diag(-h_diag, a_off)
        data[out_col.replace("mu_", "var_", 1)] = variances

    out = pd.DataFrame(data)
    out = out.sort_values(["fighter", "event_date", "event_name"]).reset_index(drop=True)
    if age_drift:
        out.attrs["age_drift_elo_per_year"] = (
            drift_per_day * _ELO_PER_NAT * _DAYS_PER_YEAR
        ).tolist()
    return out
