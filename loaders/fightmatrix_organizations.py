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
    matched = [
        row
        for row in source.itertuples(index=False)
        if re.search(row.pattern, raw, flags=re.IGNORECASE) is not None
    ]
    if not matched:
        # Normalization must be idempotent: a label this function already
        # produced has to normalize back to itself. A canonical name is not
        # always its own pattern -- "Major Regional" names a family whose
        # pattern lists the promotions in it -- so a stored canonical label
        # would otherwise round-trip to Unknown and be priced at the lowest
        # tier, which is the opposite of what the rule assigned it.
        matched = [
            row
            for row in source.itertuples(index=False)
            if row.canonical_organization.casefold() == raw.casefold()
        ]
    for row in matched:
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
