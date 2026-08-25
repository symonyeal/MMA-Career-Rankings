"""Whole-career ingestion for every fighter already in the cross-org graph.

The event crawl (``build_sherdog_majors.py``) is roster-complete *within* six
promotions and silently truncates everyone whose career ran wider. It gives
Fedor his PRIDE and Strikeforce years and drops RINGS -- the twelve bouts, from
May 2000, where he was actually built, including the King of Kings 2000 night he
beat Ricardo Arona and lost to Tsuyoshi Kosaka on a cut. Rating a fighter on a
subset of their record is the same censoring bias that made the old
fighter-seeded cache unusable, applied along a different axis.

So the promotion list stops being the scope rule. The rule is:

    a fighter the engine rates is rated on their whole record.

That is affordable and bounded because there is **no organization weight** for a
promotion label to feed -- relative promotion strength is an output of the joint
fit, read off the fighters who crossed between them. A bout is usable without
knowing who staged it, so whole careers cost one fighter page each and add no
new promotion to curate. Their opponents enter as nodes but are not themselves
expanded: one bout against an unknown is evidence about the fighter we rate, and
the unknown abstains from the board on connectivity anyway.

Writes ``data/external/sherdog/crossorg_bouts.parquet`` (event rows and career
rows merged, event card preferred where both have a bout) plus a coverage json.

Usage::

    python build_crossorg_careers.py                 # every graph fighter
    python build_crossorg_careers.py --limit 500     # busiest 500 first
    python build_crossorg_careers.py --from-cache    # no network at all
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
    crawl_careers,
    merge_careers,
    parse_cached_events,
    parse_fighter_career,
)

OUT_PATH = DEFAULT_CACHE_DIR / "crossorg_bouts.parquet"
COVERAGE_PATH = DEFAULT_CACHE_DIR / "crossorg_careers_coverage.json"


def graph_fighter_ids(bouts: pd.DataFrame) -> list[str]:
    """Fighters in the event graph, busiest first so a partial run is useful."""
    stacked = pd.concat([bouts["fighter_a_id"], bouts["fighter_b_id"]]).dropna()
    return stacked.value_counts().index.tolist()


def _cached_careers(cache_dir: Path, fighter_ids: list[str]) -> pd.DataFrame:
    import gzip

    wanted = set(fighter_ids)
    rows: list[dict] = []
    for path in sorted((cache_dir / "fighters").glob("*.html.gz")):
        fid = path.name.removesuffix(".html.gz")
        if fid not in wanted:
            continue
        with gzip.open(path, "rt", encoding="utf-8", errors="replace") as fh:
            rows.extend(parse_fighter_career(fh.read(), fid))
    return pd.DataFrame(rows)


def coverage(merged: pd.DataFrame, event_bouts: pd.DataFrame) -> dict:
    dates = pd.to_datetime(merged["event_date"], errors="coerce")
    fighters = pd.concat([merged["fighter_a_id"], merged["fighter_b_id"]]).dropna()
    by_source = merged["source"].fillna("event").value_counts() if "source" in merged else {}
    return {
        "bouts_total": int(len(merged)),
        "bouts_from_event_cards": int(len(event_bouts)),
        "bouts_added_by_careers": int(len(merged) - len(event_bouts)),
        "by_source": {str(k): int(v) for k, v in dict(by_source).items()},
        "distinct_fighters": int(fighters.nunique()),
        "date_span": [str(dates.min().date()) if dates.notna().any() else None,
                      str(dates.max().date()) if dates.notna().any() else None],
        "bouts_missing_date": int(dates.isna().sum()),
        "bouts_missing_weight_class": int(merged["weight_class"].isna().sum()),
    }


def main(limit: int | None = None, from_cache: bool = False) -> dict:
    event_bouts, _ = parse_cached_events()
    if event_bouts.empty:
        raise SystemExit("no cached events; run build_sherdog_majors.py first")
    if "source" not in event_bouts.columns:
        event_bouts = event_bouts.assign(source="event")

    ids = graph_fighter_ids(event_bouts)
    if limit:
        ids = ids[:limit]

    careers = (_cached_careers(DEFAULT_CACHE_DIR, ids) if from_cache
               else crawl_careers(ids, cache_dir=DEFAULT_CACHE_DIR))

    merged = merge_careers(event_bouts, careers)
    DEFAULT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    merged.to_parquet(OUT_PATH, index=False)

    cov = coverage(merged, event_bouts)
    cov["fighters_requested"] = len(ids)
    cov["fighter_pages_read"] = int(careers["fighter_a_id"].nunique()) if not careers.empty else 0
    COVERAGE_PATH.write_text(json.dumps(cov, indent=2))
    return cov


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=None,
                    help="only the N busiest graph fighters")
    ap.add_argument("--from-cache", action="store_true",
                    help="parse cached fighter pages only, no network")
    args = ap.parse_args()
    print(json.dumps(main(limit=args.limit, from_cache=args.from_cache), indent=2))
