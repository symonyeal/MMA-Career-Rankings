"""Score the lean rating core against held-out fights.

Rolling-origin prequential evaluation (see ``ratings/prequential.py`` for why it
is cheap and why it is honest). Writes four artifacts into the snapshot:

* ``prequential_predictions.parquet`` — one row per (variant, held-out bout)
* ``prequential_scores.parquet``      — metrics overall and per segment
* ``prequential_paired.parquet``      — paired ablation deltas with intervals
* ``prequential_summary.json``        — run configuration and cost

Usage::

    python build_prequential_evaluation.py data/snapshots/2026-08-13 \
        --events 40 --mode recent --out-dir data/model_tuning/prequential
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import pandas as pd

from ratings import prequential as PQ

# (baseline, challenger, what the comparison isolates)
ABLATION_PAIRS = [
    ("canonical", "whr", "smoother vs filter"),
    (
        "whr",
        "whr_symmetric_dominance_research",
        "shared bout-level dominance precision (research)",
    ),
]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("snapshot_dir", type=Path)
    ap.add_argument("--events", type=int, default=40, help="held-out events")
    ap.add_argument("--mode", default="recent", choices=["recent", "stratified", "all"])
    ap.add_argument("--since-year", type=int, default=None,
                    help="restrict held-out events to this year onward")
    ap.add_argument("--calibration-events", type=int, default=40)
    ap.add_argument("--min-prior-fights", type=int, default=PQ.DEFAULT_MIN_PRIOR_FIGHTS)
    ap.add_argument("--min-n", type=int, default=200,
                    help="segment sample floor below which no conclusion is drawn")
    ap.add_argument("--whr-iterations", type=int, default=None)
    ap.add_argument(
        "--with-crossorg",
        action="store_true",
        help="Deprecated alias for the named FightMatrix scope (default is UFC-only)",
    )
    ap.add_argument("--online-only", action="store_true", help="skip the WHR refit variants")
    ap.add_argument("--variants", default=None,
                    help="comma-separated variant names to score (default: all)")
    ap.add_argument("--out-dir", type=Path, default=Path("data/model_tuning/prequential"))
    ap.add_argument("--artifact-dir", type=Path, default=None,
                    help="where to write the four artifacts; defaults to the snapshot, "
                         "or to --out-dir when the snapshot is marked finalized")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    t_wall, t_cpu = time.perf_counter(), time.process_time()
    print(f"[inputs] {args.snapshot_dir}")
    inputs = PQ.build_inputs(args.snapshot_dir, with_crossorg=args.with_crossorg)
    build_cpu = time.process_time() - t_cpu
    print(f"[inputs] {len(inputs.fights):,} rated bouts, {build_cpu:.1f}s cpu")

    eval_events = PQ.choose_eval_events(
        inputs.fights, n_events=args.events, mode=args.mode, since_year=args.since_year)
    calib_events = PQ.split_calibration_events(
        inputs.fights, eval_events, n_events=args.calibration_events)
    print(f"[folds] {len(eval_events)} eval events "
          f"({eval_events['event_date'].min().date()} -> {eval_events['event_date'].max().date()}), "
          f"{int(eval_events['n_bouts'].sum())} decided bouts; "
          f"{len(calib_events)} calibration events before them")

    variants = PQ.default_variants()
    if args.online_only:
        variants = [v for v in variants if v.engine != "whr"]
    if args.variants:
        wanted = {n.strip() for n in args.variants.split(",") if n.strip()}
        missing = wanted - {v.name for v in variants}
        if missing:
            raise SystemExit(f"unknown variants: {sorted(missing)}")
        variants = [v for v in variants if v.name in wanted]

    cache_dir = args.out_dir / Path(args.snapshot_dir).name
    sweep_cpu = time.process_time()
    predictions = PQ.run_sweep(
        inputs, variants, eval_events,
        cache_dir=cache_dir,
        calibration_events=calib_events,
        min_prior_fights=args.min_prior_fights,
        whr_iterations=args.whr_iterations,
        force=args.force,
    )
    sweep_cpu = time.process_time() - sweep_cpu
    if predictions.empty:
        print("no predictions produced")
        return

    bench = PQ.benchmark_predictions(predictions, inputs)
    bench["p_a_calibrated"] = bench["p_a"]
    bench["temperature"] = 1.0
    combined = pd.concat([predictions, bench], ignore_index=True, sort=False)
    # Cross-org rows are all stored winner-first; symmetrize so AUC is defined.
    combined = PQ.symmetrize_sides(combined)
    combined = PQ.attach_segments(combined, inputs.fights, odds=inputs.odds)

    scores_raw = PQ.score_predictions(combined, min_n=args.min_n, calibrated=False)
    scores_cal = PQ.score_predictions(combined, min_n=args.min_n, calibrated=True)
    scores = pd.concat([scores_raw, scores_cal], ignore_index=True, sort=False)

    names = {v.name for v in variants}
    paired = []
    for baseline, challenger, isolates in ABLATION_PAIRS:
        if baseline not in names or challenger not in names:
            continue
        for metric in ("log_loss", "brier", "accuracy"):
            for calibrated in (False, True):
                row = PQ.paired_delta(combined, baseline, challenger,
                                      metric=metric, calibrated=calibrated)
                row["isolates"] = isolates
                row["calibrated"] = calibrated
                paired.append(row)
    paired = pd.DataFrame(paired)

    snap = Path(args.snapshot_dir)
    # Finalized snapshots are immutable: never add artifacts to one.
    finalized = any(snap.glob("*_FINALIZED"))
    if args.artifact_dir is not None:
        snap = args.artifact_dir
    elif finalized:
        snap = args.out_dir / Path(args.snapshot_dir).name
        print(f"[artifacts] snapshot is finalized; writing to {snap}")
    snap.mkdir(parents=True, exist_ok=True)
    combined.to_parquet(snap / "prequential_predictions.parquet", index=False)
    scores.to_parquet(snap / "prequential_scores.parquet", index=False)
    paired.to_parquet(snap / "prequential_paired.parquet", index=False)

    total_cpu = time.process_time() - t_cpu
    summary = {
        "snapshot": Path(args.snapshot_dir).name,
        "rated_bouts": int(len(inputs.fights)),
        "eval_events": int(len(eval_events)),
        "calibration_events": int(len(calib_events)),
        "eval_mode": args.mode,
        "since_year": args.since_year,
        "min_prior_fights": args.min_prior_fights,
        "min_n_for_conclusions": args.min_n,
        "with_crossorg_experimental": bool(args.with_crossorg),
        "variants": sorted(names),
        "scored_bouts_per_variant": int(len(predictions) / max(len(names), 1)),
        "cpu_seconds": {"inputs": round(build_cpu, 1), "sweep": round(sweep_cpu, 1),
                        "total": round(total_cpu, 1)},
        "wall_seconds": round(time.perf_counter() - t_wall, 1),
    }
    (snap / "prequential_summary.json").write_text(json.dumps(summary, indent=2))

    overall = scores[(scores.segment_type == "overall")].copy()
    for flag, label in ((False, "RAW"), (True, "TEMPERATURE-CALIBRATED")):
        col = "p_a_calibrated" if flag else "p_a"
        block = overall[overall.prob_column == col].sort_values("log_loss")
        print(f"\n=== overall, {label} (n={int(block['n'].iloc[0]):,}) ===")
        print(block[["variant", "log_loss", "brier", "accuracy", "auc",
                     "calibration_error"]].round(4).to_string(index=False))

    print(f"\ncpu: inputs {build_cpu:.0f}s + sweep {sweep_cpu:.0f}s = {total_cpu:.0f}s")


if __name__ == "__main__":
    main()
