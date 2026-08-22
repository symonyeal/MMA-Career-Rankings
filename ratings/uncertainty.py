"""Event-cluster bootstrap for the public career board.

Why this exists
---------------
A rank printed without an interval invites a reader to believe the difference
between #6 and #14 is real. For this engine it often is not: a fighter with
seven bouts and a fighter with thirty can land next to each other on career
skill mass while resting on very different amounts of evidence.

WHR's optional ``return_variance`` cannot answer that question. It inverts one
fighter's temporal Hessian block while holding every opponent's trajectory
fixed, and the joint Hessian couples fighters through every shared bout, so the
block inverse is not the corresponding block of the full inverse. It is also
conditional on the fitted opponents, which is exactly the uncertainty a career
board needs to propagate.

What this does instead
----------------------
Perturb the weight of whole **events** — the natural independent cluster, since
bouts on one card share matchmaking, judging and conditions — refit the whole
smoother, and recompute the career functional. The spread of the recomputed
scores and ranks is the reported uncertainty.

The weights are Dirichlet(1, ..., 1) scaled to mean one: the Bayesian bootstrap
(Rubin 1981). Drawing events with replacement instead would be the more familiar
cluster bootstrap, but it is wrong for this statistic. Career skill mass is a
*sum over years*, and a with-replacement draw omits about 37% of events, so
whole fighter-years disappear and every replicate is biased low — measured at
roughly 25% below the point estimate before this was changed. Dirichlet weights
keep total evidence constant and every fighter present, so the interval reflects
how much the ranking depends on which results carried weight, not on how many
events survived the draw.

The smoother already accepts one shared likelihood weight per bout, so a
replicate costs exactly one refit and no data is duplicated.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ratings.symon_score import career_skill_mass
from ratings.whr import run_whr


BOOTSTRAP_COLUMNS = [
    "fighter",
    "mass",
    "mass_lo",
    "mass_hi",
    "mass_sd",
    "rank",
    "rank_lo",
    "rank_hi",
    "replicates_present",
    "replicates",
]


def _event_index(fights: pd.DataFrame) -> tuple[np.ndarray, int]:
    """Map every bout row to its event id, and return the event count."""
    keys = pd.MultiIndex.from_arrays([
        pd.to_datetime(fights["event_date"], errors="coerce"),
        fights["event_name"].astype(str) if "event_name" in fights.columns
        else pd.Series("", index=fights.index),
    ])
    codes, uniques = pd.factorize(keys)
    return codes, len(uniques)


def _weighted(fights: pd.DataFrame, weights: np.ndarray, codes: np.ndarray) -> pd.DataFrame:
    """Attach one shared per-bout likelihood weight from its event's weight."""
    out = fights.copy()
    w = np.clip(weights[codes], 1e-9, None)
    out["weight_a"] = w
    out["weight_b"] = w
    return out


def career_mass_bootstrap(
    fights: pd.DataFrame,
    *,
    replicates: int = 200,
    seed: int = 0,
    lo: float = 0.025,
    hi: float = 0.975,
    progress: bool = False,
    whr_kwargs: dict | None = None,
    mass_kwargs: dict | None = None,
) -> pd.DataFrame:
    """Bootstrap career skill mass and its rank by resampling whole events."""
    if replicates < 1:
        raise ValueError("replicates must be at least 1")
    if not 0.0 <= lo < hi <= 1.0:
        raise ValueError("lo and hi must satisfy 0 <= lo < hi <= 1")
    whr_kwargs = dict(whr_kwargs or {})
    mass_kwargs = dict(mass_kwargs or {})
    if fights is None or fights.empty:
        return pd.DataFrame(columns=BOOTSTRAP_COLUMNS)

    f = fights.reset_index(drop=True)
    codes, n_events = _event_index(f)

    point = career_skill_mass(run_whr(_weighted(f, np.ones(n_events), codes),
                                      **whr_kwargs), **mass_kwargs)
    if point.empty:
        return pd.DataFrame(columns=BOOTSTRAP_COLUMNS)
    point = point.rename(columns={"score": "mass"})[["fighter", "mass"]]
    point["rank"] = point["mass"].rank(ascending=False, method="min").astype(int)

    rng = np.random.default_rng(seed)
    mass_draws: list[pd.Series] = []
    rank_draws: list[pd.Series] = []
    for b in range(int(replicates)):
        weights = rng.dirichlet(np.ones(n_events)) * n_events
        board = career_skill_mass(
            run_whr(_weighted(f, weights, codes), **whr_kwargs), **mass_kwargs
        )
        if board.empty:
            continue
        s = board.set_index("fighter")["score"]
        mass_draws.append(s)
        rank_draws.append(s.rank(ascending=False, method="min"))
        if progress:
            print(f"  [bootstrap] {b + 1}/{replicates}", flush=True)

    if not mass_draws:
        return pd.DataFrame(columns=BOOTSTRAP_COLUMNS)

    mass = pd.concat(mass_draws, axis=1)
    rank = pd.concat(rank_draws, axis=1)
    out = pd.DataFrame({
        "mass_lo": mass.quantile(lo, axis=1),
        "mass_hi": mass.quantile(hi, axis=1),
        "mass_sd": mass.std(axis=1, ddof=1),
        "rank_lo": rank.quantile(lo, axis=1),
        "rank_hi": rank.quantile(hi, axis=1),
        "replicates_present": mass.notna().sum(axis=1).astype(int),
    }).reset_index(names="fighter")
    out["replicates"] = len(mass_draws)

    out = point.merge(out, on="fighter", how="left")
    for col in ("rank_lo", "rank_hi"):
        out[col] = out[col].round().astype("Int64")
    return out.sort_values("rank")[BOOTSTRAP_COLUMNS].reset_index(drop=True)


def rank_is_separated(board: pd.DataFrame, a: str, b: str) -> bool:
    """True when two fighters' bootstrap rank intervals do not overlap.

    The honest reading of the board: a rank difference is only claimed where
    the intervals are disjoint.
    """
    rows = board.set_index("fighter")
    if a not in rows.index or b not in rows.index:
        return False
    ra, rb = rows.loc[a], rows.loc[b]
    if pd.isna(ra["rank_lo"]) or pd.isna(rb["rank_lo"]):
        return False
    return bool(ra["rank_hi"] < rb["rank_lo"] or rb["rank_hi"] < ra["rank_lo"])
