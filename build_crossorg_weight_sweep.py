"""Settle the cross-organization fight weight against held-out prediction.

``compute_fight_weights`` bridges a non-UFC bout through its two participants'
UFC-anchored caliber percentiles, clipped to ``[floor, cap]``, with
``unknown_pct`` standing in for a fighter who never reached the UFC. Fedor's
added wins carry a mean weight of ~0.66 under the current ``floor=0.5``,
``unknown_pct=0.30``, and that residual — not missing opponent history — is what
separates him from an external reference.

This sweeps floor and unknown_pct and asks the only question that settles the
parameter honestly: does moving it improve *out-of-sample prediction on
cross-organization bouts*? It deliberately does not measure agreement with any
external ranking. If the curve is flat across a wide band, the parameter is
unidentified by the data and the current value is a defensible prior rather
than a tuned result — and the report has to say so.

Only ``org_weight`` varies here. The fight table, the canonical history and the
sleeve weight tables are invariant to it, so they are built once.

Usage::

    python build_crossorg_weight_sweep.py \
        data/snapshots/2026-08-14-fightmatrix-depth-one-complete_edge \
        --anchor data/snapshots/2026-08-13/ratings_current.parquet
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from ratings import prequential as PQ
from loaders.sherdog_loader import compute_fight_weights

SWEEP_VARIANT = PQ.Variant(
    "sweep", engine="weighted_glicko", score_mode="quality_method", weight="combined"
)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("snapshot_dir", type=Path)
    ap.add_argument("--anchor", type=Path,
                    default=Path("data/snapshots/2026-08-13/ratings_current.parquet"),
                    help="UFC-only ratings_current that anchors the caliber percentiles")
    ap.add_argument("--floors", default="0.0,0.25,0.4,0.5,0.6,0.75,1.0")
    ap.add_argument("--unknowns", default="0.0,0.15,0.30,0.50,0.75")
    ap.add_argument("--events", type=int, default=200)
    ap.add_argument("--mode", default="all", choices=["recent", "stratified", "all"])
    ap.add_argument("--since-year", type=int, default=2005)
    ap.add_argument("--min-prior-fights", type=int, default=PQ.DEFAULT_MIN_PRIOR_FIGHTS)
    ap.add_argument("--out-dir", type=Path, default=Path("data/model_tuning/prequential"))
    args = ap.parse_args()

    t0 = time.process_time()
    # This driver is explicitly a cross-organization sensitivity experiment;
    # the production prequential default is intentionally UFC-only.
    inputs = PQ.build_inputs(args.snapshot_dir, with_crossorg=True)
    anchor = pd.read_parquet(args.anchor)
    crossorg_mask = inputs.fights.get("source", pd.Series("ufc", index=inputs.fights.index)).ne("ufc")
    n_crossorg = int(crossorg_mask.sum())
    print(f"[inputs] {len(inputs.fights):,} bouts, {n_crossorg:,} cross-org, "
          f"{time.process_time() - t0:.1f}s cpu")
    if n_crossorg == 0:
        print("no cross-organization bouts in this snapshot; nothing to sweep")
        return

    eval_events = PQ.choose_eval_events(
        inputs.fights, n_events=args.events, mode=args.mode, since_year=args.since_year)
    calib_events = PQ.split_calibration_events(inputs.fights, eval_events, n_events=60)
    eval_keys = set(zip(eval_events["event_date"], eval_events["event_name"]))
    calib_keys = set(zip(calib_events["event_date"], calib_events["event_name"]))
    print(f"[folds] {len(eval_events)} eval events, {len(calib_events)} calibration events")

    crossorg = inputs.fights[crossorg_mask]
    floors = [float(x) for x in args.floors.split(",") if x.strip()]
    unknowns = [float(x) for x in args.unknowns.split(",") if x.strip()]

    rows = []
    base_org_weight = inputs.fights["org_weight"].copy()
    for floor in floors:
        for unknown in unknowns:
            weights = compute_fight_weights(
                crossorg, anchor, floor=floor, cap=1.0, unknown_pct=unknown)
            org_weight = base_org_weight.copy()
            org_weight.loc[crossorg.index] = weights.to_numpy()
            inputs.fights["org_weight"] = org_weight

            preds = PQ.online_predictions(inputs, SWEEP_VARIANT)
            in_eval = np.array([(d, n) in eval_keys for d, n in
                                zip(preds["event_date"], preds["event_name"])], dtype=bool)
            in_calib = np.array([(d, n) in calib_keys for d, n in
                                 zip(preds["event_date"], preds["event_name"])], dtype=bool)
            floor_mask = (preds["prior_a"] >= args.min_prior_fights) & (
                preds["prior_b"] >= args.min_prior_fights)
            calib = preds[in_calib & floor_mask]
            temperature = (
                PQ.fit_temperature(calib["p_a"].to_numpy(), calib["y_a"].to_numpy())
                if len(calib) else 1.0
            )
            held = preds[in_eval & floor_mask].copy()
            held["p_a_calibrated"] = PQ.apply_temperature(held["p_a"].to_numpy(), temperature)
            held = PQ.symmetrize_sides(held)
            held = PQ.attach_segments(held, inputs.fights, odds=inputs.odds)

            for scope in ("all", "cross_org", "ufc_only"):
                block = held if scope == "all" else held[held["scope"] == scope]
                if block.empty:
                    continue
                for calibrated in (False, True):
                    col = "p_a_calibrated" if calibrated else "p_a"
                    m = PQ._metrics(block[col].to_numpy(dtype=float),
                                    block["y_a"].to_numpy(dtype=float))
                    rows.append({
                        "floor": floor, "unknown_pct": unknown, "scope": scope,
                        "calibrated": calibrated, "temperature": temperature,
                        "mean_crossorg_weight": float(weights.mean()),
                        **m,
                    })
            print(f"  floor={floor:<5} unknown={unknown:<5} "
                  f"mean_w={float(weights.mean()):.3f} "
                  f"n_eval={len(held):,}", flush=True)

    inputs.fights["org_weight"] = base_org_weight
    out = pd.DataFrame(rows)
    out_dir = args.out_dir / Path(args.snapshot_dir).name
    out_dir.mkdir(parents=True, exist_ok=True)
    out.to_parquet(out_dir / "crossorg_weight_sweep.parquet", index=False)

    for scope in ("cross_org", "all"):
        block = out[(out.scope == scope) & out.calibrated].sort_values("log_loss")
        if block.empty:
            continue
        print(f"\n=== {scope}: temperature-calibrated, best first ===")
        print(block[["floor", "unknown_pct", "mean_crossorg_weight", "log_loss",
                     "brier", "accuracy", "auc", "n"]].round(5).to_string(index=False))
        span = block["log_loss"].max() - block["log_loss"].min()
        print(f"log-loss spread across the whole grid: {span:.5f} "
              f"({100 * span / block['log_loss'].min():.2f}% of the best value)")

    (out_dir / "crossorg_weight_sweep_summary.json").write_text(json.dumps({
        "snapshot": Path(args.snapshot_dir).name,
        "crossorg_bouts": n_crossorg,
        "eval_events": int(len(eval_events)),
        "floors": floors,
        "unknowns": unknowns,
        "cpu_seconds": round(time.process_time() - t0, 1),
    }, indent=2))
    print(f"\ncpu: {time.process_time() - t0:.0f}s")


if __name__ == "__main__":
    main()
