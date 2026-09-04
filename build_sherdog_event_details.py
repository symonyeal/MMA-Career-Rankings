"""Replace inferred Sherdog bout fields with exact event-page evidence.

Fighter pages provide whole-career coverage but omit promotion and weight
class. This stage follows only the event links already present in that corpus,
reads the authoritative event card and replaces matching rows without adding
new bouts. Pages are cached individually in the shared SQLite store, so a long
run is resumable and a later parse needs no network access.

Usage::

    python build_sherdog_event_details.py
    python build_sherdog_event_details.py --limit 100
    python build_sherdog_event_details.py --from-cache
    python build_sherdog_event_details.py --report-only
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from loaders.fightmatrix_organizations import normalize_organization  # noqa: E402
from loaders.page_cache import open_cache  # noqa: E402
from loaders.sherdog_org_loader import (  # noqa: E402
    DEFAULT_CACHE_DIR,
    FetchFailed,
    _pair_key,
    _session,
    align_bout_schema,
    fetch,
    merge_careers,
    parse_event,
)


DEFAULT_BOUTS_PATH = DEFAULT_CACHE_DIR / "crossorg_bouts.parquet"
DEFAULT_REPORT_PATH = DEFAULT_CACHE_DIR / "event_detail_coverage.json"


def _present(series: pd.Series) -> pd.Series:
    return series.notna() & series.astype("string").str.strip().ne("")


def _bout_keys(frame: pd.DataFrame) -> pd.Series:
    """``event::fighter::fighter`` per row, independent of who is listed first.

    The two sources disagree about corner order, so this is the identity the
    hydration must leave untouched: same bouts in, same bouts out.
    """
    pair = frame[["fighter_a_id", "fighter_b_id"]].astype(str)
    return (
        frame["event_id"].astype(str)
        + "::"
        + pair.min(axis=1)
        + "::"
        + pair.max(axis=1)
    )


def _same_bouts(left: pd.DataFrame, right: pd.DataFrame) -> bool:
    """Same bout identities and the same number of rows for each.

    Counts, not a set: a set comparison passes while a bout is silently
    duplicated, which is the one failure this stage has to make impossible.
    """
    return (
        _bout_keys(left).value_counts().sort_index()
        .equals(_bout_keys(right).value_counts().sort_index())
    )


def _fetch_priority(usable: pd.DataFrame) -> pd.DataFrame:
    """Rank events so the pages that can change a model input come first.

    ``_organization_factor`` falls back to ``ORG_FACTOR_BY_TIER[4]`` for any
    promotion outside its named table, so an event whose promotion has no named
    tier rule scores the same read or unread -- its page can only add a display
    label. Event-name text is a prefilter, never the answer; the card still has
    to prove the promotion. Ordering this way makes an interrupted run a
    finished state rather than a partial one.
    """
    events = usable.drop_duplicates("event_id")[
        ["event_id", "event_href", "event_name", "org"]
    ].copy()
    events["bouts"] = events["event_id"].map(usable.groupby("event_id").size())
    family = (
        events["event_name"].fillna("").str.split(r"\s*[-:]\s*", regex=True, n=1).str[0].str.strip()
    )
    named = {
        name: normalize_organization(name)["canonical_organization"] != "Unknown"
        for name in family.unique()
    }
    events["priority"] = (~_present(events["org"]) & family.map(named)).astype(int)
    return events.sort_values(
        ["priority", "bouts"], ascending=[False, False], kind="stable"
    )


def _coverage(frame: pd.DataFrame) -> dict[str, int | float]:
    org = _present(frame["org"])
    weight = _present(frame["weight_class"])
    exact = frame.get("source", pd.Series("", index=frame.index)).eq("event")
    return {
        "bouts": int(len(frame)),
        "exact_event_rows": int(exact.sum()),
        "promotion_present": int(org.sum()),
        "promotion_share": float(org.mean()) if len(frame) else 0.0,
        "weight_class_present": int(weight.sum()),
        "weight_class_share": float(weight.mean()) if len(frame) else 0.0,
    }


def hydrate(
    stored: pd.DataFrame,
    *,
    cache_dir: Path,
    fetch_missing: bool,
    limit: int = 0,
    progress: bool = True,
) -> tuple[pd.DataFrame, dict]:
    """Hydrate known bouts and return a same-scope frame plus audit report."""
    usable = stored.dropna(subset=["event_id", "event_href"]).copy()
    usable["event_id"] = usable["event_id"].astype(str)
    ranked = _fetch_priority(usable)
    href_by_event = ranked.set_index("event_id")["event_href"].astype(str)
    wanted_by_event = {
        event_id: set(keys)
        for event_id, keys in _bout_keys(usable).groupby(usable["event_id"])
    }

    event_rows: list[dict] = []
    parsed_events = 0
    requested = 0
    fetched = 0
    hard_missing: list[str] = []
    unreachable: list[str] = []
    unparsed: list[str] = []
    session = _session() if fetch_missing else None

    with open_cache(cache_dir) as cache:
        cached_before = set(cache.keys("events"))
        for position, (event_id, href) in enumerate(href_by_event.items(), 1):
            html = cache.get("events", event_id)
            if html is None and fetch_missing and (not limit or requested < limit):
                requested += 1
                try:
                    html = fetch(session, href, cache, "events", event_id)
                except FetchFailed:
                    unreachable.append(event_id)
                    continue
                if html is None:
                    hard_missing.append(event_id)
                    continue
                fetched += 1
            if html is None:
                continue

            event, rows = parse_event(
                html,
                href,
                allow_unlisted_organization=True,
            )
            if event is None:
                unparsed.append(event_id)
                continue
            parsed_events += 1
            wanted = wanted_by_event.get(event_id, set())
            for row in rows:
                key = "::".join(
                    (event_id, *_pair_key(row["fighter_a_id"], row["fighter_b_id"]))
                )
                if key in wanted:
                    row["source"] = "event"
                    event_rows.append(row)
            if progress and position % 100 == 0:
                print(
                    f"events {position:,}/{len(href_by_event):,}; "
                    f"fetched={fetched:,}; exact bouts={len(event_rows):,}",
                    flush=True,
                )

        cached_after = set(cache.keys("events"))

    exact = pd.DataFrame(event_rows)
    if not exact.empty:
        # A tournament card can stage the same pair twice -- Sakuraba and
        # Silveira met in the quarter-final and the final of Ultimate Japan 1.
        # The corpus carries one row for that pair, so the first card entry
        # supplies its evidence and the rematch is not a new bout here.
        exact = exact[~_bout_keys(exact).duplicated()].reset_index(drop=True)
    merged = merge_careers(exact, stored) if not exact.empty else stored.copy()
    merged = align_bout_schema(merged, stored)
    if not _same_bouts(merged, stored):
        raise ValueError("event hydration changed the corpus bout identities")

    report = {
        "events_in_corpus": int(len(href_by_event)),
        "events_that_can_move_a_tier": int(ranked["priority"].sum()),
        "events_without_usable_link": int(stored["event_id"].isna().sum()),
        "cached_events_before": int(len(cached_before)),
        "cached_events_after": int(len(cached_after)),
        "network_requests": int(requested),
        "pages_fetched": int(fetched),
        "events_parsed": int(parsed_events),
        "exact_bouts_matched": int(len(exact)),
        "hard_missing_event_ids": hard_missing,
        "unreachable_event_ids": unreachable,
        "unparsed_event_ids": unparsed,
        "before": _coverage(stored),
        "after": _coverage(merged),
    }
    return merged, report


def main() -> dict:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bouts-path", default=str(DEFAULT_BOUTS_PATH))
    parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR))
    parser.add_argument("--report-path", default=str(DEFAULT_REPORT_PATH))
    parser.add_argument(
        "--from-cache",
        action="store_true",
        help="apply only event pages already in the cache",
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="measure cached coverage without changing the bout artifact",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="maximum new event pages to request; zero means all missing pages",
    )
    args = parser.parse_args()
    if args.limit < 0:
        parser.error("--limit must be zero or positive")

    bouts_path = Path(args.bouts_path)
    stored = pd.read_parquet(bouts_path)
    merged, report = hydrate(
        stored,
        cache_dir=Path(args.cache_dir),
        fetch_missing=not (args.from_cache or args.report_only),
        limit=args.limit,
    )

    if not args.report_only:
        next_path = bouts_path.with_name(f"{bouts_path.stem}.next{bouts_path.suffix}")
        merged.to_parquet(next_path, index=False)
        checked = pd.read_parquet(next_path)
        if not _same_bouts(checked, stored):
            raise ValueError("written event-detail artifact changed bout identities")
        next_path.replace(bouts_path)
        report["artifact"] = str(bouts_path)

    report_path = Path(args.report_path)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    main()
