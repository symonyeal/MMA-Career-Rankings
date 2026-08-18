"""Versioned, time-aware FightMatrix organization normalization."""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RULES_PATH = (
    PROJECT_ROOT / "data" / "external" / "fightmatrix" / "organization_normalization.csv"
)
RULESET_VERSION = "2026-08-14.1"


@lru_cache(maxsize=4)
def load_organization_rules(path: str | Path = DEFAULT_RULES_PATH) -> pd.DataFrame:
    """Load and validate the committed normalization rules."""
    rules = pd.read_csv(Path(path), keep_default_na=False)
    required = {
        "rule_id", "pattern", "canonical_organization", "promotion_family", "region",
        "active_from", "active_to", "tier", "tier_from", "tier_to", "match_method",
        "confidence", "manual_override", "notes",
    }
    missing = required.difference(rules.columns)
    if missing:
        raise ValueError(f"organization rules missing columns: {sorted(missing)}")
    if rules["rule_id"].duplicated().any():
        raise ValueError("organization rule_id values must be unique")
    return rules


def _within(value: pd.Timestamp | pd.NaT, start: str, end: str) -> bool:
    if pd.isna(value):
        return True
    if start and value < pd.Timestamp(start):
        return False
    if end and value > pd.Timestamp(end):
        return False
    return True


def normalize_organization(
    raw_label: str | None,
    event_date=None,
    *,
    rules: pd.DataFrame | None = None,
) -> dict:
    """Return an auditable organization match; unknowns stay unknown."""
    raw = " ".join(str(raw_label or "").split())
    when = pd.to_datetime(event_date, errors="coerce")
    source = load_organization_rules() if rules is None else rules
    for row in source.itertuples(index=False):
        if re.search(row.pattern, raw, flags=re.IGNORECASE) is None:
            continue
        active = _within(when, row.active_from, row.active_to)
        tier_active = _within(when, row.tier_from, row.tier_to)
        return {
            "raw_organization": raw or "Unknown",
            "canonical_organization": row.canonical_organization,
            "promotion_family": row.promotion_family,
            "organization_region": row.region or None,
            "organization_tier": int(row.tier) if active and tier_active else 3,
            "organization_match_method": row.match_method,
            "organization_confidence": float(row.confidence),
            "organization_manual_override": str(row.manual_override).lower() == "true",
            "organization_rule_id": row.rule_id,
            "organization_ruleset_version": RULESET_VERSION,
            "organization_notes": row.notes or None,
        }
    return {
        "raw_organization": raw or "Unknown",
        "canonical_organization": "Unknown",
        "promotion_family": "Unknown",
        "organization_region": None,
        "organization_tier": 4,
        "organization_match_method": "unresolved",
        "organization_confidence": 0.0,
        "organization_manual_override": False,
        "organization_rule_id": None,
        "organization_ruleset_version": RULESET_VERSION,
        "organization_notes": "No normalization rule matched.",
    }


def build_organization_map(bouts: pd.DataFrame) -> pd.DataFrame:
    """Normalize every observed raw label/date period into a versioned artifact."""
    columns = [
        "raw_organization", "canonical_organization", "promotion_family",
        "organization_region", "organization_tier", "organization_match_method",
        "organization_confidence", "organization_manual_override", "organization_rule_id",
        "organization_ruleset_version", "organization_notes", "first_event_date",
        "last_event_date", "bout_count",
    ]
    if bouts is None or bouts.empty:
        return pd.DataFrame(columns=columns)
    records = []
    work = bouts.copy()
    work["event_date"] = pd.to_datetime(work.get("event_date"), errors="coerce")
    work["_raw_org"] = work.get("org", pd.Series("Unknown", index=work.index)).fillna("Unknown")
    for (raw, year), group in work.groupby(
        ["_raw_org", work["event_date"].dt.year.fillna(0)], dropna=False, sort=True
    ):
        sample_date = group["event_date"].dropna().median() if group["event_date"].notna().any() else pd.NaT
        rec = normalize_organization(str(raw), sample_date)
        rec.update({
            "first_event_date": group["event_date"].min(),
            "last_event_date": group["event_date"].max(),
            "bout_count": int(len(group)),
        })
        records.append(rec)
    return pd.DataFrame(records).reindex(columns=columns)


def annotate_organizations(bouts: pd.DataFrame) -> pd.DataFrame:
    """Attach normalized organization fields to bout rows deterministically."""
    if bouts is None or bouts.empty:
        return bouts.copy()
    rows = [
        normalize_organization(raw, date)
        for raw, date in zip(bouts.get("org"), bouts.get("event_date"))
    ]
    return pd.concat([bouts.reset_index(drop=True), pd.DataFrame(rows)], axis=1)
