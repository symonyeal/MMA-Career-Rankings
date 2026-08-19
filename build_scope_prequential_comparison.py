"""Does admitting cross-organization history predict UFC fights better?

Phase E of the 2026-08-18 review. The expanded-scope decision was previously
argued on rank correlation against an external reference — which defines success
as reproducing a system this project is not trying to be. This asks the question
the engine can actually be held to: holding the held-out bouts fixed, does a
model that has seen a fighter's non-UFC record forecast their next UFC fight
better than one that has not?

The comparison is paired on identical held-out UFC bouts, so the two arms differ
only in what history they were allowed to learn from. Cross-organization bouts
are never scored — only UFC bouts, which both arms can predict.

Usage::

    python build_scope_prequential_comparison.py \
        data/snapshots/2026-08-14-fightmatrix-depth-one-complete_edge
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from ratings import prequential as PQ

ARMS = {
    "with_crossorg": True,
    "ufc_only": False,
}

COMPARE_VARIANTS = [
    PQ.Variant("canonical", engine="glicko", stream="canonical"),
    PQ.Variant("method", engine="glicko", stream="method"),
    PQ.Variant("method_integrity_performance", engine="weighted_glicko",
               score_mode="quality_method", weight="combined"),
]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("snapshot_dir", type=Path)
    ap.add_argument("--events", type=int, default=200)
    ap.add_argument("--mode", default="all", choices=["recent", "stratified", "all"])
    ap.add_argument("--since-year", type=int, default=2010)
    ap.add_argument("--min-prior-fights", type=int, default=PQ.DEFAULT_MIN_PRIOR_FIGHTS)
    ap.add_argument("--out-dir", type=Path, default=Path("data/model_tuning/prequential"))
    args = ap.parse_args()

    t0 = time.process_time()
    arms = {}
    for name, with_crossorg in ARMS.items():
        arms[name] = PQ.build_inputs(args.snapshot_dir, with_crossorg=with_crossorg)
        print(f"[{name}] {len(arms[name].fights):,} rated bouts", flush=True)

    # Folds are defined on the UFC-only arm so both arms can predict every one.
    base = arms["ufc_only"]
    eval_events = PQ.choose_eval_events(
        base.fights, n_events=args.events, mode=args.mode, since_year=args.since_year)
    calib_events = PQ.split_calibration_events(base.fights, eval_events, n_events=60)
    eval_keys = set(zip(eval_events["event_date"], eval_events["event_name"]))
    calib_keys = set(zip(calib_events["event_date"], calib_events["event_name"]))
    print(f"[folds] {len(eval_events)} eval / {len(calib_events)} calibration events")

    ufc_urls = set(
        base.fights.loc[
            base.fights.get("source", pd.Series("ufc", index=base.fights.index)).eq("ufc"),
            "fight_url",
        ]
    )

    frames = []
    for arm_name, inputs in arms.items():
        for variant in COMPARE_VARIANTS:
            preds = PQ.online_predictions(inputs, variant)
            preds = preds[preds["fight_url"].isin(ufc_urls)]
            floor = (preds["prior_a"] >= args.min_prior_fights) & (
                preds["prior_b"] >= args.min_prior_fights)
            in_calib = np.array([(d, n) in calib_keys for d, n in
                                 zip(preds["event_date"], preds["event_name"])], dtype=bool)
            in_eval = np.array([(d, n) in eval_keys for d, n in
                                zip(preds["event_date"], preds["event_name"])], dtype=bool)
            calib = preds[in_calib & floor]
            temperature = (
                PQ.fit_temperature(calib["p_a"].to_numpy(), calib["y_a"].to_numpy())
                if len(calib) else 1.0
            )
            held = preds[in_eval & floor].copy()
            held["p_a_calibrated"] = PQ.apply_temperature(held["p_a"].to_numpy(), temperature)
            held["variant"] = f"{arm_name}::{variant.name}"
            held["arm"] = arm_name
            held["base_variant"] = variant.name
            held["temperature"] = temperature
            frames.append(held)
            print(f"  {arm_name}::{variant.name}: {len(held):,} held-out UFC bouts, "
                  f"T={temperature:.2f}", flush=True)

    allp = pd.concat(frames, ignore_index=True, sort=False)
    # Paired: keep only bouts every arm/variant could predict.
    n_series = allp.groupby("fight_url")["variant"].nunique()
    keep = set(n_series[n_series == len(ARMS) * len(COMPARE_VARIANTS)].index)
    allp = allp[allp["fight_url"].isin(keep)].reset_index(drop=True)
    allp = PQ.symmetrize_sides(allp)
    allp = PQ.attach_segments(allp, base.fights, odds=base.odds)

    scores = pd.concat([
        PQ.score_predictions(allp, calibrated=False),
        PQ.score_predictions(allp, calibrated=True),
    ], ignore_index=True, sort=False)

    paired = []
    for variant in COMPARE_VARIANTS:
        for metric in ("log_loss", "brier", "accuracy"):
            for calibrated in (False, True):
                row = PQ.paired_delta(
                    allp, f"ufc_only::{variant.name}", f"with_crossorg::{variant.name}",
                    metric=metric, calibrated=calibrated)
                row["base_variant"] = variant.name
                row["calibrated"] = calibrated
                paired.append(row)
    paired = pd.DataFrame(paired)

    out_dir = args.out_dir / Path(args.snapshot_dir).name
    out_dir.mkdir(parents=True, exist_ok=True)
    allp.to_parquet(out_dir / "scope_comparison_predictions.parquet", index=False)
    scores.to_parquet(out_dir / "scope_comparison_scores.parquet", index=False)
    paired.to_parquet(out_dir / "scope_comparison_paired.parquet", index=False)
    (out_dir / "scope_comparison_summary.json").write_text(json.dumps({
        "snapshot": Path(args.snapshot_dir).name,
        "held_out_ufc_bouts": int(len(keep)),
        "eval_events": int(len(eval_events)),
        "cpu_seconds": round(time.process_time() - t0, 1),
    }, indent=2))

    overall = scores[(scores.segment_type == "overall")
                     & (scores.prob_column == "p_a_calibrated")].sort_values("log_loss")
    print(f"\n=== held-out UFC bouts only, temperature-calibrated (n={int(overall['n'].iloc[0]):,}) ===")
    print(overall[["variant", "log_loss", "brier", "accuracy", "auc",
                   "calibration_error"]].round(5).to_string(index=False))

    print("\n=== paired: with_crossorg minus ufc_only (negative = cross-org helps) ===")
    print(paired[paired.calibrated][["base_variant", "metric", "n", "delta", "lo", "hi", "favours"]]
          .round(5).to_string(index=False))
    print(f"\ncpu: {time.process_time() - t0:.0f}s")


if __name__ == "__main__":
    main()
