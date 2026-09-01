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

from project_helpers import bout_fingerprint, normalize_name_key

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
CANONICAL_DATE_DRIFT_DAYS = 1

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


def _winner_key(winner: object) -> str | None:
    """Winner identity in exactly the namespace used by bout fingerprints."""
    if not isinstance(winner, str):
        return None
    return normalize_name_key(winner, compact=True) or None


def _pair_key(fights: pd.DataFrame) -> pd.Series:
    """Order-independent fighter identity without the date component."""
    if fights.empty:
        return pd.Series(index=fights.index, dtype=object)
    return pd.Series(
        [
            "::".join(
                sorted(
                    [
                        normalize_name_key(a, compact=True),
                        normalize_name_key(b, compact=True),
                    ]
                )
            )
            for a, b in zip(fights["fighter_a"], fights["fighter_b"])
        ],
        index=fights.index,
        dtype=object,
    )


def _result_key(fights: pd.DataFrame) -> pd.Series:
    """Comparable decided result, including draws and no-contests."""
    winner = fights.get("winner", pd.Series(pd.NA, index=fights.index)).map(_winner_key)
    result = winner.map(lambda value: f"winner::{value}" if value else pd.NA)
    draws = fights.get("is_draw", pd.Series(False, index=fights.index)).fillna(False).astype(bool)
    no_contests = fights.get("is_nc", pd.Series(False, index=fights.index)).fillna(False).astype(bool)
    result.loc[draws] = "draw"
    result.loc[no_contests] = "no_contest"
    return result


def canonical_date_drift_matches(
    extra: pd.DataFrame,
    prior: pd.DataFrame,
    *,
    day_slack: int = CANONICAL_DATE_DRIFT_DAYS,
) -> pd.DataFrame:
    """Match a lower-source copy whose UFC date crossed midnight.

    The completed Sherdog career crawl carries UFC bouts from fighter pages.
    Nine international UFC cards in the 2026-08-13 snapshot use the local date
    there and the preceding date in UFCStats, leaving 99 physical bouts in the
    likelihood twice. Pair and date proximity alone is unsafe: the same corpus
    also holds real consecutive-day tournament rematches. A match therefore
    requires the same normalized pair and result, a one-day difference, and
    exactly one canonical UFC source row. Distinct non-UFC event sessions are
    left alone even when the same fighter wins both bouts.

    The returned indices are evidence pairs rather than only a drop mask so the
    combined-table builder can preserve the losing corpus in
    ``available_in_corpora`` on the surviving canonical row.
    """
    columns = ["extra_index", "prior_index"]
    required = {"fighter_a", "fighter_b", "event_date", "source"}
    if day_slack < 1 or extra.empty or prior.empty:
        return pd.DataFrame(columns=columns)
    if not required <= set(extra.columns) or not required <= set(prior.columns):
        return pd.DataFrame(columns=columns)

    left = pd.DataFrame(
        {
            "extra_index": extra.index,
            "_pair": _pair_key(extra),
            "_result": _result_key(extra),
            "_extra_date": pd.to_datetime(extra["event_date"], errors="coerce"),
            "_extra_source": extra["source"].fillna("").astype(str).str.strip().str.casefold(),
        },
        index=extra.index,
    )
    right = pd.DataFrame(
        {
            "prior_index": prior.index,
            "_pair": _pair_key(prior),
            "_result": _result_key(prior),
            "_prior_date": pd.to_datetime(prior["event_date"], errors="coerce"),
            "_prior_source": prior["source"].fillna("").astype(str).str.strip().str.casefold(),
        },
        index=prior.index,
    )
    left = left.dropna(subset=["_result", "_extra_date"])
    right = right.dropna(subset=["_result", "_prior_date"])
    if left.empty or right.empty:
        return pd.DataFrame(columns=columns)

    candidates = left.merge(right, on=["_pair", "_result"], how="inner")
    gap = (candidates["_extra_date"] - candidates["_prior_date"]).abs().dt.days
    one_canonical = candidates["_extra_source"].eq("ufc") ^ candidates[
        "_prior_source"
    ].eq("ufc")
    matched = candidates[gap.between(1, day_slack, inclusive="both") & one_canonical]
    # If either side could refer to two rows, proximity did not identify a
    # one-to-one physical fight. Preserve the whole ambiguity for review.
    matches_per_extra = matched.groupby("extra_index")["prior_index"].nunique()
    matches_per_prior = matched.groupby("prior_index")["extra_index"].nunique()
    unambiguous_extra = set(matches_per_extra[matches_per_extra.eq(1)].index)
    unambiguous_prior = set(matches_per_prior[matches_per_prior.eq(1)].index)
    matched = matched[
        matched["extra_index"].isin(unambiguous_extra)
        & matched["prior_index"].isin(unambiguous_prior)
    ]
    return (
        matched[columns]
        .drop_duplicates()
        .sort_values(columns, kind="mergesort")
        .reset_index(drop=True)
    )


def bout_dedupe_key(
    fights: pd.DataFrame,
    fingerprint: pd.Series | None = None,
) -> pd.Series:
    """Prefer a declared canonical bout PK; otherwise use the cross-source key.

    UFC's canonical schema declares ``fight_url`` to be its primary key. That
    distinction matters for UFC Japan 1997: Sakuraba and Silveira fought twice
    on the same card, so their pair-and-date fingerprints are necessarily the
    same, while their two UFCStats fight URLs identify two real bouts. Other
    corpora do not promise that property -- their differing URLs can be one
    bout scraped from two perspectives -- and therefore stay on the conservative
    pair-and-date key.
    """
    if fingerprint is None:
        if fights.empty:
            return pd.Series(index=fights.index, dtype=object)
        fingerprint = bout_fingerprint(fights)
    key = fingerprint.copy()
    if not {"source", "fight_url"} <= set(fights.columns):
        return key
    source = fights["source"].fillna("").astype(str).str.strip().str.casefold()
    url = (fights["fight_url"].fillna("").astype(str).str.strip()
           .str.rstrip("/").str.casefold())
    canonical_ufc = source.eq("ufc") & url.ne("")
    key.loc[canonical_ufc] = "ufc::" + url.loc[canonical_ufc]
    return key


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
    ``canonical_date_drift``
        A lower-source copy has the same pair and result as a canonical UFC
        bout one day away. This is the observed international-date mismatch;
        non-UFC consecutive-day tournament rematches are deliberately exempt.
    ``contradictory_duplicate``
        the same bout arrives once per source perspective, and the perspectives
        do not always agree on who won. Keeping either row asserts a result the
        sources contradict; keeping both hands each fighter a win and a loss for
        one fight. The bout is dropped. Winner names are compared in the same
        accent-, punctuation- and alias-normalized namespace as the bout key.

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
        seen = set() if ufc_fights.empty else set(bout_fingerprint(ufc_fights))
        out = out.assign(_fp=bout_fingerprint(out))
        duplicate = out["_fp"].isin(seen)
        if int(duplicate.sum()):
            dropped["already_in_ufc_table"] = int(duplicate.sum())
            out = out[~duplicate]

        drift_matches = canonical_date_drift_matches(out, ufc_fights)
        if not drift_matches.empty:
            drifted = set(drift_matches["extra_index"])
            dropped["canonical_date_drift"] = len(drifted)
            out = out.drop(index=drifted)

        out["_bout_key"] = bout_dedupe_key(out, out["_fp"])
        out["_winner_key"] = out["winner"].map(_winner_key)
        repeated = out["_bout_key"].duplicated(keep=False)
        if int(repeated.sum()):
            # Only a row that names a winner can contradict another. A draw, a
            # no-contest or an overturned result asserts nothing, so it is a
            # redundant row, not a conflicting one. Genuine UFC same-day bouts
            # have already been separated here by their canonical primary keys.
            winners = (out.loc[repeated]
                       .groupby("_bout_key")["_winner_key"].nunique(dropna=True))
            contradictory = set(winners[winners > 1].index)
            if contradictory:
                mask = out["_bout_key"].isin(contradictory)
                dropped["contradictory_duplicate"] = int(mask.sum())
                out = out[~mask]
            # Keep the row that carries the most information: a rateable,
            # decided result ahead of an excluded or undecided one.
            order = out.assign(
                _decisive=out["winner"].notna().astype(int),
                _rateable=(~out.get("is_excluded", pd.Series(False, index=out.index))
                           .fillna(False).astype(bool)).astype(int),
            ).sort_values(["_bout_key", "_rateable", "_decisive"],
                          ascending=[True, False, False], kind="mergesort")
            redundant_ids = order.index[order["_bout_key"].duplicated(keep="first")]
            if len(redundant_ids):
                dropped["repeated_in_source_table"] = int(len(redundant_ids))
                out = out.drop(index=redundant_ids)
        out = out.drop(columns=["_fp", "_bout_key", "_winner_key"])

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
