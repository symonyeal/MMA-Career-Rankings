"""Which bouts a rating is allowed to see, named rather than implied.

There are two non-UFC corpora in this project and they are not interchangeable:

``majors``
    ``build_sherdog_majors.py`` crawls PRIDE, WEC, Strikeforce, Affliction,
    Bellator and RIZIN **by event**, so it is roster-complete inside those six
    promotions and spans 1997-2026. It back-fills the early era.
``fightmatrix``
    a bounded crawl seeded from current FightMatrix rankings. It is
    roster-complete for nobody, and because the seeds are today's ranked
    fighters it back-fills the modern regional circuit.

Measured on the same functional and bar, they move the board in *opposite*
directions -- top-100 fighters still active in 2024: 70 UFC-only, 57 with
majors, 85 with FightMatrix. Anything that treats "cross-org" as one switch
will therefore get a result it cannot explain, which is why each scope is
named and nothing is merged unless the merge is asked for by name.

Two rules hold across every scope:

* **No organisation weight.** Relative promotion strength is an output of the
  joint fit, read off the fighters who crossed; a weight asserts the answer.
* **Ask for a scope and get it, or get an error.** A scope whose artifact is
  missing raises. Silently returning UFC-only and calling it a joint fit is how
  "cross-org makes no difference" became a believed result.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from project_helpers import bout_fingerprint

# scope name -> the snapshot artifact holding its non-UFC bouts
SCOPE_ARTIFACT: dict[str, str] = {
    "majors": "majors_fights.parquet",
    "fightmatrix": "fightmatrix_crossorg_fights.parquet",
    # UFC 1-27, dropped by the unified-rules cutoff. Admitted as a scope so the
    # decision is named and reversible; see :mod:`ratings.rules_era`.
    "pre_unified": "pre_unified_fights.parquet",
}
UFC_ONLY = "ufc"
ALL_SCOPES = "all"
DEFAULT_PUBLISHED_SCOPE = "majors,pre_unified"

# Merge order is by **source authority**, not alphabetical, because the dedupe
# guard keeps whichever copy of a bout arrives first.
#
# It matters. A Sherdog fighter page carries the subject's whole record, UFC
# bouts included, so the whole-career majors corpus contains 3,970 bouts that
# are already in `canonical_fights` and 153 of the 253 pre-unified UFC bouts.
# Merged alphabetically, `majors` lands before `pre_unified` and Sherdog's parse
# of a 1997 UFC bout beats UFCStats' own -- and the row then carries
# `source = "sherdog_majors"`, so `label_rules_era` calls it `non_ufc` and the
# rules-era term never reaches it. Both are wrong for the same reason: the
# authoritative parse should win.
SCOPE_MERGE_ORDER = ("pre_unified", "majors", "fightmatrix")
SCOPES = (UFC_ONLY, *SCOPE_MERGE_ORDER, ALL_SCOPES)
assert set(SCOPE_MERGE_ORDER) == set(SCOPE_ARTIFACT), "every scope needs a merge rank"


def scope_sources(scope: str) -> tuple[str, ...]:
    """The corpora one scope spec admits, in a stable merge order.

    A spec is a single name, ``all``, or a comma-separated list -- ``majors``,
    ``majors,pre_unified``, ``all``. Combining is spelled out on purpose: a
    reader of a run log can see exactly which corpora produced a board. The
    published default is itself the explicit spec ``majors,pre_unified``.

    The returned order is ``SCOPE_MERGE_ORDER``, whatever order the caller
    wrote them in, so a scope spec cannot decide which source's parse of a
    shared bout survives the dedupe guard.
    """
    parts = [p.strip() for p in str(scope).split(",") if p.strip()]
    if not parts:
        raise ValueError(f"empty scope {scope!r}; expected one of {', '.join(SCOPES)}")
    if ALL_SCOPES in parts:
        if len(parts) > 1:
            raise ValueError(f"scope {scope!r} combines {ALL_SCOPES!r} with a named scope")
        return SCOPE_MERGE_ORDER
    sources: list[str] = []
    for part in parts:
        if part == UFC_ONLY:
            continue
        if part not in SCOPE_ARTIFACT:
            raise ValueError(
                f"unknown scope {part!r}; expected one of {', '.join(SCOPES)} "
                "or a comma-separated combination of them")
        if part in sources:
            raise ValueError(f"scope {scope!r} names {part!r} twice")
        sources.append(part)
    return tuple(sorted(sources, key=SCOPE_MERGE_ORDER.index))


def staged_scope(snapshot_dir: Path) -> str:
    """The widest scope spec this snapshot can actually satisfy.

    ``all`` is a *request*, and a request for a corpus that was never staged
    raises, which is correct when a caller named it. The combined-table writer
    names nothing: it takes whatever corpora are present, so that the one
    authoritative artifact is as wide as the snapshot allows without a missing
    optional corpus turning a build into an error.
    """
    snapshot_dir = Path(snapshot_dir)
    present = [
        source for source in SCOPE_MERGE_ORDER
        if (snapshot_dir / SCOPE_ARTIFACT[source]).exists()
    ]
    return ",".join(present) if present else UFC_ONLY


def corpora_for_scope(scope: str) -> tuple[str, ...]:
    """The ``source_corpus`` labels one scope spec admits.

    :func:`scope_sources` names the non-UFC corpora a spec merges. The UFC table
    is the base of every scope and is never staged as an extension, so it does
    not appear there -- but it does appear in ``source_corpus``, which is what a
    row filter has to match. This is the bridge between the two: given a scope
    name, the exact set of corpus labels a row may carry.
    """
    return (UFC_ONLY, *scope_sources(scope))


def _missing_artifact_error(snapshot_dir: Path, source: str, path: Path) -> Exception:
    near = sorted(
        p.name for p in snapshot_dir.glob("*.parquet")
        if ("crossorg" in p.name or "majors" in p.name) and p.name != path.name
    )
    if source == "majors":
        hint = (" Stage it with loaders.majors_scope.stage_majors_scope(snapshot_dir), "
                "which needs data/external/sherdog/majors_bouts.parquet.")
    elif source == "pre_unified":
        hint = (" Stage it with ratings.rules_era.stage_pre_unified_scope(snapshot_dir), "
                "which reads the snapshot's own _excluded_bouts.csv.")
    else:
        hint = (f" The snapshot does carry {', '.join(near)}; stage one of those as "
                f"{path.name} to choose it explicitly." if near
                else " The snapshot carries no cross-org artifact at all; build one first.")
    return FileNotFoundError(
        f"scope {source!r} requested but {path} does not exist, so the run would "
        f"silently rate the UFC-only table and report it as a {source} result.{hint}"
    )


def scope_guard(
    extra: pd.DataFrame,
    ufc_fights: pd.DataFrame,
    *,
    source: str,
    strict: bool = True,
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Drop rows that are not what the scope claims to be, and say how many.

    Three ways a staged non-UFC table stops being one, all of them observed on
    real artifacts:

    ``org_is_ufc``
        Older depth-one artifacts carried UFC-labelled bouts in a table that
        was supposed to be cross-organisation only.
    ``already_in_ufc_table``
        19 of those were the *same bout* as a canonical row -- same pair, same
        date -- so admitting the scope updated those ratings twice, once at
        weight 1.0 and once at an org weight.
    ``contradictory_duplicate``
        the same bout arrives once per source perspective, and the perspectives
        do not always agree on who won. Keeping either row asserts a result the
        sources contradict; keeping both hands each fighter a win and a loss for
        one fight. The bout is dropped.

    This runs at the merge point every producer passes through, so a snapshot
    that was built before the producers were fixed is still safe to rate.
    """
    dropped: dict[str, int] = {}
    out = extra

    # The pre-unified scope is UFC bouts by definition -- they are separated
    # from the rated table by date, not by promotion -- so the "this says UFC
    # in a non-UFC table" check does not apply to it. The duplicate checks do.
    if "org" in out.columns and source != "pre_unified":
        is_ufc = out["org"].astype(str).str.strip().str.casefold().eq("ufc")
        if int(is_ufc.sum()):
            dropped["org_is_ufc"] = int(is_ufc.sum())
            out = out[~is_ufc]

    if not out.empty and {"fighter_a", "fighter_b", "event_date"} <= set(out.columns):
        seen = set(bout_fingerprint(ufc_fights))
        duplicate = bout_fingerprint(out).isin(seen)
        if int(duplicate.sum()):
            dropped["already_in_ufc_table"] = int(duplicate.sum())
            out = out[~duplicate]

        out = out.assign(_fp=bout_fingerprint(out))
        repeated = out["_fp"].duplicated(keep=False)
        if int(repeated.sum()):
            # Only a row that names a winner can contradict another. A draw, a
            # no-contest or an overturned result asserts nothing, so it is a
            # redundant row, not a conflicting one -- Sakuraba beat Silveira at
            # UFC Japan 1997 in a rematch held later on the same card, after
            # their first bout that night was overturned, and both rows are
            # real.
            winners = out.loc[repeated].groupby("_fp")["winner"].nunique(dropna=True)
            contradictory = set(winners[winners > 1].index)
            if contradictory:
                mask = out["_fp"].isin(contradictory)
                dropped["contradictory_duplicate"] = int(mask.sum())
                out = out[~mask]
            # Keep the row that carries the most information: a rateable,
            # decided result ahead of an excluded or undecided one.
            #
            # Limitation, stated rather than hidden: two genuine bouts between
            # the same pair on the same day are indistinguishable from a
            # duplicate at this key, so a same-night tournament rematch is
            # collapsed to one row. That is rare and confined to 1990s cards.
            order = out.assign(
                _decisive=out["winner"].notna().astype(int),
                _rateable=(~out.get("is_excluded", pd.Series(False, index=out.index))
                           .fillna(False).astype(bool)).astype(int),
            ).sort_values(["_fp", "_rateable", "_decisive"], ascending=[True, False, False],
                          kind="mergesort")
            redundant_ids = order.index[order["_fp"].duplicated(keep="first")]
            if len(redundant_ids):
                dropped["repeated_in_source_table"] = int(len(redundant_ids))
                out = out.drop(index=redundant_ids)
        out = out.drop(columns="_fp")

    if out.empty and strict:
        raise ValueError(
            f"scope {source!r} requested but every staged bout failed the scope guard "
            f"({dropped}), so the run would silently rate the UFC-only table."
        )
    return out.reset_index(drop=True), dropped


def merge_scope(
    fights: pd.DataFrame,
    snapshot_dir: Path,
    *,
    scope: str,
    label: str = "scope",
) -> pd.DataFrame:
    """Merge every corpus one scope name admits, or refuse loudly."""
    snapshot_dir = Path(snapshot_dir)
    sources = scope_sources(scope)
    if not sources:
        staged = [name for name in SCOPE_ARTIFACT.values()
                  if (snapshot_dir / name).exists()]
        if staged:
            print(f"[{label}] UFC-only scope; {', '.join(staged)} not admitted")
        return fights

    merged = fights
    for source in sources:
        path = snapshot_dir / SCOPE_ARTIFACT[source]
        if not path.exists():
            raise _missing_artifact_error(snapshot_dir, source, path)
        extra = pd.read_parquet(path)
        if extra.empty:
            raise ValueError(
                f"scope {source!r} requested but {path} holds zero bouts, so the run "
                "would silently rate the UFC-only table and report it as a joint fit."
            )
        if "org_weight" not in extra.columns:
            extra["org_weight"] = 1.0
        if "source" not in extra.columns:
            extra["source"] = source
        extra, dropped = scope_guard(extra, merged, source=source)
        merged = pd.concat([merged, extra], ignore_index=True, sort=False)
        orgs = sorted(extra.get("org", pd.Series(dtype=str)).dropna().unique())
        print(f"[{label}] scope {source}: merged {len(extra):,} bouts (orgs: {orgs})")
        if dropped:
            print(f"[{label}] scope {source}: guard dropped "
                  f"{sum(dropped.values()):,} rows: {dropped}")
    return merged
