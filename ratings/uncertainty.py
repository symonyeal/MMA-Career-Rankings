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
    eligible_fighters: set[str] | None = None,
    return_draws: bool = False,
) -> pd.DataFrame | tuple[pd.DataFrame, pd.DataFrame]:
    """Bootstrap career skill mass and its rank by resampling whole events.

    ``return_draws=True`` also returns the fighters-by-replicates mass matrix.
    Keep it: the marginal intervals in the summary cannot answer whether *two
    named fighters* differ, because that is a paired question and two
    overlapping marginal intervals are consistent with a difference of a
    constant sign in every replicate. :func:`career_tiers` needs the pairing.

    ``eligible_fighters`` applies the published completeness gate before every
    point and replicate rank. Without it, short-record fighters withheld from
    the board still widen and reorder the board's reported intervals.
    """
    if replicates < 1:
        raise ValueError("replicates must be at least 1")
    if not 0.0 <= lo < hi <= 1.0:
        raise ValueError("lo and hi must satisfy 0 <= lo < hi <= 1")
    whr_kwargs = dict(whr_kwargs or {})
    mass_kwargs = dict(mass_kwargs or {})
    empty_draws = pd.DataFrame()
    if fights is None or fights.empty:
        empty = pd.DataFrame(columns=BOOTSTRAP_COLUMNS)
        return (empty, empty_draws) if return_draws else empty

    f = fights.reset_index(drop=True)
    codes, n_events = _event_index(f)

    point = career_skill_mass(run_whr(_weighted(f, np.ones(n_events), codes),
                                      **whr_kwargs), **mass_kwargs)
    if point.empty:
        empty = pd.DataFrame(columns=BOOTSTRAP_COLUMNS)
        return (empty, empty_draws) if return_draws else empty
    if eligible_fighters is not None:
        point = point[point["fighter"].isin(eligible_fighters)].copy()
    if point.empty:
        empty = pd.DataFrame(columns=BOOTSTRAP_COLUMNS)
        return (empty, empty_draws) if return_draws else empty
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
        if eligible_fighters is not None:
            board = board[board["fighter"].isin(eligible_fighters)]
        s = board.set_index("fighter")["score"]
        mass_draws.append(s)
        rank_draws.append(s.rank(ascending=False, method="min"))
        if progress:
            print(f"  [bootstrap] {b + 1}/{replicates}", flush=True)

    if not mass_draws:
        empty = pd.DataFrame(columns=BOOTSTRAP_COLUMNS)
        return (empty, empty_draws) if return_draws else empty

    mass = pd.concat(mass_draws, axis=1)
    mass.columns = [f"r{i}" for i in range(mass.shape[1])]
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
    out = out.sort_values("rank")[BOOTSTRAP_COLUMNS].reset_index(drop=True)
    if return_draws:
        return out, mass.reindex(out["fighter"])
    return out


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


TIER_COLUMNS = [
    "tier",
    "tier_label",
    "fighter",
    "mass",
    "mass_lo",
    "mass_hi",
    "rank",
    "tier_leader",
    "p_below_tier_leader",
]

# The board's own floor. A career that never cleared the bar in any year has a
# mass of exactly zero and so does every other such career, which is a tie, not
# an ordering -- the same fact :func:`ratings.boards.completeness_gated_board`
# refuses to print a rank for.
UNRANKED_TIER_LABEL = "Unranked (no year above the bar)"


def separation_probability(draws: pd.DataFrame, a: str, b: str) -> float:
    """Share of replicates in which ``a`` outscores ``b``.

    Paired, and that is the point. Two fighters can have heavily overlapping
    marginal intervals and still differ in the same direction in every single
    replicate, because the thing that moves them is largely shared -- both
    careers are re-weighted by the same events. Comparing marginal intervals
    throws that pairing away and calls a real difference unresolved.
    """
    if a not in draws.index or b not in draws.index:
        return float("nan")
    x = draws.loc[a].to_numpy(dtype=float)
    y = draws.loc[b].to_numpy(dtype=float)
    usable = np.isfinite(x) & np.isfinite(y)
    if not usable.any():
        return float("nan")
    return float((x[usable] > y[usable]).mean())


def career_tiers(
    board: pd.DataFrame,
    draws: pd.DataFrame,
    *,
    confidence: float = 0.95,
    unranked_at_or_below: float | None = 0.0,
) -> pd.DataFrame:
    """Group the board into tiers it can actually defend, and say the rule.

    The problem this answers: the production 150-replicate bootstrap gives a
    median top-50 rank interval **157 places** wide. Jon Jones at [1, 2] is the
    only tight interval in the top twenty; the next narrowest is 17 wide.
    Publishing #6 and #14 as different numbers asserts a difference the data
    does not support, and publishing a 157-wide interval beside every rank is
    accurate but unreadable.

    **The rule, stated rather than implied.** Walk the board in descending
    mass. The first fighter opens tier 1 and is its *leader*. Each next fighter
    joins the current tier unless the tier's leader outscores them in at least
    ``confidence`` of replicates -- in which case that fighter opens the next
    tier and becomes its leader.

    So a tier means exactly one thing: **nobody in it is separated from the
    fighter at the top of it.** A tier boundary is a claim -- that the new
    leader is separated from the previous leader -- and it is the only claim the
    board makes about ordering.

    Two properties worth knowing before reading a tier:

    * The rule is anchored on the leader, not on neighbours. Chaining down a
      list of pairwise overlaps merges everything into one block, because
      "indistinguishable" is not transitive; anchoring makes each tier a
      statement about one named fighter.
    * Tiers are therefore not symmetric. A fighter can be separated from someone
      in their own tier -- just not from the leader. That is a real feature of
      the underlying uncertainty, not an artefact to be smoothed away.
    """
    if not 0.5 < float(confidence) < 1.0:
        raise ValueError("confidence must lie in (0.5, 1)")
    if board is None or board.empty:
        return pd.DataFrame(columns=TIER_COLUMNS)

    out = board.sort_values(["mass", "fighter"], ascending=[False, True]).reset_index(drop=True)
    at_floor = (
        pd.Series(False, index=out.index) if unranked_at_or_below is None
        else pd.to_numeric(out["mass"], errors="coerce").le(float(unranked_at_or_below))
    )
    ranked = out[~at_floor]

    tier_of: list[int] = []
    leader_of: list[str] = []
    prob_of: list[float] = []
    tier = 0
    leader: str | None = None
    for fighter in ranked["fighter"]:
        if leader is None:
            tier, leader = 1, fighter
            p = float("nan")
        else:
            p = separation_probability(draws, leader, fighter)
            if np.isfinite(p) and p >= float(confidence):
                tier += 1
                leader = fighter
        tier_of.append(tier)
        leader_of.append(leader)
        prob_of.append(p)

    tiered = ranked.assign(tier=tier_of, tier_leader=leader_of, p_below_tier_leader=prob_of)
    tiered["tier_label"] = "Tier " + tiered["tier"].astype(str)

    withheld = out[at_floor].assign(
        tier=pd.NA, tier_leader=pd.NA, p_below_tier_leader=float("nan"),
        tier_label=UNRANKED_TIER_LABEL,
    )
    joined = pd.concat([tiered, withheld], ignore_index=True, sort=False)
    for col in TIER_COLUMNS:
        if col not in joined.columns:
            joined[col] = pd.NA
    return joined[TIER_COLUMNS]


def tier_summary(tiers: pd.DataFrame) -> pd.DataFrame:
    """One row per tier: who leads it, how many are in it, and its mass span."""
    if tiers is None or tiers.empty:
        return pd.DataFrame(columns=["tier", "tier_label", "leader", "fighters",
                                     "mass_hi_edge", "mass_lo_edge"])
    ranked = tiers[tiers["tier"].notna()]
    rows = ranked.groupby("tier", sort=True).agg(
        tier_label=("tier_label", "first"),
        leader=("tier_leader", "first"),
        fighters=("fighter", "size"),
        mass_hi_edge=("mass", "max"),
        mass_lo_edge=("mass", "min"),
    ).reset_index()
    unranked = int(tiers["tier"].isna().sum())
    if unranked:
        rows.loc[len(rows)] = {
            "tier": pd.NA, "tier_label": UNRANKED_TIER_LABEL, "leader": pd.NA,
            "fighters": unranked, "mass_hi_edge": 0.0, "mass_lo_edge": 0.0,
        }
    return rows
