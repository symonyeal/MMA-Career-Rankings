"""Whole-History Rating (WHR) — the retrospective production skill estimator.

Reference: Rémi Coulom (2008), "Whole-History Rating: A Bayesian Rating System
for Players of Time-Varying Strength."

Why this exists
---------------
The diagnostic canonical engine is Glicko-2, a *filter*: information flows one
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

By default the appearance mean is subtracted after every pass
(``center_each_pass``, :data:`WHR_CENTER_EACH_PASS`). That is the solver the
published boards and the tuned priors were fitted with. It is not the exact
posterior mode: the anchor and virtual-game priors already fix the origin, so
the shift moves the fit off it and lets one bout graph move another it is not
connected to. ``center_each_pass=False`` solves the posterior exactly; it is a
candidate until it passes a held-out test on production inputs. A fixed pass
count is not a convergence certificate.

The output ``mu_whr`` is mapped to a familiar Elo-like scale
(``1500 + r * 400/ln(10)``) so it slots into the same downstream machinery as
``mu_canonical``. ``w2_per_day`` should ultimately be chosen by predictive
backtest (Brier / log-loss); the default is a reasonable MMA prior.
"""
from __future__ import annotations


import numpy as np
import pandas as pd

from ratings.constants import (
    GREGORIAN_YEAR_DAYS,
    WHR_CENTER_EACH_PASS,
    WHR_ITERATIONS,
    WHR_PRIOR_VAR,
    WHR_STEP_CLIP,
    WHR_VIRTUAL_GAMES,
    WHR_W2_PER_DAY,
    WHR_WINNER_SCORE_COL,
)

import whr_rs

# Natural-scale rating -> Elo-like display scale.
_ELO_PER_NAT = 400.0 / np.log(10.0)
_ELO_ANCHOR = 1500.0
_EPOCH = pd.Timestamp("2000-01-01")
AGE_BIN_EDGES = np.array([24.0, 27.0, 30.0, 33.0, 36.0, 39.0, 42.0])
AGE_BIN_LABELS = ("<24", "24-27", "27-30", "30-33", "33-36", "36-39", "39-42", "42+")


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

    start_age = (pd.Timestamp(start) - pd.Timestamp(birth)).days / GREGORIAN_YEAR_DAYS
    end_age = (pd.Timestamp(end) - pd.Timestamp(birth)).days / GREGORIAN_YEAR_DAYS
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

    # Appearance 2i is fighter_a of bout i and 2i+1 is fighter_b. A draw wins
    # over a recorded winner, and a bout whose winner is neither fighter scores
    # as a draw.
    app_fighter[0::2], app_fighter[1::2] = fighter_a, fighter_b
    app_event[0::2] = app_event[1::2] = event_name
    app_day[0::2] = app_day[1::2] = days
    app_opp[0::2] = np.arange(1, 2 * n, 2)
    app_opp[1::2] = np.arange(0, 2 * n, 2)
    app_weight[0::2] = app_weight[1::2] = bout_weight
    draw = np.array([bool(x) for x in is_draw], dtype=bool)
    a_won = ~draw & np.array([w == a for w, a in zip(winner, fighter_a)], dtype=bool)
    b_won = ~draw & ~a_won & np.array([w == b for w, b in zip(winner, fighter_b)], dtype=bool)
    s_win = np.where(np.isnan(winner_score_arr), 1.0, winner_score_arr)
    app_score[0::2] = np.where(a_won, s_win, np.where(b_won, 1.0 - s_win, 0.5))
    app_score[1::2] = np.where(a_won, 1.0 - s_win, np.where(b_won, s_win, 0.5))

    # Fighters in order of first appearance, each with its nodes ascending,
    # which is chronological: the dict order is the Gauss--Seidel update order.
    codes, names = pd.factorize(app_fighter)
    order = np.argsort(codes, kind="stable")
    cuts = np.cumsum(np.bincount(codes, minlength=len(names)))[:-1]
    by_fighter: dict[str, list[int]] = {
        name: nodes.tolist() for name, nodes in zip(names, np.split(order, cuts))
    }

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


def _fit(
    fighter_node_arrays: dict[object, np.ndarray],
    fighter_gaps: dict[object, np.ndarray],
    transition_bins: dict[object, np.ndarray],
    app_opp: np.ndarray,
    app_score: np.ndarray,
    app_weight: np.ndarray,
    *,
    w2_per_day: float,
    inv_prior: float,
    vg_total: float,
    step_clip: float,
    fit_passes: int,
    age_drift: bool,
    center_each_pass: bool,
    return_variance: bool,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Pack appearance arrays for Rust fitting; return ratings, drift per day and conditional variances.

    Fighters keep their dict order: the passes are Gauss--Seidel, so the order
    fighters are updated in is part of the result.
    """
    fs = list(fighter_node_arrays)
    ks = np.array([len(fighter_node_arrays[f]) for f in fs], dtype=np.int64)
    pt = np.zeros(len(fs) + 1, dtype=np.int64)
    pt[1:] = np.cumsum(ks)
    ix = np.concatenate([fighter_node_arrays[f] for f in fs]).astype(np.int64)
    gp = np.zeros(len(ix), dtype=float)
    bn = np.full(len(ix), -1, dtype=np.int64)
    for i, f in enumerate(fs):
        lo, k = int(pt[i]), int(ks[i])
        if k > 1:
            gp[lo:lo + k - 1] = fighter_gaps[f]
            if age_drift:
                bn[lo:lo + k - 1] = transition_bins[f]
    r, dr, var = whr_rs.fit(
        app_opp.astype("<i8").tobytes(), app_score.astype("<f8").tobytes(),
        app_weight.astype("<f8").tobytes(), pt.astype("<i8").tobytes(), ix.astype("<i8").tobytes(),
        gp.astype("<f8").tobytes(), bn.astype("<i8").tobytes(),
        float(w2_per_day), float(inv_prior), float(vg_total), float(step_clip), int(fit_passes),
        bool(age_drift), bool(center_each_pass), len(AGE_BIN_LABELS),
        25.0 / (_ELO_PER_NAT * GREGORIAN_YEAR_DAYS), return_variance,
    )
    return tuple(np.frombuffer(values, dtype="<f8").copy() for values in (r, dr, var))


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
    center_each_pass: bool = WHR_CENTER_EACH_PASS,
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

    ``center_each_pass`` re-centres the appearance mean after every pass, as
    every published fit has; ``False`` solves the exact posterior mode.

    Numerical fitting and conditional variances require the ``whr_rs`` extension.
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
            app_age[nodes] = (app_day[nodes] - birth_day) / GREGORIAN_YEAR_DAYS
            if len(nodes) > 1:
                mid_age = (app_age[nodes][1:] + app_age[nodes][:-1]) / 2.0
                bins = np.digitize(mid_age, AGE_BIN_EDGES).astype(int)
                bins[(mid_age < 14.0) | (mid_age > 65.0)] = -1
                transition_bins[fighter] = bins
            else:
                transition_bins[fighter] = np.zeros(0, dtype=int)

    # Gaps are a property of the schedule, not of the current ratings, so they
    # are built once instead of being rebuilt for every fighter on every pass.
    # The inner loop runs about 34,000 x 2 x iterations times, and rebuilding
    # them there dominated the fit.
    fighter_gaps: dict[object, np.ndarray] = {}
    for fighter, nodes in fighter_node_arrays.items():
        if len(nodes) > 1:
            fighter_gaps[fighter] = np.maximum(
                app_day[nodes][1:] - app_day[nodes][:-1], 1.0
            )

    ratings, drift_per_day, variances = _fit(
        fighter_node_arrays, fighter_gaps, transition_bins, app_opp, app_score, app_weight,
        w2_per_day=w2_per_day, inv_prior=inv_prior, vg_total=vg_total, step_clip=step_clip,
        fit_passes=int(iterations), age_drift=age_drift, center_each_pass=center_each_pass,
        return_variance=return_variance,
    )

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
            drift_per_day[app_bins[valid_age]] * _ELO_PER_NAT * GREGORIAN_YEAR_DAYS
        )
        data["age_years"] = app_age
        data["prior_drift_elo_per_year"] = prior_drift

    if return_variance:
        data[out_col.replace("mu_", "var_", 1)] = variances

    out = pd.DataFrame(data)
    out = out.sort_values(["fighter", "event_date", "event_name"]).reset_index(drop=True)
    if age_drift:
        out.attrs["age_drift_elo_per_year"] = (
            drift_per_day * _ELO_PER_NAT * GREGORIAN_YEAR_DAYS
        ).tolist()
    return out


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
