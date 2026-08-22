"""Ingest the major non-UFC promotions roster-complete, and report coverage.

Phase 2 of the whole-sport plan. Crawls PRIDE, WEC, Strikeforce, Affliction,
Bellator and RIZIN by *event* (see ``loaders.sherdog_org_loader``), then writes:

  data/external/sherdog/majors_bouts.parquet    every bout on every card
  data/external/sherdog/majors_events.parquet   every event, dated
  data/external/sherdog/majors_coverage.json    per-promotion, per-year counts

The coverage file is the honest part: it states how many events and bouts each
promotion contributed and over what date span, so a later claim about a
fighter's whole-sport rating can be checked against what was actually ingested
rather than against what we hoped to ingest.

Usage:
    python build_sherdog_majors.py                 # crawl (cached pages are free)
    python build_sherdog_majors.py --report-only   # re-emit reports from cache
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from loaders.sherdog_org_loader import (
    DEFAULT_CACHE_DIR,
    MAJOR_ORGS,
    crawl,
    parse_cached_events,
)

BOUTS_PATH = DEFAULT_CACHE_DIR / "majors_bouts.parquet"
EVENTS_PATH = DEFAULT_CACHE_DIR / "majors_events.parquet"
COVERAGE_PATH = DEFAULT_CACHE_DIR / "majors_coverage.json"


def coverage(bouts: pd.DataFrame, events: pd.DataFrame) -> dict:
    ev = events.copy()
    ev["year"] = pd.to_datetime(ev["event_date"], errors="coerce").dt.year
    bt = bouts.merge(ev[["event_href", "year"]], on="event_href", how="left")

    fighters = pd.concat([
        bouts[["org", "fighter_a_id"]].rename(columns={"fighter_a_id": "fid"}),
        bouts[["org", "fighter_b_id"]].rename(columns={"fighter_b_id": "fid"}),
    ])

    out: dict = {"orgs": {}, "totals": {}}
    for org in [o.label for o in MAJOR_ORGS]:
        e, b = ev[ev["org"] == org], bt[bt["org"] == org]
        if e.empty:
            out["orgs"][org] = {"events": 0, "bouts": 0}
            continue
        years = e["year"].dropna().astype(int)
        out["orgs"][org] = {
            "events": int(len(e)),
            "bouts": int(len(b)),
            "distinct_fighters": int(fighters[fighters["org"] == org]["fid"].nunique()),
            "first_event": str(e["event_date"].min()),
            "last_event": str(e["event_date"].max()),
            "events_by_year": {str(y): int(c) for y, c in years.value_counts().sort_index().items()},
            "bouts_missing_weight_class": int(b["weight_class"].isna().sum()),
            "bouts_missing_outcome": int(b["fighter_a_outcome"].isna().sum()),
        }
    out["totals"] = {
        "events": int(len(ev)),
        "bouts": int(len(bouts)),
        "distinct_fighters": int(fighters["fid"].nunique()),
        "date_span": [str(ev["event_date"].min()), str(ev["event_date"].max())],
    }
    return out


def main(report_only: bool = False, from_cache: bool = False) -> dict:
    if from_cache:
        bouts, events = parse_cached_events()
        DEFAULT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    elif report_only and BOUTS_PATH.exists():
        bouts = pd.read_parquet(BOUTS_PATH)
        events = pd.read_parquet(EVENTS_PATH)
    else:
        bouts, events = crawl()
        DEFAULT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        bouts.to_parquet(BOUTS_PATH, index=False)
        events.to_parquet(EVENTS_PATH, index=False)

    cov = coverage(bouts, events)
    COVERAGE_PATH.write_text(json.dumps(cov, indent=2))
    return cov


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Roster-complete major-promotion ingestion.")
    ap.add_argument("--report-only", action="store_true", help="rebuild reports from saved parquet")
    ap.add_argument("--from-cache", action="store_true",
                    help="reparse cached HTML without any network access")
    args = ap.parse_args()
    info = main(report_only=args.report_only, from_cache=args.from_cache)
    print(json.dumps(info["orgs"], indent=2)[:4000])
    print(json.dumps(info["totals"], indent=2))
