"""Build the one fight table every model path should consume.

The staged per-corpus artifacts keep their source-specific shape because they
are easier to audit that way, but they are *build inputs*. The model sees one
named table with one dedupe policy and no hidden re-concatenation in each
consumer.

The table is written at **maximum coverage** -- every staged corpus, scope
``all`` -- and a named scope is then a row filter on ``source_corpus`` rather
than a second merge of the same sources. Before this, every consumer called
``build_combined_fights`` and re-merged the staged parquets itself, so the
written artifact was a report nobody read and the same dedupe ran four times
per build. Writing it once at full coverage means one file carries the evidence
and the scope decides which of its rows a run is allowed to see.

Filtering the maximum-coverage table is not the same operation as merging a
narrower one, and the difference is deliberate. ``scope_guard`` compares each
arriving corpus against everything merged before it, so at full coverage a bout
that FightMatrix and the Sherdog majors both carry is resolved once, in favour
of the higher-priority source. Selecting ``fightmatrix`` from that table returns
the majors parse of such a bout rather than a second copy of it. One bout, one
row, best available source -- which is what the fingerprint guard exists to
enforce.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from project_helpers import bout_fingerprint, date_range
from ratings.scope import (
    DEFAULT_PUBLISHED_SCOPE,
    corpora_for_scope,
    merge_scope,
    staged_scope,
)


COMBINED_FIGHTS_ARTIFACT = "combined_fights.parquet"
COMBINED_FIGHTS_SUMMARY_ARTIFACT = "combined_fights_summary.json"



def max_coverage_scope(snapshot_dir: Path) -> str:
    """The scope the authoritative artifact is written at: everything staged.

    Not the literal ``all``. ``all`` is a *request*, and a request for a corpus
    the snapshot never staged raises -- correct when a caller named it, wrong
    here, where the writer names nothing and simply takes the widest coverage
    available.
    """
    return staged_scope(snapshot_dir)

SOURCE_PRIORITY = {
    # UFCStats' own parse wins shared UFC bouts, including the pre-unified rows
    # restored from the snapshot's excluded-bouts file.
    "ufc": 0,
    "pre_unified": 0,
    # Event/whole-career Sherdog majors are next: they are roster-complete for
    # the named major promotions, but not the canonical UFC source.
    "sherdog_majors": 10,
    "majors": 10,
    # FightMatrix profiles are a ranked-cohort diagnostic corpus, not a
    # complete promotion/event crawl.
    "fightmatrix_public": 20,
    "fightmatrix": 20,
}

SOURCE_CORPUS = {
    "ufc": "ufc",
    "sherdog_majors": "majors",
    "majors": "majors",
    "fightmatrix_public": "fightmatrix",
    "fightmatrix": "fightmatrix",
}


def _counts(series: pd.Series, *, limit: int | None = None) -> dict[str, int]:
    values = series.dropna().astype(str)
    counts = values.value_counts()
    if limit is not None:
        counts = counts.head(limit)
    return {str(k): int(v) for k, v in counts.items()}


def _canonical_base(snapshot_dir: Path) -> pd.DataFrame:
    fights = pd.read_parquet(snapshot_dir / "canonical_fights.parquet")
    if "source" not in fights.columns:
        fights["source"] = "ufc"
    fights["source"] = fights["source"].fillna("ufc")
    if "org" not in fights.columns:
        fights["org"] = "UFC"
    fights["org"] = fights["org"].fillna("UFC")
    if "org_weight" not in fights.columns:
        fights["org_weight"] = 1.0
    fights["org_weight"] = pd.to_numeric(fights["org_weight"], errors="coerce").fillna(1.0)
    return fights


def _tag_combined(fights: pd.DataFrame, *, scope: str) -> pd.DataFrame:
    out = fights.copy()
    out["event_date"] = pd.to_datetime(out["event_date"], errors="coerce")
    if "source" not in out.columns:
        out["source"] = "ufc"
    out["source"] = out["source"].fillna("ufc").astype(str)
    if "org" not in out.columns:
        out["org"] = pd.NA

    source_key = out["source"].str.casefold()
    out["source_priority"] = source_key.map(SOURCE_PRIORITY).fillna(90).astype(int)
    out["source_corpus"] = source_key.map(SOURCE_CORPUS).fillna(out["source"])

    org_text = out["org"].fillna("").astype(str).str.casefold()
    pre_unified = source_key.eq("ufc") & org_text.str.contains("pre-unified", regex=False)
    out.loc[pre_unified, "source_corpus"] = "pre_unified"

    out["rated_scope"] = str(scope)
    out["bout_fingerprint"] = bout_fingerprint(out)
    excluded = out.get("is_excluded", pd.Series(False, index=out.index)).fillna(False).astype(bool)
    has_result = out.get("winner", pd.Series(pd.NA, index=out.index)).notna() | out.get(
        "is_draw", pd.Series(False, index=out.index)
    ).fillna(False).astype(bool)
    out["is_model_bout"] = (~excluded) & has_result
    return out.sort_values(["event_date", "event_name", "source_priority", "fight_url"]).reset_index(drop=True)


def combined_fights_summary(fights: pd.DataFrame, *, scope: str) -> dict[str, object]:
    duplicate_fingerprints = int(fights["bout_fingerprint"].duplicated().sum()) if len(fights) else 0
    model_bouts = fights.get("is_model_bout", pd.Series(False, index=fights.index)).fillna(False).astype(bool)
    start, end = date_range(fights)
    source_fields = {
        "ufc": "canonical UFCStats rows; authoritative for shared UFC bouts",
        "pre_unified": "UFC excluded-bouts recovery; admitted only by named scope",
        "majors": "Sherdog major-promotion event/whole-career rows after identity resolution",
        "fightmatrix": "FightMatrix ranked-cohort profile rows; diagnostic scope",
    }
    return {
        "artifact": COMBINED_FIGHTS_ARTIFACT,
        "scope": str(scope),
        "rows": int(len(fights)),
        "model_bouts": int(model_bouts.sum()),
        "excluded_or_unrateable_bouts": int(len(fights) - model_bouts.sum()),
        "duplicate_fingerprints": duplicate_fingerprints,
        "date_range": [start, end],
        "sources": _counts(fights["source"]) if "source" in fights.columns else {},
        "source_corpora": _counts(fights["source_corpus"]) if "source_corpus" in fights.columns else {},
        "organizations_top50": _counts(fights["org"], limit=50) if "org" in fights.columns else {},
        "columns": sorted(str(c) for c in fights.columns),
        "source_field_policy": source_fields,
    }


def build_combined_fights(
    snapshot_dir: Path,
    *,
    scope: str = DEFAULT_PUBLISHED_SCOPE,
    label: str = "combined",
    strict_duplicates: bool = True,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Return the unified fight table and a compact audit summary."""
    snapshot_dir = Path(snapshot_dir)
    base = _canonical_base(snapshot_dir)
    merged = merge_scope(base, snapshot_dir, scope=scope, label=label)
    combined = _tag_combined(merged, scope=scope)
    summary = combined_fights_summary(combined, scope=scope)
    if strict_duplicates and int(summary["duplicate_fingerprints"]):
        raise ValueError(
            "combined fight table still has duplicate bout fingerprints after scope guard: "
            f"{summary['duplicate_fingerprints']}"
        )
    return combined, summary


def select_scope(combined: pd.DataFrame, scope: str) -> pd.DataFrame:
    """The rows of the authoritative table one named scope is allowed to see."""
    admitted = corpora_for_scope(scope)
    if "source_corpus" not in combined.columns:
        raise ValueError(
            "combined fight table carries no source_corpus column, so a scope "
            "cannot be selected from it; rebuild it with write_combined_fights"
        )
    out = combined[combined["source_corpus"].isin(admitted)].copy()
    if out.empty:
        raise ValueError(
            f"scope {scope!r} selects zero bouts from the combined table "
            f"(admitted corpora: {', '.join(admitted)}); the run would rate nothing"
        )
    out["rated_scope"] = str(scope)
    return out.reset_index(drop=True)


def load_combined_fights(
    snapshot_dir: Path,
    *,
    scope: str = DEFAULT_PUBLISHED_SCOPE,
    label: str = "combined",
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Read the authoritative table and select one scope, or rebuild it.

    Falls back to a rebuild when the artifact is absent or was written at a
    coverage that does not contain the requested scope. It never quietly
    returns a narrower table than the caller asked for: that is the failure the
    scope module exists to prevent.
    """
    snapshot_dir = Path(snapshot_dir)
    path = snapshot_dir / COMBINED_FIGHTS_ARTIFACT
    if path.exists():
        combined = pd.read_parquet(path)
        present = set(combined.get("source_corpus", pd.Series(dtype=str)).dropna().unique())
        wanted = set(corpora_for_scope(scope))
        # "ufc" is the base of every scope and is always present; a corpus that
        # is genuinely empty in the snapshot would be indistinguishable from one
        # that was never staged, so a missing corpus falls through to the
        # rebuild, which raises with the builder's name.
        if wanted <= present:
            selected = select_scope(combined, scope)
            return selected, combined_fights_summary(selected, scope=scope)
        print(
            f"[{label}] {COMBINED_FIGHTS_ARTIFACT} lacks {', '.join(sorted(wanted - present))}; "
            "rebuilding from the staged corpora"
        )
    return build_combined_fights(snapshot_dir, scope=scope, label=label)


def write_combined_fights(
    snapshot_dir: Path,
    *,
    scope: str | None = None,
    label: str = "combined",
    allow_narrowing: bool = False,
) -> dict[str, object]:
    """Persist ``combined_fights`` and its summary next to the snapshot.

    Defaults to maximum coverage. Pass a narrower ``scope`` only to reproduce an
    older artifact deliberately -- every consumer selects from this file, so a
    narrow one silently caps what any later run can rate.

    **A write that would remove a corpus is skipped, not performed.** The staged
    per-corpus parquets are build inputs, and once they are archived a rebuild
    sees fewer of them; without this guard the next run would quietly replace a
    whole-sport table with a UFC-only one and every later reader would inherit
    it. ``allow_narrowing=True`` performs the write anyway, for when dropping a
    corpus is the actual intent.
    """
    snapshot_dir = Path(snapshot_dir)
    scope = max_coverage_scope(snapshot_dir) if scope is None else scope
    combined, summary = build_combined_fights(snapshot_dir, scope=scope, label=label)

    summary_path = snapshot_dir / COMBINED_FIGHTS_SUMMARY_ARTIFACT
    if not allow_narrowing and (snapshot_dir / COMBINED_FIGHTS_ARTIFACT).exists() and summary_path.exists():
        try:
            existing = json.loads(summary_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            existing = {}
        held = set(existing.get("source_corpora", {}))
        writing = set(summary.get("source_corpora", {}))
        if held - writing:
            print(
                f"[{label}] keeping the existing {COMBINED_FIGHTS_ARTIFACT}: it holds "
                f"{', '.join(sorted(held - writing))}, which the staged corpora no longer "
                "supply. Pass allow_narrowing=True to drop them on purpose."
            )
            return existing

    combined.to_parquet(snapshot_dir / COMBINED_FIGHTS_ARTIFACT, index=False)
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary
