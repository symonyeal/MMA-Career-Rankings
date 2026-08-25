"""Settle ``WHR_VIRTUAL_GAMES`` against held-out prediction.

``ratings/whr.py`` says the prior mass "should ultimately be chosen by
predictive backtest (Brier / log-loss); the default is a reasonable MMA prior".
It never was. This driver runs that backtest.

Why the constant matters
------------------------
An undefeated fighter has no interior maximum-likelihood rating, so ``v`` alone
stops the climb. The module's own closed form for ``k`` wins over average
opposition is::

    sigma(r) = (k + v/2) / (k + v)   ->   mu = 1500 + 173.72 * ln(2k/v + 1)

At the production ``v = 2.0`` that is ``1500 + 173.72*ln(k+1)``, which reaches
2045 on a 22-fight unbeaten run — above every contender bar in the modern era,
on no evidence about a single opponent. ``v`` binds *only* where the likelihood
is unbounded, i.e. on near-perfect records, so it is a targeted control on that
failure rather than a global shrinkage knob.

What this measures, and what it does not
----------------------------------------
The only honest question for a rating parameter is whether moving it improves
out-of-sample prediction. This deliberately does not measure agreement with any
external all-time ranking. If the curve is flat across a wide band then ``v`` is
unidentified by prediction, the current value is a prior rather than a tuned
result, and the report has to say so — at which point a value may be chosen
inside the indifference band on separate, stated grounds.

Usage::

    python build_whr_prior_sweep.py data/snapshots/2026-08-13 \
        --values 2,4,6,8,10,14,20 --events 40
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from ratings import prequential as PQ

BASELINE_V = 2.0  # ratings.constants.WHR_VIRTUAL_GAMES, the production value
SCALE = 400.0 / np.log(10)


def variant_name(v: float) -> str:
    return f"whr_v{v:g}".replace(".", "p")


def undefeated_ceiling(k: int, v: float) -> float:
    """The module's closed form: where a k-0 record settles vs average opposition."""
    return 1500.0 + SCALE * np.log(2.0 * k / v + 1.0)


def attach_unbeaten_segment(
    predictions: pd.DataFrame, fights: pd.DataFrame, *, min_streak: int = 8
) -> pd.DataFrame:
    """Flag bouts where a side arrives unbeaten over at least ``min_streak`` wins.

    This is the population the prior actually governs. A whole-sport gate that
    only reports an overall number cannot see the defect: the fighters whose
    likelihood is unbounded are precisely the ones a UFC-only held-out set never
    contains, and even on a whole-sport set they are a small minority of bouts.
    Averaged over everything, a change that fixes them is invisible.
    """
    draw = pd.to_numeric(fights.get("is_draw"), errors="coerce").fillna(0).astype(bool)
    nc = pd.to_numeric(fights.get("is_nc"), errors="coerce").fillna(0).astype(bool)
    decided = fights[~(draw | nc)].copy()
    decided["event_date"] = pd.to_datetime(decided["event_date"])
    sides = pd.concat([
        decided[["fight_url", "event_date", "fighter_a", "winner"]].rename(
            columns={"fighter_a": "fighter"}),
        decided[["fight_url", "event_date", "fighter_b", "winner"]].rename(
            columns={"fighter_b": "fighter"}),
    ], ignore_index=True)
    sides["won"] = sides["fighter"].eq(sides["winner"]).astype(int)
    sides["lost"] = 1 - sides["won"]
    # Sort once, then take strictly-prior cumulative sums per fighter. Assigning
    # the shifted cumsum back by index (never .to_numpy(), which would be in
    # group order rather than row order) is what keeps the record aligned.
    sides = sides.sort_values(["event_date", "fight_url"]).reset_index(drop=True)
    g = sides.groupby("fighter", sort=False)
    sides["prior_w"] = g["won"].cumsum() - sides["won"]
    sides["prior_l"] = g["lost"].cumsum() - sides["lost"]
    sides["unbeaten"] = (sides["prior_l"] == 0) & (sides["prior_w"] >= min_streak)

    flag = (sides.groupby(["fight_url"], sort=False)["unbeaten"].any()
            .rename("_faces_unbeaten"))
    out = predictions.merge(flag, on="fight_url", how="left")
    out["unbeaten_entrant"] = np.where(
        out["_faces_unbeaten"].fillna(False).to_numpy(dtype=bool),
        "faces_unbeaten", "both_tested",
    )
    return out.drop(columns="_faces_unbeaten")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("snapshot_dir", type=Path)
    ap.add_argument("--values", default="2,4,6,8,10,14,20",
                    help="comma-separated virtual_games values to score")
    ap.add_argument("--scope", default=None,
                    help="rating scope, e.g. 'majors,pre_unified' (default: UFC only)")
    ap.add_argument("--events", type=int, default=40, help="held-out events")
    ap.add_argument("--mode", default="recent", choices=["recent", "stratified", "all"])
    ap.add_argument("--calibration-events", type=int, default=40)
    ap.add_argument("--min-prior-fights", type=int, default=PQ.DEFAULT_MIN_PRIOR_FIGHTS)
    ap.add_argument("--min-n", type=int, default=200)
    ap.add_argument("--unbeaten-streak", type=int, default=8,
                    help="wins with no losses that make a side an unbeaten entrant")
    ap.add_argument("--whr-iterations", type=int, default=None)
    ap.add_argument("--out-dir", type=Path, default=Path("data/model_tuning/whr-prior"))
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    values = [float(x) for x in args.values.split(",") if x.strip()]
    if BASELINE_V not in values:
        values.insert(0, BASELINE_V)

    t_wall, t_cpu = time.perf_counter(), time.process_time()
    print(f"[inputs] {args.snapshot_dir} scope={args.scope or 'ufc'}")
    inputs = PQ.build_inputs(args.snapshot_dir, scope=args.scope)
    print(f"[inputs] {len(inputs.fights):,} rated bouts, "
          f"{time.process_time() - t_cpu:.1f}s cpu")

    eval_events = PQ.choose_eval_events(
        inputs.fights, n_events=args.events, mode=args.mode)
    calib_events = PQ.split_calibration_events(
        inputs.fights, eval_events, n_events=args.calibration_events)
    print(f"[folds] {len(eval_events)} eval events "
          f"({eval_events['event_date'].min().date()} -> "
          f"{eval_events['event_date'].max().date()}), "
          f"{int(eval_events['n_bouts'].sum())} decided bouts; "
          f"{len(calib_events)} calibration events")

    # use_age_drift matches the production ``whr`` variant, so the only thing
    # varying across the sweep is the prior mass.
    variants = [
        PQ.Variant(variant_name(v), engine="whr", use_age_drift=True, virtual_games=v)
        for v in values
    ]

    out_dir = args.out_dir / Path(args.snapshot_dir).name
    sweep_cpu = time.process_time()
    predictions = PQ.run_sweep(
        inputs, variants, eval_events,
        cache_dir=out_dir / "cache",
        calibration_events=calib_events,
        min_prior_fights=args.min_prior_fights,
        whr_iterations=args.whr_iterations,
        force=args.force,
    )
    sweep_cpu = time.process_time() - sweep_cpu
    if predictions.empty:
        raise SystemExit("no predictions produced")

    combined = PQ.symmetrize_sides(predictions)
    combined = PQ.attach_segments(combined, inputs.fights, odds=inputs.odds)
    combined = attach_unbeaten_segment(combined, inputs.fights,
                                       min_streak=args.unbeaten_streak)
    segments = PQ.SEGMENTS + ["unbeaten_entrant"]
    scores = pd.concat(
        [PQ.score_predictions(combined, min_n=args.min_n, segments=segments,
                              calibrated=c)
         for c in (False, True)],
        ignore_index=True, sort=False,
    )

    base = variant_name(BASELINE_V)
    paired = []
    for v in values:
        name = variant_name(v)
        if name == base:
            continue
        for metric in ("log_loss", "brier", "accuracy"):
            for calibrated in (False, True):
                row = PQ.paired_delta(combined, base, name,
                                      metric=metric, calibrated=calibrated)
                row["virtual_games"] = v
                row["calibrated"] = calibrated
                paired.append(row)
    paired = pd.DataFrame(paired)

    out_dir.mkdir(parents=True, exist_ok=True)
    combined.to_parquet(out_dir / "whr_prior_predictions.parquet", index=False)
    scores.to_parquet(out_dir / "whr_prior_scores.parquet", index=False)
    paired.to_parquet(out_dir / "whr_prior_paired.parquet", index=False)

    overall = scores[(scores.segment_type == "overall")
                     & (scores.prob_column == "p_a_calibrated")].copy()
    overall["virtual_games"] = [
        values[[variant_name(v) for v in values].index(n)] for n in overall.variant
    ]
    overall = overall.sort_values("virtual_games")

    print(f"\n=== overall, temperature-calibrated (n={int(overall['n'].iloc[0]):,}) ===")
    print(overall[["virtual_games", "log_loss", "brier", "accuracy", "auc",
                   "calibration_error"]].round(5).to_string(index=False))

    if not paired.empty:
        ll = paired[(paired.metric == "log_loss") & paired.calibrated].sort_values(
            "virtual_games")
        print("\n=== paired delta vs v=2 (log loss; negative = the change helps) ===")
        print(ll[["virtual_games", "delta", "lo", "hi", "n", "favours"]]
              .round(5).to_string(index=False))
        acc = paired[(paired.metric == "accuracy") & paired.calibrated].sort_values(
            "virtual_games")
        print("\n=== paired delta vs v=2 (accuracy; positive = the change helps) ===")
        print(acc[["virtual_games", "delta", "lo", "hi", "n", "favours"]]
              .round(5).to_string(index=False))

    # The decisive slice. ``v`` only binds where the likelihood is unbounded, so
    # an overall average across mostly-tested fighters dilutes the effect toward
    # zero no matter how large it is on the population that matters.
    seg = scores[(scores.segment_type == "unbeaten_entrant")
                 & (scores.prob_column == "p_a_calibrated")].copy()
    if not seg.empty:
        seg["virtual_games"] = [
            values[[variant_name(v) for v in values].index(n)] for n in seg.variant
        ]
        print("\n=== by unbeaten entrant (the population the prior governs) ===")
        for band, block in seg.groupby("segment"):
            block = block.sort_values("virtual_games")
            print(f"\n  -- {band} (n={int(block['n'].iloc[0]):,}) --")
            print(block[["virtual_games", "log_loss", "brier", "accuracy",
                         "calibration_error"]].round(5).to_string(index=False))
        for band in seg.segment.unique():
            rows = []
            for v in values:
                if variant_name(v) == base:
                    continue
                sub = combined[combined.unbeaten_entrant.eq(band)]
                row = PQ.paired_delta(sub, base, variant_name(v),
                                      metric="log_loss", calibrated=True)
                row["virtual_games"] = v
                rows.append(row)
            if rows:
                print(f"\n  -- paired delta vs v=2 within '{band}' "
                      f"(negative = helps) --")
                print(pd.DataFrame(rows)[["virtual_games", "delta", "lo", "hi",
                                          "n", "favours"]]
                      .round(5).to_string(index=False))

    print("\n=== what each value does to an undefeated run ===")
    ks = [13, 18, 22, 30]
    print("    k   " + "".join(f"  v={v:<6g}" for v in values))
    for k in ks:
        print(f"  {k:3d}   " + "".join(f"  {undefeated_ceiling(k, v):7.0f}"
                                       for v in values))

    summary = {
        "snapshot": Path(args.snapshot_dir).name,
        "scope": args.scope or "ufc",
        "rated_bouts": int(len(inputs.fights)),
        "eval_events": int(len(eval_events)),
        "calibration_events": int(len(calib_events)),
        "min_prior_fights": args.min_prior_fights,
        "values": values,
        "baseline": BASELINE_V,
        "scored_bouts_per_variant": int(len(predictions) / max(len(variants), 1)),
        "cpu_seconds": {"sweep": round(sweep_cpu, 1),
                        "total": round(time.process_time() - t_cpu, 1)},
        "wall_seconds": round(time.perf_counter() - t_wall, 1),
    }
    (out_dir / "whr_prior_summary.json").write_text(json.dumps(summary, indent=2))
    print(f"\n[artifacts] {out_dir}")
    print(f"cpu: sweep {sweep_cpu:.0f}s, total {summary['cpu_seconds']['total']:.0f}s")


if __name__ == "__main__":
    main()
