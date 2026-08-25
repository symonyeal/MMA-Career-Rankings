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
from loaders.fightmatrix_profiles import build_public_profile_snapshot  # noqa: E402
from loaders.odds_ingest_mdabbert import run as ingest_mdabbert_odds  # noqa: E402
from ratings.glicko2_engine import DEFAULT_TAU  # noqa: E402
from ratings.constants import SUSTAINED_PEAK_MIN_FIGHTS  # noqa: E402
from ratings.rate_snapshot import run as run_ratings  # noqa: E402
from ratings.rules_era import stage_pre_unified_scope  # noqa: E402
from ratings.scope import DEFAULT_PUBLISHED_SCOPE  # noqa: E402
from ratings.symon_score import DEFAULT_CAREER_REFERENCE  # noqa: E402


def stage_scopes(snapshot_dir: Path) -> dict[str, object]:
    """Write every non-UFC scope artifact the inputs support.

    Each one is optional and each failure is reported rather than raised: a
    missing Sherdog corpus is a reason not to be able to *select* that scope,
    not a reason to fail the refresh. Selecting a scope that was not staged
    still raises, at the point of selection, where it means something.
    """
    from loaders.majors_scope import stage_majors_scope  # local: pulls bs4

    staged: dict[str, object] = {}
    for name, stage in (("pre_unified", stage_pre_unified_scope),
                        ("majors", stage_majors_scope)):
        try:
            staged[name] = stage(snapshot_dir)
            print(f"[refresh] staged scope {name}: "
                  f"{staged[name].get('rateable_bouts', staged[name].get('bouts'))} bouts")
        except (FileNotFoundError, ValueError) as exc:
            staged[name] = f"not staged: {type(exc).__name__}: {exc}"
            print(f"[refresh] scope {name} not staged: {exc}")
    return staged
from analysis.build_notebook import build as build_notebook  # noqa: E402
from build_boards import select_core_rating_col, write_board_artifacts  # noqa: E402


_MDABBERT_CANDIDATES = (
    PROJECT_ROOT.parent / "archive" / "ufc-master.csv",
    PROJECT_ROOT.parent.parent / "archive" / "ufc-master.csv",
)
DEFAULT_MDABBERT_CSV = next(
    (path for path in _MDABBERT_CANDIDATES if path.exists()),
    _MDABBERT_CANDIDATES[0],
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
    headline_col = select_core_rating_col(eligible)
    top = eligible.sort_values(headline_col, ascending=False).head(10)
    top_line = "; ".join(f"{row.fighter} {getattr(row, headline_col):.1f}" for row in top.itertuples(index=False))
    from ratings.constants import rating_label
    headline_label = (
        "Public Legacy Score"
        if headline_col == "public_legacy_score"
        else "Career Skill Mass"
        if headline_col == "symon_career_skill_mass"
        else rating_label(headline_col)
    )

    lines = [
        "",
        f"## {snapshot_date} - Refresh run",
        f"- Canonical snapshot rebuilt from Greco CSVs: events={counts['events_kept']}, fights={counts['fights_kept']}, rounds={counts['rounds_kept']}, excluded={counts['excluded_bouts']}.",
        f"- Combined model fight table written for scope {ratings_summary.get('scope', 'unknown')}: rows={ratings_summary.get('combined_fights', {}).get('rows', 'unknown')}, model_bouts={ratings_summary.get('combined_fights', {}).get('model_bouts', 'unknown')}.",
        f"- Ratings and dominance produced: fighters_rated={ratings_summary['current_fighters']}, fighter_event_rows={ratings_summary['history_rows']}, events_processed={ratings_summary['events_processed']}.",
        "- Streams: canonical Glicko-2 filter + WHR smoother over the same binary W/L/D evidence, "
        "plus a method-scored research diagnostic.",
        "- Public scores: Public Legacy Score (the core board) and fixed 10-year Prime. "
        "Career Skill Mass is the skill diagnostic underneath the board; FightMatrix and the "
        "public anchor lists are sanity checks for top-100 outliers, never tuning targets.",
        "- Audit layers (integrity, dominance, odds, opponent context) do not enter the rating likelihood.",
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
    parser.add_argument(
        "--min-fights", type=int, default=SUSTAINED_PEAK_MIN_FIGHTS,
        help="Completeness threshold for published ranking and uncertainty artifacts.",
    )
    parser.add_argument(
        "--bootstrap-replicates", type=int, default=0,
        help=(
            "Refit the smoother this many times under Dirichlet-reweighted events to "
                "publish rank intervals (0 skips; benchmark the selected scope before a release run)."
        ),
    )
    parser.add_argument("--include-external", action="store_true",
                        help="Also load project-local UFC-DataLab, FightMatrix, and cached odds artifacts into the snapshot.")
    parser.add_argument("--include-odds", action="store_true",
                        help="Ingest the mdabbert ufc-master.csv before ratings so the performance sleeve's market sub-factor is active.")
    parser.add_argument("--mdabbert-csv", default=str(DEFAULT_MDABBERT_CSV),
                        help="Path to mdabbert ufc-master.csv. Used for odds + missed-weight cross-check.")
    parser.add_argument("--refresh-fightmatrix", action="store_true",
                        help="When --include-external is set, re-fetch FightMatrix HTML instead of using cache.")
    parser.add_argument(
        "--include-fightmatrix-profiles",
        action="store_true",
        help="Stage the bounded public ranked-cohort profile histories and merge their non-UFC bouts.",
    )
    parser.add_argument("--fightmatrix-profile-sleep", type=float, default=1.0)
    parser.add_argument("--fightmatrix-profile-limit", type=int, default=None)
    parser.add_argument(
        "--fightmatrix-insecure",
        action="store_true",
        help="Disable FightMatrix TLS verification only on a managed interception network.",
    )
    parser.add_argument(
        "--scope", default=DEFAULT_PUBLISHED_SCOPE,
        help=(
            "Which bouts the rating may see: ufc, majors, pre_unified, "
            "fightmatrix, all, or a comma-separated combination. Staging happens "
            "either way; this only decides what is rated."
        ),
    )
    parser.add_argument(
        "--experimental-crossorg",
        action="store_true",
        help="Deprecated alias for --scope fightmatrix.",
    )
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

    if args.include_fightmatrix_profiles and not args.include_external:
        parser.error("--include-fightmatrix-profiles requires --include-external")

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
        if args.include_fightmatrix_profiles:
            profile_summary = build_public_profile_snapshot(
                snapshot_dir,
                cache_dir=project_root / "data" / "external" / "fightmatrix" / "profiles",
                refresh=args.refresh_fightmatrix,
                sleep_seconds=args.fightmatrix_profile_sleep,
                verify_tls=not args.fightmatrix_insecure,
                max_profiles=args.fightmatrix_profile_limit,
            )
            print(
                "[refresh] FightMatrix public profiles: "
                f"profiles={profile_summary['profiles_loaded']:,}, "
                f"bouts={profile_summary['unique_public_bouts']:,}, "
                f"rated_crossorg={profile_summary['rated_crossorg_bouts']:,}"
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
    # Stage every scope the inputs allow, then rate only the one asked for.
    # Staging is cheap and reversible; rating is the decision. Keeping them
    # apart means "the corpus is not staged" and "the corpus is not admitted"
    # cannot be confused for each other.
    stage_scopes(snapshot_dir)

    ratings_summary = run_ratings(
        snapshot_dir,
        tau=args.tau,
        min_fights=args.min_fights,
        mdabbert_csv=mdabbert_csv if mdabbert_csv and mdabbert_csv.exists() else None,
        include_experimental_crossorg=args.experimental_crossorg,
        scope=args.scope,
    )
    board_summary = write_board_artifacts(
        snapshot_dir,
        min_rating_periods=args.min_fights,
        scope=args.scope,
    )
    print(
        "[refresh] board artifacts: "
        f"core={board_summary['core_rating_col']}, "
        f"integrity={board_summary['integrity_rating_col']}, "
        f"ledger_rows={board_summary['ledger_rows']:,}, "
        f"ranked={board_summary['ranked_fighters']:,}, "
        f"withheld={board_summary['withheld_fighters']:,}"
    )
    if args.bootstrap_replicates > 0:
        from ratings import prequential as PQ
        from ratings.age import load_birth_dates
        from ratings.uncertainty import career_mass_bootstrap, career_tiers, tier_summary

        # Through the scope loader, so the intervals describe the board that was
        # just rated. Reading canonical_fights directly here published UFC-only
        # intervals beside a joint board, and nothing in the artifacts said so.
        bootstrap_fights = PQ.load_fight_table(snapshot_dir, scope=args.scope)
        board, draws = career_mass_bootstrap(
            bootstrap_fights,
            replicates=args.bootstrap_replicates,
            whr_kwargs={"birth_dates": load_birth_dates(snapshot_dir), "age_drift": True},
            eligible_fighters=set(
                pd.read_parquet(snapshot_dir / "ratings_current.parquet").loc[
                    lambda x: x["rating_periods"].fillna(0) >= args.min_fights,
                    "fighter",
                ].astype(str)
            ),
            return_draws=True,
        )
        board.to_parquet(snapshot_dir / "career_mass_uncertainty.parquet", index=False)
        tiers = career_tiers(board, draws)
        tiers.to_parquet(snapshot_dir / "career_mass_tiers.parquet", index=False)
        widths = (board.head(50)["rank_hi"] - board.head(50)["rank_lo"]).median()
        ranked_tiers = tiers[tiers["tier"].notna()]
        uncertainty_summary = {
            "replicates": int(args.bootstrap_replicates),
            "seed": 0,
            "scope": args.scope,
            "interval": [0.025, 0.975],
            "reference": str(DEFAULT_CAREER_REFERENCE),
            "age_drift": True,
            "tier_confidence": 0.95,
            "min_rating_periods": int(args.min_fights),
            "tiers": int(ranked_tiers["tier"].nunique()),
            "tiered_fighters": int(len(ranked_tiers)),
            "unranked_at_floor": int(tiers["tier"].isna().sum()),
            "fighters": int(len(board)),
            "median_rank_width_top50": float(widths),
        }
        (snapshot_dir / "career_mass_uncertainty.json").write_text(
            json.dumps(uncertainty_summary, indent=2) + "\n", encoding="utf-8"
        )
        print(f"[refresh] rank intervals: {args.bootstrap_replicates} replicates, "
              f"scope={args.scope}, median top-50 width {widths:.0f}")
        print(f"[refresh] tiers: {ranked_tiers['tier'].nunique()} over "
              f"{len(ranked_tiers):,} fighters, "
              f"{int(tiers['tier'].isna().sum()):,} unranked at the score floor")
        print(tier_summary(tiers).head(8).round(1).to_string(index=False))
    else:
        print("[refresh] rank intervals skipped (--bootstrap-replicates 0)")
    append_changelog(project_root, args.snapshot_date, counts, ratings_summary, previous_dir)
    print(f"[refresh] changelog appended: {project_root / 'data' / 'CHANGELOG.md'}")
    notebook_path = rebuild_notebook(project_root)
    print(f"[refresh] notebook rebuilt: {notebook_path}")


if __name__ == "__main__":
    main()
