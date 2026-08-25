"""Build the one fight table every model path should consume.

The raw/staged artifacts keep their source-specific shape because they are
easier to audit that way. The model, however, should see one named table with
one dedupe policy, one scope string, and no hidden re-concatenation in each
consumer.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from project_helpers import bout_fingerprint, date_range
from ratings.scope import DEFAULT_PUBLISHED_SCOPE, merge_scope


COMBINED_FIGHTS_ARTIFACT = "combined_fights.parquet"
COMBINED_FIGHTS_SUMMARY_ARTIFACT = "combined_fights_summary.json"

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


def write_combined_fights(
    snapshot_dir: Path,
    *,
    scope: str = DEFAULT_PUBLISHED_SCOPE,
    label: str = "combined",
) -> dict[str, object]:
    """Persist ``combined_fights`` and its summary next to the snapshot."""
    snapshot_dir = Path(snapshot_dir)
    combined, summary = build_combined_fights(snapshot_dir, scope=scope, label=label)
    combined.to_parquet(snapshot_dir / COMBINED_FIGHTS_ARTIFACT, index=False)
    (snapshot_dir / COMBINED_FIGHTS_SUMMARY_ARTIFACT).write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary
