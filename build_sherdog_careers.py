"""Complete Sherdog whole-career coverage for the fighters the corpus truncates.

Why this exists
---------------
``loaders.sherdog_org_loader.parse_fighter_career`` already states the rule:

    Enumerating six promotions by event is roster-complete *within* those six
    and silently truncates everyone whose career ran wider. [...] So once a
    fighter is in the graph at all, their whole record comes in.

That expansion was run over the 4,501 fighters who appeared on a
PRIDE / WEC / Strikeforce / Affliction / Bellator / RIZIN card. It was never run
over the UFCStats roster, so the rule ended up applied to one corpus and not the
other, and the published scope carries two different coverage rules at once.

Measured on ``data/snapshots/2026-08-13`` before this builder existed, over the
1,825 fighters with three or more UFC bouts:

    career page read      fighters   median recorded pre-UFC bouts
    yes                        547                             13
    no                       1,278                              1

That gap is worth rating points rather than nothing, because a low-loss record
has no interior Bradley--Terry maximum: the equilibrium sits near
``opponent_level + 173.72 * ln(2k/v)``, so ``k`` -- how many of a fighter's
bouts the corpus happens to hold -- moves the rating directly. Khabib
Nurmagomedov was rated on 14 bouts; his Sherdog page carries 29.

What it does
------------
Resolves a Sherdog id for every rated fighter whose career rows are not yet in
the corpus, fetches those pages through the same polite cached loader, merges
the new rows into ``crossorg_bouts.parquet`` under the existing event-card
precedence, and reports coverage before and after.

The work is defined by what is in the CORPUS, not by what is in the HTML cache:
a cached page whose rows were never merged truncates a career exactly as much as
no page at all, and keying off the cache would make a second run merge nothing.
Cached pages cost no network, so re-running is free and idempotent.

Run of 2026-08-27: 1,278 targets, 1,057 ids already known from the corpus and
221 needing a fightfinder search, of which 77 could not be resolved. Corpus
63,813 -> 80,902 bouts.

Completion pass of 2026-09-02: the careers merged in the first pass named most
of those 77 as opponents, which made them identifiable, so repeated runs closed
all but four. Coverage of the eligible roster is 1,821 of 1,825, 99.8%. The four
that remain -- Leonardo Mafra, Thiago Perpetuo, Marcos Vinicius, Ozzy Diaz --
are names the search cannot separate from other fighters carrying them, and
this builder has no way to be handed an id by hand.

Usage::

    python build_sherdog_careers.py --snapshot-dir data/snapshots/2026-08-13
    python build_sherdog_careers.py --report-only      # no network
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

from loaders.career_coverage import (  # noqa: E402
    DEFAULT_MIN_UFC_BOUTS,
    cached_page_ids,
    coverage_rows,
    coverage_summary,
    describe,
    incorporated_page_ids,
    record_incorporated_page_ids,
)
from loaders.majors_scope import (  # noqa: E402
    DEFAULT_MAJORS_DIR,
    MAJORS_CAREERS,
    load_majors_bouts,
    resolve_identities,
    to_canonical_fights,
)
from loaders.sherdog_loader import resolve_fighter_url  # noqa: E402
from loaders.sherdog_org_loader import (  # noqa: E402
    _session,
    crawl_careers,
    merge_careers,
)

COVERAGE_REPORT = "career_coverage.json"

# ``load_majors_bouts`` parses ``event_date`` to datetime for its own use, while
# the stored artifact and a freshly parsed fighter page both carry an ISO date
# string. Concatenating the two gives an object column that parquet refuses to
# write, and a few numeric columns arrive as int where the artifact holds float.
# So the merged frame is cast back to the schema already on disk rather than
# whatever the concatenation happened to produce.
_DATE_COLUMNS = ("event_date",)
_FLOAT_COLUMNS = ("end_round", "end_time_seconds", "match_order", "org_id")


def align_to_stored_schema(merged: pd.DataFrame, stored: pd.DataFrame) -> pd.DataFrame:
    """Cast a merged bout table back to the dtypes the artifact already uses."""
    out = merged.copy()
    for column in _DATE_COLUMNS:
        if column in out.columns:
            out[column] = pd.to_datetime(out[column], errors="coerce").dt.strftime("%Y-%m-%d")
    for column in _FLOAT_COLUMNS:
        if column in out.columns:
            out[column] = pd.to_numeric(out[column], errors="coerce").astype("float64")
    for column, dtype in stored.dtypes.items():
        if column not in out.columns or column in _DATE_COLUMNS or column in _FLOAT_COLUMNS:
            continue
        if pd.api.types.is_bool_dtype(dtype):
            out[column] = out[column].fillna(False).astype(bool)
        elif str(dtype) in {"str", "object", "string"}:
            out[column] = out[column].astype("object").where(out[column].notna(), None)
    ordered = [c for c in stored.columns if c in out.columns]
    return out[ordered + [c for c in out.columns if c not in ordered]]


def coverage_table(
    canonical_fights: pd.DataFrame,
    corpus_fights: pd.DataFrame,
    identity: pd.DataFrame,
    merged_ids: set[str],
) -> pd.DataFrame:
    """One row per UFC fighter: what the corpus holds and has incorporated."""
    resolved = identity[identity["join_method"].ne("unjoined")]
    return coverage_rows(
        canonical_fights,
        corpus_fights,
        sherdog_ids=(
            resolved.assign(_id=resolved["sherdog_id"].astype(str))
            .drop_duplicates("canonical_name")
            .set_index("canonical_name")["_id"]
        ),
        merged_ids=merged_ids,
    )


def main() -> dict:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--snapshot-dir", default="data/snapshots/2026-08-13")
    ap.add_argument("--majors-dir", default=str(DEFAULT_MAJORS_DIR))
    ap.add_argument("--min-ufc-bouts", type=int, default=DEFAULT_MIN_UFC_BOUTS)
    ap.add_argument("--report-only", action="store_true",
                    help="report coverage without touching the network")
    ap.add_argument("--limit", type=int, default=0,
                    help="stop after this many page fetches (0 = no limit)")
    args = ap.parse_args()

    snapshot_dir = Path(args.snapshot_dir)
    majors_dir = Path(args.majors_dir)
    canonical = pd.read_parquet(snapshot_dir / "canonical_fights.parquet")
    bouts = load_majors_bouts(majors_dir)
    identity = resolve_identities(bouts, canonical)
    staged = to_canonical_fights(bouts, identity)
    corpus = pd.concat([canonical, staged], ignore_index=True, sort=False)
    # "Needs reading" is decided by whether the fighter's career rows are in the
    # CORPUS, not by whether their HTML is on disk. A cached page whose rows were
    # never merged is exactly as truncating as no page at all, and defining the
    # work from the cache makes the builder non-idempotent: a second run would
    # see every page cached and merge nothing.
    merged_ids = incorporated_page_ids(majors_dir, bouts)
    table = coverage_table(canonical, corpus, identity, merged_ids)
    eligible = table[table["ufc_bouts"] >= args.min_ufc_bouts].copy()
    todo = eligible[~eligible["whole_career_merged"]]
    cached_ids = cached_page_ids(majors_dir)
    report = {
        "min_ufc_bouts": int(args.min_ufc_bouts),
        "ufc_fighters": int(len(table)),
        "eligible": int(len(eligible)),
        "already_cached": int(
            eligible["sherdog_id"].astype("string").fillna("").isin(cached_ids).sum()
        ),
        "already_merged": int(eligible["whole_career_merged"].sum()),
        "to_read": int(len(todo)),
        "id_known": int(todo["sherdog_id"].notna().sum()),
        "id_unknown": int(todo["sherdog_id"].isna().sum()),
        "bouts_before": int(len(bouts)),
    }
    print(describe(coverage_summary(table, min_ufc_bouts=args.min_ufc_bouts)), flush=True)
    print(json.dumps(report, indent=2), flush=True)
    if args.report_only:
        return report

    session = _session()
    # Fighters with no Sherdog id anywhere in the corpus need the fightfinder
    # search first. An unresolvable name is reported, never guessed.
    unresolved: list[str] = []
    known = todo.dropna(subset=["sherdog_id"])
    ids: list[str] = [str(i) for i in known["sherdog_id"]]
    # A fighter page names the opponent but leaves the subject's own name blank,
    # so a fighter whose id appears nowhere else in the corpus arrives nameless
    # and the identity resolver has nothing to join on -- their whole recovered
    # record would be dropped. The name is not in doubt: it is the canonical
    # fighter whose page was requested.
    name_by_id: dict[str, str] = {
        str(i): str(f) for i, f in zip(known["sherdog_id"], known["fighter"])
    }
    missing = todo[todo["sherdog_id"].isna()]["fighter"].tolist()
    for n, name in enumerate(missing, 1):
        url = resolve_fighter_url(str(name), session, majors_dir)
        if url:
            fid = url.rsplit("-", 1)[-1]
            ids.append(fid)
            name_by_id[fid] = str(name)
        else:
            unresolved.append(str(name))
        if n % 50 == 0:
            print(f"  search {n}/{len(missing)}  resolved={len(ids)}", flush=True)
    report["search_resolved"] = len(ids) - int(todo["sherdog_id"].notna().sum())
    report["search_unresolved"] = len(unresolved)
    report["unresolved_names"] = unresolved

    if args.limit:
        ids = ids[: args.limit]
    print(f"fetching {len(ids)} career pages", flush=True)
    careers = crawl_careers(ids, cache_dir=majors_dir, session=session, progress=True)
    if not careers.empty:
        subject = careers["fighter_a_id"].astype(str).map(name_by_id)
        careers["fighter_a"] = careers["fighter_a"].fillna(subject)
        report["subject_names_filled"] = int(subject.notna().sum())
    report["career_rows_fetched"] = int(len(careers))
    report["unreachable"] = list(careers.attrs.get("unreachable", []))

    if not careers.empty:
        path = majors_dir / MAJORS_CAREERS
        merged = align_to_stored_schema(merge_careers(bouts, careers), pd.read_parquet(path))
        merged.to_parquet(path, index=False)
        parsed_ids = set(careers["fighter_a_id"].dropna().astype(str))
        record_incorporated_page_ids(majors_dir, merged_ids | parsed_ids)
        report["bouts_after"] = int(len(merged))
        report["bouts_added"] = int(len(merged) - len(bouts))
        report["career_pages_incorporated"] = int(len(merged_ids | parsed_ids))
        report["artifact"] = str(path)
    else:
        report["bouts_after"] = int(len(bouts))
        report["bouts_added"] = 0

    (majors_dir / COVERAGE_REPORT).write_text(json.dumps(report, indent=2))
    print(json.dumps({k: v for k, v in report.items()
                      if k not in ("unresolved_names", "unreachable")}, indent=2))
    return report


if __name__ == "__main__":
    main()
