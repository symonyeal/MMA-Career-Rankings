"""Build and validate an experimental recursive public FightMatrix snapshot."""
from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path

import pandas as pd

from analysis.fightmatrix_graph import PolicyConfig, build_graph_artifacts, finalize_snapshot
from analysis.fightmatrix_validation import (
    build_anomaly_summary,
    build_anomaly_traces,
    build_scope_validation,
)
from loaders.fightmatrix_expansion import DEFAULT_PROFILE_CACHE_DIR, ExpansionConfig, run_expansion
from ratings.rate_snapshot import run as run_ratings


def stage_rating_snapshot(
    base: Path, expansion: Path, target: Path, *, model_policy: str | None = None,
) -> None:
    """Create a new experimental bundle; never overwrite or mutate the base."""
    base, expansion, target = Path(base).resolve(), Path(expansion).resolve(), Path(target).resolve()
    if target.exists():
        raise FileExistsError(f"experimental rating snapshot already exists: {target}")
    target.mkdir(parents=True)
    rating_outputs = {
        "ratings_current.parquet", "ratings_history.parquet", "ratings_history_whr.parquet",
        "ratings_history_method_integrity.parquet", "ratings_history_method_performance.parquet",
        "ratings_history_method_integrity_performance.parquet",
        "ratings_history_whr_performance.parquet", "ratings_history_whr_integrity_performance.parquet",
        "performance_appearances.parquet", "integrity_appearances.parquet", "sleeve_attribution.parquet",
        "fight_dominance.parquet", "fighter_dominance.parquet", "division_entropy.parquet",
        "division_resume.parquet", "calibration_residuals.parquet",
    }
    for source in base.iterdir():
        if source.is_file() and source.name not in rating_outputs and source.name != "crossorg_fights.parquet":
            shutil.copy2(source, target / source.name)
    model_file = (
        expansion / f"fightmatrix_model_bouts_{model_policy}.parquet"
        if model_policy else expansion / "fightmatrix_model_eligible_bouts.parquet"
    )
    eligible = pd.read_parquet(model_file)
    eligible = eligible[~eligible["is_excluded"].fillna(False)].copy()
    existing_path = base / "crossorg_fights.parquet"
    if existing_path.exists():
        existing = pd.read_parquet(existing_path)
        if "source" in existing:
            existing = existing[existing["source"].ne("fightmatrix_public_expanded")]
        eligible = pd.concat([existing, eligible], ignore_index=True, sort=False)
    eligible.to_parquet(target / "crossorg_fights.parquet", index=False)
    for source in expansion.glob("fightmatrix_*.*"):
        if source.is_file():
            shutil.copy2(source, target / source.name)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-snapshot", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--cache-dir", default=str(DEFAULT_PROFILE_CACHE_DIR))
    parser.add_argument("--max-depth", type=int, default=1)
    parser.add_argument("--max-profiles", type=int, default=5000)
    parser.add_argument("--max-new-profiles", type=int, default=1000)
    parser.add_argument("--request-budget", type=int, default=1000)
    parser.add_argument("--wall-clock-seconds", type=float, default=3600)
    parser.add_argument("--min-priority", type=float, default=0.0)
    parser.add_argument("--earliest-fight-date", default="1990-01-01")
    parser.add_argument("--min-professional-bouts", type=int, default=1)
    parser.add_argument("--max-organization-tier", type=int, default=4)
    parser.add_argument("--target-graph-closure", type=float, default=1.0)
    parser.add_argument("--target-weighted-edge-support", type=float, default=1.0)
    parser.add_argument("--max-unresolved-profile-pct", type=float, default=1.0)
    parser.add_argument("--sleep-seconds", type=float, default=1.0)
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--insecure", action="store_true")
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--checkpoint-every", type=int, default=10)
    parser.add_argument("--policy", choices=["raw", "complete_edge", "reliability", "boundary", "burn_in"], default="reliability")
    parser.add_argument("--minimum-completeness", type=float, default=0.8)
    parser.add_argument("--stage-rating-snapshot")
    parser.add_argument("--run-ratings", action="store_true")
    parser.add_argument("--bounded-cohort-snapshot")
    parser.add_argument("--finalize", action="store_true")
    return parser


def main() -> None:
    args = _parser().parse_args()
    base, output = Path(args.base_snapshot), Path(args.output_dir)
    config = ExpansionConfig(
        max_depth=args.max_depth, max_profiles=args.max_profiles,
        max_new_profiles_per_run=args.max_new_profiles, request_budget=args.request_budget,
        wall_clock_seconds=args.wall_clock_seconds, min_priority=args.min_priority,
        earliest_fight_date=args.earliest_fight_date,
        min_professional_bouts=args.min_professional_bouts,
        max_organization_tier=args.max_organization_tier,
        max_unresolved_profile_pct=args.max_unresolved_profile_pct,
        target_graph_closure=args.target_graph_closure,
        target_weighted_edge_support=args.target_weighted_edge_support,
        sleep_seconds=args.sleep_seconds,
        max_retries=args.max_retries, verify_tls=not args.insecure,
        retry_failed=args.retry_failed,
        checkpoint_every=args.checkpoint_every,
    )
    crawl = run_expansion(base, output, cache_dir=Path(args.cache_dir), config=config)
    audit = build_graph_artifacts(
        base, output,
        policy=PolicyConfig(policy=args.policy, minimum_completeness=args.minimum_completeness),
    )
    result = {"crawl": crawl, "audit": audit, "production_default_changed": False}
    if args.stage_rating_snapshot:
        rated = Path(args.stage_rating_snapshot)
        stage_rating_snapshot(base, output, rated, model_policy=args.policy)
        if args.run_ratings:
            rating_started = time.perf_counter()
            result["ratings"] = run_ratings(rated)
            rating_runtime = round(time.perf_counter() - rating_started, 3)
            (rated / "fightmatrix_rating_runtime.json").write_text(
                json.dumps({"policy": args.policy, "runtime_seconds": rating_runtime}, indent=2),
                encoding="utf-8",
            )
            scopes = {"ufc_only": base, "expanded": rated}
            if args.bounded_cohort_snapshot:
                scopes["bounded_302_seed"] = Path(args.bounded_cohort_snapshot)
            comparison, panel = build_scope_validation(scopes, rated)
            traces = build_anomaly_traces(rated, rated)
            anomaly_summary = build_anomaly_summary(panel, traces, rated)
            result["validation"] = {
                "scope_rows": len(comparison), "panel_rows": len(panel),
                "anomaly_trace_rows": len(traces), "anomaly_summary_rows": len(anomaly_summary),
            }
    if args.finalize:
        result["finalized_marker"] = str(finalize_snapshot(output))
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
