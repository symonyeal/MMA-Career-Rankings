"""Resolve Sherdog fighter ids to one canonical identity per person.

Cross-org bouts arrive keyed by Sherdog's numeric fighter id, which is a better
identifier than any name -- but the rating engine keys on the canonical UFC
fighter name, so the two have to be joined before a PRIDE bout can sit in the
same likelihood as a UFC one.

The join is deliberately conservative, and the reason is measured: the
"surname + shared initial" tier of ``crossorg_identity_audit`` is dominated by
siblings who all fight -- Murilo and Mauricio Rua, Patricky and Patricio Freire,
Kanna and Kai Asakura. Any rule loose enough to catch the genuine variants merges
brothers into one fighter, which would corrupt exactly the historical careers the
whole-sport scope exists to measure. So:

* an **exact normalized-name key** match, or
* an entry in ``data/external/crossorg/identity_overrides.csv``, hand-verified,
  which is where ring names live because no name rule can derive
  ``Ronaldo Souza`` -> ``Jacare Souza``.

Nothing else joins. A fighter who matches neither keeps their Sherdog name as
their own canonical identity: they are still rated, still constrain their
opponents, and simply are not asserted to be someone already in the UFC set.

Two ids claiming one canonical name is a **collision**, reported and left
unjoined rather than silently merged -- that is the shape a sibling error takes.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from project_helpers import normalize_name_key

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OVERRIDES_PATH = PROJECT_ROOT / "data" / "external" / "crossorg" / "identity_overrides.csv"


def load_overrides(path: Path = OVERRIDES_PATH) -> dict[str, str]:
    """``sherdog_name -> canonical_name``, hand-verified only."""
    if not path.exists():
        return {}
    frame = pd.read_csv(path)
    return {
        normalize_name_key(str(r.sherdog_name), compact=True): str(r.canonical_name)
        for r in frame.itertuples()
        if isinstance(r.sherdog_name, str) and isinstance(r.canonical_name, str)
    }


def sherdog_names(bouts: pd.DataFrame) -> pd.Series:
    """One display name per Sherdog id, taking the most common spelling."""
    stacked = pd.concat([
        bouts[["fighter_a_id", "fighter_a"]].rename(
            columns={"fighter_a_id": "sherdog_id", "fighter_a": "name"}),
        bouts[["fighter_b_id", "fighter_b"]].rename(
            columns={"fighter_b_id": "sherdog_id", "fighter_b": "name"}),
    ]).dropna(subset=["sherdog_id", "name"])
    return stacked.groupby("sherdog_id")["name"].agg(lambda s: s.mode().iat[0])


def build_identity_map(
    bouts: pd.DataFrame,
    core_names: list[str],
    *,
    overrides: dict[str, str] | None = None,
) -> pd.DataFrame:
    """One row per Sherdog id: the canonical identity it will be rated under."""
    overrides = load_overrides() if overrides is None else overrides
    core_by_key = {normalize_name_key(n, compact=True): n for n in core_names
                   if isinstance(n, str)}

    names = sherdog_names(bouts)
    rows = []
    for sherdog_id, name in names.items():
        key = normalize_name_key(name, compact=True)
        override = overrides.get(key)
        if override is not None:
            rows.append((sherdog_id, name, override, "override"))
        elif key in core_by_key:
            rows.append((sherdog_id, name, core_by_key[key], "name_key"))
        else:
            rows.append((sherdog_id, name, name, "unjoined"))

    out = pd.DataFrame(rows, columns=["sherdog_id", "sherdog_name",
                                      "canonical_name", "join_method"])

    # Two ids claiming one canonical identity is either a sibling merge or a
    # plain namesake -- Sherdog carries two Eddie Alvarezes and two Anderson
    # Silvas, distinguished only by id. Refuse both rather than guess.
    joined = out[out["join_method"].ne("unjoined")]
    clashes = joined["canonical_name"].value_counts()
    clashes = set(clashes[clashes > 1].index)
    collided = out["canonical_name"].isin(clashes) & out["join_method"].ne("unjoined")
    out.loc[collided, "join_method"] = "collision"
    out.loc[collided, "canonical_name"] = out.loc[collided, "sherdog_name"]

    # Refusing to join is not enough: two different people whose names are the
    # same string would still be rated as one fighter. Anything not joined to a
    # core identity is suffixed with its Sherdog id wherever its name is not
    # unique, so distinct people stay distinct all the way into the likelihood.
    return _disambiguate(out)


def _disambiguate(identity: pd.DataFrame) -> pd.DataFrame:
    out = identity.copy()
    ambiguous = out["canonical_name"].value_counts()
    ambiguous = set(ambiguous[ambiguous > 1].index)
    needs_suffix = out["canonical_name"].isin(ambiguous) & out["join_method"].isin(
        {"unjoined", "collision"}
    )
    out.loc[needs_suffix, "canonical_name"] = (
        out.loc[needs_suffix, "canonical_name"]
        + " (sherdog:" + out.loc[needs_suffix, "sherdog_id"].astype(str) + ")"
    )
    return out


def resolve_collisions(
    identity: pd.DataFrame,
    bouts: pd.DataFrame,
    canonical_fights: pd.DataFrame,
    *,
    min_matches: int = 2,
) -> pd.DataFrame:
    """Award a contested name to the id whose record actually contains it.

    Refusing every namesake is safe but costs the real fighter their history --
    unjoining both Eddie Alvarezes loses the one who fought in the UFC. Names
    cannot break the tie, so use evidence: a fighter page carries the subject's
    *whole* record, UFC bouts included, so the genuine claimant is the id whose
    bout dates line up with the canonical UFC record for that name. The impostor
    has no such overlap and stays unjoined.
    """
    out = identity.copy()
    contested = out.loc[out["join_method"].eq("collision")]
    if contested.empty or canonical_fights.empty:
        return out

    fights = canonical_fights.copy()
    fights["event_date"] = pd.to_datetime(fights["event_date"], errors="coerce")
    ufc_dates: dict[str, set] = {}
    for side in ("fighter_a", "fighter_b"):
        for name, group in fights.groupby(side):
            ufc_dates.setdefault(name, set()).update(group["event_date"].dropna())

    dates = bouts.copy()
    dates["event_date"] = pd.to_datetime(dates["event_date"], errors="coerce")
    by_id: dict[str, set] = {}
    for col in ("fighter_a_id", "fighter_b_id"):
        for fid, group in dates.groupby(col):
            by_id.setdefault(fid, set()).update(group["event_date"].dropna())

    # Recover which canonical name each contested id was claiming.
    core_claim = dict(zip(contested["sherdog_id"], contested["sherdog_name"]))
    for claimed, group in contested.groupby(
        contested["sherdog_id"].map(core_claim).map(lambda n: normalize_name_key(n, compact=True))
    ):
        candidates = {}
        for fid in group["sherdog_id"]:
            target = next((n for n in ufc_dates
                           if normalize_name_key(n, compact=True) == claimed), None)
            if target is None:
                continue
            candidates[fid] = (len(by_id.get(fid, set()) & ufc_dates[target]), target)
        if not candidates:
            continue
        best_id, (best_n, target) = max(candidates.items(), key=lambda kv: kv[1][0])
        runner_up = sorted((v[0] for k, v in candidates.items() if k != best_id), reverse=True)
        if best_n >= min_matches and (not runner_up or best_n > runner_up[0]):
            mask = out["sherdog_id"].eq(best_id)
            out.loc[mask, "canonical_name"] = target
            out.loc[mask, "join_method"] = "collision_resolved"
    return out


def apply_identity_map(bouts: pd.DataFrame, identity: pd.DataFrame) -> pd.DataFrame:
    """Add canonical ``fighter_a``/``fighter_b`` names to cross-org bouts."""
    mapping = dict(zip(identity["sherdog_id"], identity["canonical_name"]))
    out = bouts.copy()
    out["fighter_a"] = out["fighter_a_id"].map(mapping)
    out["fighter_b"] = out["fighter_b_id"].map(mapping)
    return out.dropna(subset=["fighter_a", "fighter_b"])


def _opponent_key(name: object) -> str:
    return normalize_name_key(str(name), compact=True) if isinstance(name, str) else ""


def _bout_fingerprints(bouts: pd.DataFrame) -> dict[str, set[tuple]]:
    """Per Sherdog id, the set of (date, opponent-key) pairs on their record."""
    frame = bouts.copy()
    frame["_d"] = pd.to_datetime(frame["event_date"], errors="coerce")
    out: dict[str, set[tuple]] = {}
    for own, opp in (("fighter_a_id", "fighter_b"), ("fighter_b_id", "fighter_a")):
        sub = frame[[own, opp, "_d"]].dropna()
        for fid, name, date in sub.itertuples(index=False):
            out.setdefault(fid, set()).add((date.normalize(), _opponent_key(name)))
    return out


def _canonical_fingerprints(fights: pd.DataFrame) -> dict[str, set[tuple]]:
    frame = fights.copy()
    frame["_d"] = pd.to_datetime(frame["event_date"], errors="coerce")
    out: dict[str, set[tuple]] = {}
    for own, opp in (("fighter_a", "fighter_b"), ("fighter_b", "fighter_a")):
        sub = frame[[own, opp, "_d"]].dropna()
        for name, other, date in sub.itertuples(index=False):
            out.setdefault(name, set()).add((date.normalize(), _opponent_key(other)))
    return out


def _overlap(a: set[tuple], b: set[tuple], *, day_slack: int = 1) -> int:
    """Shared (date, opponent) pairs, tolerating the known +/-1 day date drift."""
    if not a or not b:
        return 0
    by_opp: dict[str, list] = {}
    for date, opp in b:
        by_opp.setdefault(opp, []).append(date)
    hits = 0
    for date, opp in a:
        for other in by_opp.get(opp, ()):
            if abs((date - other).days) <= day_slack:
                hits += 1
                break
    return hits


def resolve_by_bout_evidence(
    identity: pd.DataFrame,
    bouts: pd.DataFrame,
    canonical_fights: pd.DataFrame,
    *,
    min_overlap: int = 2,
) -> pd.DataFrame:
    """Join the remaining ids on shared bouts rather than on their names.

    Names are the weakest evidence available and the tier that holds the real
    variants is the same tier that holds siblings. Bouts are far stronger: a
    Sherdog fighter page carries the subject's *whole* record, UFC bouts
    included, so if an id and a canonical fighter share two or more
    (date, opponent) pairs they are the same person, whatever they are called.

    This is what recovers the cases that matter most. Sherdog indexes the
    Bellator bantamweight champion under his legal name ``Patrick Mix`` while the
    canonical set calls him ``Patchy Mix``; no name rule joins those without also
    merging brothers, and leaving them apart splits an 11-1 record outside the
    UFC from an 0-2 record inside it -- destroying the single most informative
    thing the whole-sport scope was built to see.

    Siblings fall out for free: Murilo Rua's record shares no bout with Mauricio
    Rua's, so the overlap is zero and nothing is joined.
    """
    out = identity.copy()
    pending = out["join_method"].isin({"unjoined", "collision"})
    if not pending.any() or canonical_fights.empty:
        return out

    claimed = set(out.loc[~pending, "canonical_name"])
    fingerprints = _bout_fingerprints(bouts)
    canonical = {k: v for k, v in _canonical_fingerprints(canonical_fights).items()
                 if k not in claimed}

    awards: dict[str, tuple[str, int]] = {}
    for fid in out.loc[pending, "sherdog_id"]:
        mine = fingerprints.get(fid)
        if not mine:
            continue
        scored = [(name, _overlap(mine, prints))
                  for name, prints in canonical.items()]
        scored = [s for s in scored if s[1] >= min_overlap]
        if not scored:
            continue
        scored.sort(key=lambda kv: kv[1], reverse=True)
        if len(scored) > 1 and scored[0][1] == scored[1][1]:
            continue  # ambiguous; leave it for a human
        name, score = scored[0]
        if name not in awards or score > awards[name][1]:
            awards[name] = (fid, score)

    for name, (fid, _score) in awards.items():
        mask = out["sherdog_id"].eq(fid)
        out.loc[mask, "canonical_name"] = name
        out.loc[mask, "join_method"] = "bout_evidence"
    return _disambiguate(out)


def summary(identity: pd.DataFrame) -> dict:
    counts = identity["join_method"].value_counts()
    return {
        "fighters": int(len(identity)),
        "by_method": {str(k): int(v) for k, v in counts.items()},
        "joined_to_core": int(counts.get("name_key", 0) + counts.get("override", 0)),
        "collisions": identity.loc[identity["join_method"].eq("collision"),
                                   "sherdog_name"].tolist()[:40],
    }
