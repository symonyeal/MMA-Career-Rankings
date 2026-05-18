"""Refresh the UFC ranking snapshot end to end.

This script copies the current Greco CSV inputs into data/raw/<date>/, rebuilds
the canonical parquet snapshot, runs ratings and dominance, then appends a short
entry to data/CHANGELOG.md.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import date
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from loaders.ufcstats_loader import GRECO_FILES, build_snapshot  # noqa: E402
from loaders.datalab_loader import DEFAULT_DATALAB_DIR, build_snapshot as build_datalab_snapshot  # noqa: E402
from loaders.fightmatrix_loader import build_snapshot as build_fightmatrix_snapshot  # noqa: E402
from loaders.odds_ingest_mdabbert import run as ingest_mdabbert_odds  # noqa: E402
from ratings.glicko2_engine import DEFAULT_TAU  # noqa: E402
from ratings.rate_snapshot import run as run_ratings  # noqa: E402
from analysis.build_notebook import build as build_notebook  # noqa: E402


DEFAULT_MDABBERT_CSV = (
    PROJECT_ROOT.parent / "archive" / "ufc-master.csv"
)


def has_greco_files(path: Path) -> bool:
    return all((path / filename).exists() for filename in GRECO_FILES.values())


def default_greco_dir(project_root: Path, snapshot_date: str) -> Path:
    candidates = [
        project_root / "data" / "raw" / snapshot_date,
        project_root / "scrape_ufc_stats-main" / "scrape_ufc_stats-main",
        project_root.parent / "scrape_ufc_stats-main" / "scrape_ufc_stats-main",
    ]
    for candidate in candidates:
        if has_greco_files(candidate):
            return candidate
    return candidates[0]


def copy_raw_inputs(greco_dir: Path, raw_dir: Path) -> None:
    raw_dir.mkdir(parents=True, exist_ok=True)
    for filename in GRECO_FILES.values():
        src = greco_dir / filename
        if not src.exists():
            raise FileNotFoundError(f"missing Greco CSV: {src}")
        dst = raw_dir / filename
        if src.resolve() != dst.resolve():
            shutil.copy2(src, dst)


def previous_snapshot_dir(project_root: Path, snapshot_date: str) -> Path | None:
    snapshots_root = project_root / "data" / "snapshots"
    if not snapshots_root.exists():
        return None
    candidates = []
    for path in snapshots_root.iterdir():
        if path.is_dir() and path.name < snapshot_date and (path / "ratings_current.parquet").exists():
            candidates.append(path)
    return sorted(candidates, key=lambda p: p.name)[-1] if candidates else None


def mover_lines(current_path: Path, previous_path: Path | None, limit: int = 10) -> list[str]:
    if previous_path is None:
        return ["- Movers: no previous ratings snapshot found for comparison."]

    current = pd.read_parquet(current_path)[["fighter", "mu_canonical"]]
    previous = pd.read_parquet(previous_path / "ratings_current.parquet")[["fighter", "mu_canonical"]]
    merged = current.merge(previous, on="fighter", suffixes=("_current", "_previous"))
    if merged.empty:
        return ["- Movers: no overlapping fighters found in previous snapshot."]

    merged["delta_mu"] = merged["mu_canonical_current"] - merged["mu_canonical_previous"]
    up = merged.sort_values("delta_mu", ascending=False).head(limit)
    down = merged.sort_values("delta_mu", ascending=True).head(limit)

    lines = [f"- Movers vs {previous_path.name} by mu_canonical:"]
    lines.append("  - Up: " + "; ".join(
        f"{row.fighter} {row.delta_mu:+.1f}" for row in up.itertuples(index=False)
    ))
    lines.append("  - Down: " + "; ".join(
        f"{row.fighter} {row.delta_mu:+.1f}" for row in down.itertuples(index=False)
    ))
    return lines


def append_changelog(project_root: Path, snapshot_date: str, counts: dict[str, int],
                     ratings_summary: dict, previous_dir: Path | None) -> None:
    changelog = project_root / "data" / "CHANGELOG.md"
    current_path = project_root / "data" / "snapshots" / snapshot_date / "ratings_current.parquet"
    current = pd.read_parquet(current_path)
    eligible = current[current["rating_periods"] >= 3].copy()
    # WHR (Whole-History Rating smoother) is the default headline ranking.
    headline_col = next(
        (
            col
            for col in (
                "sustained_peak_headline_mu_whr",
                "sustained_peak_headline_mu_method_integrity_performance",
                "sustained_peak_mu_method_integrity_performance",
                "five_year_peak_mu_canonical",
            )
            if col in eligible.columns
        ),
        "five_year_peak_mu_canonical",
    )
    top = eligible.sort_values(headline_col, ascending=False).head(10)
    top_line = "; ".join(f"{row.fighter} {getattr(row, headline_col):.1f}" for row in top.itertuples(index=False))
    from ratings.constants import rating_label
    headline_label = rating_label(headline_col)

    lines = [
        "",
        f"## {snapshot_date} - Refresh run",
        f"- Canonical snapshot rebuilt from Greco CSVs: events={counts['events_kept']}, fights={counts['fights_kept']}, rounds={counts['rounds_kept']}, excluded={counts['excluded_bouts']}.",
        f"- Ratings and dominance produced: fighters_rated={ratings_summary['current_fighters']}, fighter_event_rows={ratings_summary['history_rows']}, events_processed={ratings_summary['events_processed']}.",
        "- Streams: wl (canonical) + method_rating + method_clean + method_perf + method_full + whr_rating + whr_clean + whr_perf + whr_full.",
        "- Performance sleeve includes quality, market, rank context, championship context, and P4P context.",
        "- Period metrics: 10-year and 5-year windows, opponent-weighted, result-aware, with all qualifying fights counted.",
        f"- Top 10 by {headline_label}: {top_line}",
    ]
    lines.extend(mover_lines(current_path, previous_dir))
    changelog.write_text(changelog.read_text(encoding="utf-8") + "\n".join(lines) + "\n", encoding="utf-8")


def rebuild_notebook(project_root: Path) -> Path:
    target = project_root / "analysis" / "notebook.ipynb"
    target.write_text(json.dumps(build_notebook(), indent=1), encoding="utf-8")
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh UFC snapshot, ratings, dominance, and changelog.")
    parser.add_argument("--snapshot-date", default=str(date.today()), help="YYYY-MM-DD snapshot label.")
    parser.add_argument("--project-root", default=str(PROJECT_ROOT), help="Project root path.")
    parser.add_argument("--greco-dir", default=None, help="Path to Greco scrape_ufc_stats CSV directory.")
    parser.add_argument("--tau", type=float, default=DEFAULT_TAU, help=f"Glicko-2 tau; default {DEFAULT_TAU}.")
    parser.add_argument("--min-fights", type=int, default=3, help="Ranking eligibility threshold for reporting.")
    parser.add_argument("--include-external", action="store_true",
                        help="Also load project-local UFC-DataLab, FightMatrix, and cached odds artifacts into the snapshot.")
    parser.add_argument("--include-odds", action="store_true",
                        help="Ingest the mdabbert ufc-master.csv before ratings so the performance sleeve's market sub-factor is active.")
    parser.add_argument("--mdabbert-csv", default=str(DEFAULT_MDABBERT_CSV),
                        help="Path to mdabbert ufc-master.csv. Used for odds + missed-weight cross-check.")
    parser.add_argument("--refresh-fightmatrix", action="store_true",
                        help="When --include-external is set, re-fetch FightMatrix HTML instead of using cache.")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    greco_dir = (
        Path(args.greco_dir).resolve()
        if args.greco_dir
        else default_greco_dir(project_root, args.snapshot_date).resolve()
    )
    snapshot_dir = project_root / "data" / "snapshots" / args.snapshot_date
    raw_dir = project_root / "data" / "raw" / args.snapshot_date
    previous_dir = previous_snapshot_dir(project_root, args.snapshot_date)

    print(f"[refresh] project_root = {project_root}")
    print(f"[refresh] greco_dir    = {greco_dir}")
    print(f"[refresh] raw_dir      = {raw_dir}")
    print(f"[refresh] snapshot_dir = {snapshot_dir}")

    copy_raw_inputs(greco_dir, raw_dir)
    counts, _ = build_snapshot(greco_dir, snapshot_dir)
    if args.include_external:
        if DEFAULT_DATALAB_DIR.exists():
            build_datalab_snapshot(DEFAULT_DATALAB_DIR, snapshot_dir)
        else:
            print(f"[refresh] UFC-DataLab checkout not found, skipping: {DEFAULT_DATALAB_DIR}")
        build_fightmatrix_snapshot(
            snapshot_dir=snapshot_dir,
            cache_dir=project_root / "data" / "external" / "fightmatrix" / "html",
            refresh=args.refresh_fightmatrix,
        )
    mdabbert_csv = Path(args.mdabbert_csv).resolve() if args.mdabbert_csv else None
    if args.include_odds or args.include_external:
        if mdabbert_csv and mdabbert_csv.exists():
            odds_info = ingest_mdabbert_odds(snapshot_dir, mdabbert_csv, keep_existing=False)
            print(
                "[refresh] mdabbert odds ingest: "
                f"loaded={odds_info['mdabbert_rows_loaded']:,}, "
                f"joined={odds_info['mdabbert_rows_joined']:,}, "
                f"snapshot odds_lines={odds_info['odds_lines_rows']:,}"
            )
        else:
            print(f"[refresh] mdabbert csv not found, skipping odds ingest: {mdabbert_csv}")
    ratings_summary = run_ratings(
        snapshot_dir,
        tau=args.tau,
        min_fights=args.min_fights,
        mdabbert_csv=mdabbert_csv if mdabbert_csv and mdabbert_csv.exists() else None,
    )
    append_changelog(project_root, args.snapshot_date, counts, ratings_summary, previous_dir)
    print(f"[refresh] changelog appended: {project_root / 'data' / 'CHANGELOG.md'}")
    notebook_path = rebuild_notebook(project_root)
    print(f"[refresh] notebook rebuilt: {notebook_path}")


if __name__ == "__main__":
    main()
