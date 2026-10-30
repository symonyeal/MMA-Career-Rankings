"""Versioned, time-aware FightMatrix organization normalization."""
from __future__ import annotations

import re
from functools import cache, lru_cache
from pathlib import Path

import pandas as pd


from project_helpers import PROJECT_ROOT
DEFAULT_RULES_PATH = (
    PROJECT_ROOT / "data" / "external" / "fightmatrix" / "organization_normalization.csv"
)
RULESET_VERSION = "2026-09-08.1"


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


@lru_cache(maxsize=4)
def _rule_rows(path: str | Path = DEFAULT_RULES_PATH) -> tuple:
    """The committed rules as tuples, built once: rebuilding them on every call cost
    minutes per pass over a corpus of tens of thousands of bouts."""
    return tuple(load_organization_rules(path).itertuples(index=False))


@cache
def _ts(s: str) -> pd.Timestamp:
    return pd.Timestamp(s)


def _within(value: pd.Timestamp | pd.NaT, start: str, end: str) -> bool:
    if pd.isna(value):
        return True
    if start and value < _ts(start):
        return False
    return not (end and value > _ts(end))


@lru_cache(maxsize=4)
def _patterns(path: str | Path = DEFAULT_RULES_PATH) -> tuple:
    """Every pattern compiled together, so a malformed one raises on the first call as the
    all-rows scan did, not only when a label happens to reach it."""
    return tuple(re.compile(row.pattern, re.IGNORECASE) for row in _rule_rows(path))


@lru_cache(maxsize=1 << 18)
def _first_rule(raw: str):
    """The rule ``raw`` normalizes to under the committed rules, or None. Depends on the label alone, and
    a corpus repeats a few thousand labels over tens of thousands of bouts and several passes."""
    rows = _rule_rows()
    for row, pat in zip(rows, _patterns()):
        if pat.search(raw) is not None:
            return row
    # Normalization must be idempotent: a label this function already
    # produced has to normalize back to itself. A canonical name is not
    # always its own pattern -- "Major Regional" names a family whose
    # pattern lists the promotions in it -- so a stored canonical label
    # would otherwise round-trip to Unknown and be priced at the lowest
    # tier, which is the opposite of what the rule assigned it.
    return _by_canonical().get(raw.casefold())


@lru_cache(maxsize=4)
def _by_canonical(path: str | Path = DEFAULT_RULES_PATH) -> dict:
    out: dict = {}
    for row in _rule_rows(path):
        out.setdefault(row.canonical_organization.casefold(), row)  # first rule wins, as in the list scan
    return out


def normalize_organization(
    raw_label: str | None,
    event_date=None,
    *,
    rules: pd.DataFrame | None = None,
    verified_label: bool = False,
) -> dict:
    """Return an auditable organization match; unknowns stay unknown."""
    raw = " ".join(str(raw_label or "").split())
    when = event_date if type(event_date) is pd.Timestamp else pd.to_datetime(event_date, errors="coerce")
    if rules is None:
        first = _first_rule(raw)
        matched = () if first is None else (first,)
    else:
        source = tuple(rules.itertuples(index=False))
        matched = [
            row
            for row in source
            if re.search(row.pattern, raw, flags=re.IGNORECASE) is not None
        ]
        if not matched:
            matched = [
                row
                for row in source
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
    if verified_label and raw and raw.casefold() != "unknown":
        # An event page proves the promotion's identity even when the tier
        # vocabulary has no named rule for it. Preserve that evidence and use
        # the declared catch-all tier instead of treating a known label as
        # missing data.
        return {
            "raw_organization": raw,
            "canonical_organization": raw,
            "promotion_family": raw,
            "organization_region": None,
            "organization_tier": 4,
            "organization_match_method": "verified_unclassified",
            "organization_confidence": 1.0,
            "organization_manual_override": False,
            "organization_rule_id": None,
            "organization_ruleset_version": RULESET_VERSION,
            "organization_notes": "Verified source label; no named tier rule matched.",
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
