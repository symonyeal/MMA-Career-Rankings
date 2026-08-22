"""Fighters whose record outside the UFC does not survive contact with it.

There is no organization weight in this engine, and there should not be: a
promotion's level is an *output* of one joint fit, read off the fighters who
crossed between them. But "it emerges from the bridges" is a claim that has to be
checkable, and this module is the check.

The signature is not "won a lot outside, lost inside" -- everyone's UFC
opposition is stronger, so that alone means nothing. It is a *transfer* failure:
the strength implied by the outside record does not predict the inside one.

``transfer_test`` fits one Bradley-Terry strength to a fighter's results against
rated opponents outside the UFC and another to their results inside it, and
reports the gap with its standard error. Conditioning on each opponent
individually is what makes it trustworthy, because only about 65% of a fighter's
outside opponents are rated at all against 100% of their inside ones -- any
measure built on *mean* opponent rating compares two differently-selected pools.
An earlier version of this module did exactly that and got the headline case
backwards; see the note in ``crossover_profile``.

Patchy Mix is the case that names the class, and also the case that shows why
the uncertainty has to travel with the estimate. Sherdog indexes him under his
legal name ``Patrick Mix``: 11-1 outside the UFC through Kyoji Horiguchi,
Sergio Pettis, Raufeon Stots and James Gallagher, then 0-2 inside it. His
implied outside strength is ~1730; his inside record is winless, so without a
prior it has no interior maximum at all. The virtual games below give it one,
heavily shrunk and loosely pinned -- which is the honest reading of two bouts,
however lopsided the story sounds.

Aggregated over a promotion's crossovers the same gap becomes an org-level
estimate produced as an output rather than assumed as a weight, and it is the
gate the joint fit must clear: a fit never told about promotions should
reproduce these gaps by itself. Read them beside bridge density, which varies
roughly thirty-fold across promotion-eras (Zuffa-era WEC has 35% of bouts with
both fighters UFC-rated; RIZIN after 2020 has 1%).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from project_helpers import normalize_name_key
from ratings.constants import WHR_VIRTUAL_GAMES

_ELO_ANCHOR = 1500.0

# A side with fewer rated opponents than this is described but not screened:
# there is nothing to condition on.
MIN_RATED_OPPONENTS = 2


def _rating_lookup(history: pd.DataFrame, mu_col: str = "mu_whr") -> dict[str, np.ndarray]:
    frame = history[["fighter", "event_date", mu_col]].copy()
    frame["event_date"] = pd.to_datetime(frame["event_date"])
    frame = frame.sort_values(["fighter", "event_date"])
    return {name: group[["event_date", mu_col]].to_numpy()
            for name, group in frame.groupby("fighter")}


def _rating_at(lookup: dict[str, np.ndarray], name: str, when) -> float:
    arr = lookup.get(name)
    if arr is None or len(arr) == 0:
        return np.nan
    dates = np.array([np.datetime64(d) for d in arr[:, 0]])
    idx = int(np.searchsorted(dates, np.datetime64(when), side="right")) - 1
    return float(arr[max(idx, 0), 1])


def _long(bouts: pd.DataFrame) -> pd.DataFrame:
    """One row per fighter-appearance: fighter, opponent, outcome, date, org."""
    keep = [c for c in ("event_date", "org") if c in bouts.columns]
    left = bouts[["fighter_a", "fighter_b", "fighter_a_outcome", *keep]].rename(
        columns={"fighter_a": "fighter", "fighter_b": "opponent",
                 "fighter_a_outcome": "outcome"})
    right = bouts[["fighter_b", "fighter_a", "fighter_b_outcome", *keep]].rename(
        columns={"fighter_b": "fighter", "fighter_a": "opponent",
                 "fighter_b_outcome": "outcome"})
    return pd.concat([left, right], ignore_index=True)


def _side_stats(frame: pd.DataFrame, lookup, ratings_by_key) -> dict:
    if frame.empty:
        return {"bouts": 0, "wins": 0, "losses": 0, "win_rate": np.nan,
                "rated_opponents": 0, "mean_opponent_rating": np.nan}
    outcome = frame["outcome"].astype(str).str.lower()
    wins = int(outcome.str.startswith("w").sum())
    losses = int(outcome.str.startswith("l").sum())
    rated = []
    for opp, when in zip(frame["opponent"], frame["event_date"]):
        key = normalize_name_key(str(opp), compact=True)
        canonical = ratings_by_key.get(key)
        if canonical is None:
            continue
        value = _rating_at(lookup, canonical, when)
        if np.isfinite(value):
            rated.append(value)
    return {
        "bouts": int(len(frame)),
        "wins": wins,
        "losses": losses,
        "win_rate": (wins / (wins + losses)) if (wins + losses) else np.nan,
        "rated_opponents": len(rated),
        "mean_opponent_rating": float(np.mean(rated)) if rated else np.nan,
    }


def crossover_profile(
    crossorg_bouts: pd.DataFrame,
    canonical_fights: pd.DataFrame,
    ratings_history: pd.DataFrame,
    *,
    mu_col: str = "mu_whr",
) -> pd.DataFrame:
    """Descriptive record summary per fighter with bouts on both sides.

    This is a reporting frame, not the screen -- use ``transfer_test`` for that.

    ``crossorg_bouts`` must already carry canonical fighter names (run it
    through ``loaders.crossorg_identity.apply_identity_map`` first), or a
    fighter's two halves stay two people and nothing here can see them.
    """
    lookup = _rating_lookup(ratings_history, mu_col=mu_col)
    ratings_by_key = {normalize_name_key(n, compact=True): n for n in lookup}

    outside = _long(crossorg_bouts.assign(
        event_date=pd.to_datetime(crossorg_bouts["event_date"], errors="coerce")
    )).dropna(subset=["fighter", "opponent", "event_date"])

    ufc = canonical_fights
    if "is_excluded" in ufc.columns:
        ufc = ufc[~ufc["is_excluded"].fillna(False)]
    inside = _long(ufc.assign(
        event_date=pd.to_datetime(ufc["event_date"], errors="coerce")
    )).dropna(subset=["fighter", "opponent", "event_date"])

    both = set(outside["fighter"]) & set(inside["fighter"])
    rows = []
    for name in sorted(both):
        out_side = outside[outside["fighter"].eq(name)]
        in_side = inside[inside["fighter"].eq(name)]
        o, i = (_side_stats(out_side, lookup, ratings_by_key),
                _side_stats(in_side, lookup, ratings_by_key))
        orgs = out_side["org"].dropna() if "org" in out_side else pd.Series(dtype=str)
        rows.append({
            "fighter": name,
            "main_outside_org": orgs.mode().iat[0] if not orgs.empty else None,
            "outside_bouts": o["bouts"], "outside_w": o["wins"], "outside_l": o["losses"],
            "outside_win_rate": o["win_rate"],
            "outside_rated_opponents": o["rated_opponents"],
            "outside_opponent_rating": o["mean_opponent_rating"],
            "ufc_bouts": i["bouts"], "ufc_w": i["wins"], "ufc_l": i["losses"],
            "ufc_win_rate": i["win_rate"],
            "ufc_rated_opponents": i["rated_opponents"],
            "ufc_opponent_rating": i["mean_opponent_rating"],
        })

    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out["win_rate_drop"] = out["outside_win_rate"] - out["ufc_win_rate"]
    # NOTE: a "rating inversion" column (mean outside opponent rating minus mean
    # inside) used to live here as the aberration screen. It was removed after it
    # failed on the case it was built for: Patchy Mix's two UFC opponents rate
    # *above* his rated Bellator ones, giving him an inversion of -118 and a
    # clean bill of health. Comparing mean opponent ratings cannot separate "beat
    # better opponents" from "faced fewer weak ones", because only ~65% of a
    # fighter's outside opponents are rated at all against 100% inside. Use
    # ``transfer_test``, which conditions on each opponent individually.
    out["measurable"] = (
        (out["outside_rated_opponents"] >= MIN_RATED_OPPONENTS)
        & (out["ufc_rated_opponents"] >= MIN_RATED_OPPONENTS)
    )
    return out.sort_values(["measurable", "win_rate_drop"], ascending=[False, False])


def _implied_strength(
    results: list[tuple[float, float]],
    *,
    virtual_games: float = WHR_VIRTUAL_GAMES,
    anchor: float = _ELO_ANCHOR,
) -> tuple[float, float]:
    """Regularized strength and its standard error from (opponent_rating, won) pairs.

    Newton on the Bradley-Terry log-likelihood with the Elo scale, so opponent
    quality is handled exactly rather than by averaging ratings.

    ``virtual_games`` matters more here than anywhere else in this module. An
    undefeated or winless record has no interior maximum, and **52% of crossovers
    have one on at least one side** -- systematically the dominant-outside
    fighters, who are exactly the ones a transfer test is looking for. Dropping
    them biases the aggregate toward "no effect"; keeping their boundary
    estimates fills it with clipped nonsense. Both mistakes were made before this
    prior was added, in opposite directions, on the same data.

    So every fighter carries the same prior evidence the WHR estimator already
    gives them: half a win and half a loss per virtual game against an average
    opponent, which makes the likelihood strictly concave and every gap finite.
    """
    if not results:
        return np.nan, np.inf
    scale = 400.0 / np.log(10.0)
    opponents = np.array([r for r, _ in results], dtype=float)
    wins = np.array([w for _, w in results], dtype=float)
    if virtual_games > 0:
        half = float(virtual_games) / 2.0
        opponents = np.concatenate([opponents, [anchor, anchor]])
        wins = np.concatenate([wins, [1.0, 0.0]])
        weights = np.concatenate([np.ones(len(results)), [half, half]])
    else:
        weights = np.ones(len(results))

    theta = float(opponents.mean())
    for _ in range(60):
        p = 1.0 / (1.0 + np.exp(-(theta - opponents) / scale))
        gradient = float(np.sum(weights * (wins - p))) / scale
        information = float(np.sum(weights * p * (1.0 - p))) / (scale ** 2)
        if information <= 1e-12:
            break
        step = gradient / information
        theta += max(min(step, 400.0), -400.0)
        if abs(step) < 1e-6:
            break
    p = 1.0 / (1.0 + np.exp(-(theta - opponents) / scale))
    information = float(np.sum(weights * p * (1.0 - p))) / (scale ** 2)
    stderr = float(np.sqrt(1.0 / information)) if information > 1e-12 else np.inf
    bound = float(opponents.mean()) + 800.0
    return float(np.clip(theta, opponents.mean() - 800.0, bound)), stderr


def transfer_test(
    crossorg_bouts: pd.DataFrame,
    canonical_fights: pd.DataFrame,
    ratings_history: pd.DataFrame,
    *,
    mu_col: str = "mu_whr",
    min_bouts_each_side: int = 2,
) -> pd.DataFrame:
    """Does a fighter's form outside the UFC predict their form inside it?

    Fit one strength to their outside results and one to their inside results,
    each against rated opponents only, and report the gap with its standard
    error. This is the measure that survives the objection the simpler ones do
    not: opponent quality is conditioned on exactly, so it does not matter that
    only the stronger outside opponents are rated at all.

    The uncertainty is the point. Patchy Mix has twenty-five bouts outside and
    **two** inside, so however lopsided the story reads, two bouts cannot carry
    a confident verdict -- and a method that claimed otherwise would be wrong.
    Aggregated over a promotion's crossovers, though, the same gap becomes the
    org-level estimate, produced as an output instead of assumed as a weight.
    """
    lookup = _rating_lookup(ratings_history, mu_col=mu_col)
    ratings_by_key = {normalize_name_key(n, compact=True): n for n in lookup}

    def rated_results(frame: pd.DataFrame) -> list[tuple[float, float]]:
        out = []
        for opp, when, outcome in zip(frame["opponent"], frame["event_date"],
                                      frame["outcome"].astype(str).str.lower()):
            if not (outcome.startswith("w") or outcome.startswith("l")):
                continue
            canonical = ratings_by_key.get(normalize_name_key(str(opp), compact=True))
            if canonical is None:
                continue
            value = _rating_at(lookup, canonical, when)
            if np.isfinite(value):
                out.append((value, 1.0 if outcome.startswith("w") else 0.0))
        return out

    outside = _long(crossorg_bouts.assign(
        event_date=pd.to_datetime(crossorg_bouts["event_date"], errors="coerce")
    )).dropna(subset=["fighter", "opponent", "event_date"])
    ufc = canonical_fights
    if "is_excluded" in ufc.columns:
        ufc = ufc[~ufc["is_excluded"].fillna(False)]
    inside = _long(ufc.assign(
        event_date=pd.to_datetime(ufc["event_date"], errors="coerce")
    )).dropna(subset=["fighter", "opponent", "event_date"])

    rows = []
    for name in sorted(set(outside["fighter"]) & set(inside["fighter"])):
        out_side = outside[outside["fighter"].eq(name)]
        results_out = rated_results(out_side)
        results_in = rated_results(inside[inside["fighter"].eq(name)])
        if len(results_out) < min_bouts_each_side or len(results_in) < min_bouts_each_side:
            continue
        theta_out, se_out = _implied_strength(results_out)
        theta_in, se_in = _implied_strength(results_in)
        gap = theta_out - theta_in
        se = float(np.sqrt(se_out ** 2 + se_in ** 2))
        orgs = out_side["org"].dropna() if "org" in out_side else pd.Series(dtype=str)
        rows.append({
            "fighter": name,
            "main_outside_org": orgs.mode().iat[0] if not orgs.empty else None,
            "rated_bouts_outside": len(results_out),
            "rated_bouts_inside": len(results_in),
            "implied_strength_outside": theta_out,
            "implied_strength_inside": theta_in,
            "transfer_gap": gap,
            "transfer_gap_se": se,
            "z": gap / se if np.isfinite(se) and se > 0 else np.nan,
        })
    out = pd.DataFrame(rows)
    return out.sort_values("z", ascending=False) if not out.empty else out


def aberrations(transfer: pd.DataFrame, *, min_z: float = 1.96) -> pd.DataFrame:
    """Crossovers whose outside form is not merely better but *inconsistent*.

    Screened on the z of the gap, not its size, so a huge gap resting on two
    bouts does not outrank a moderate one resting on twenty.
    """
    if transfer.empty:
        return transfer
    return transfer[transfer["z"].ge(min_z)].sort_values("z", ascending=False)


def promotion_summary(transfer: pd.DataFrame) -> pd.DataFrame:
    """Per promotion, how far its crossovers' form falls short inside the UFC.

    This is the org-level question answered as an **output** rather than assumed
    as a weight, and it is the gate the joint fit has to clear: if a fit that was
    never told about promotions cannot reproduce these gaps, it is not seeing
    what the records plainly show.

    Read it beside the bridge density for that promotion-era -- a gap estimated
    from eighteen crossovers is not the same object as one from a hundred.
    """
    if transfer.empty:
        return transfer
    usable = transfer[transfer["main_outside_org"].notna() & np.isfinite(transfer["z"])]
    grouped = usable.groupby("main_outside_org").agg(
        crossovers=("fighter", "size"),
        median_gap=("transfer_gap", "median"),
        mean_gap=("transfer_gap", "mean"),
        sd=("transfer_gap", "std"),
    )
    stderr = grouped["sd"] / np.sqrt(grouped["crossovers"])
    grouped["ci_lo"] = grouped["mean_gap"] - 1.96 * stderr
    grouped["ci_hi"] = grouped["mean_gap"] + 1.96 * stderr
    grouped["resolved"] = (grouped["ci_lo"] > 0) | (grouped["ci_hi"] < 0)
    return grouped.drop(columns="sd").sort_values("mean_gap", ascending=False)
