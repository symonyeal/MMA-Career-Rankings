"""Is the rules-era term identified, and what does admitting UFC 1-27 cost?

The 2026-08-24 decision admits the 253 pre-unified UFC bouts to the rating and
carries an explicit rules-era indicator, so the difference between the two rule
sets is *estimated* rather than assumed. This is the estimator.

Two questions, kept apart because they have different answers:

1. **Does admitting the era help or hurt held-out prediction?** Paired on
   identical held-out unified-era UFC bouts, ``ufc`` against ``pre_unified``.
   The extra bouts can only reach a modern forecast through the fighters who
   crossed the boundary, so a small or unresolved effect is the expected result
   and is reported as such rather than rounded into a claim.

2. **Is the weight identified?** A grid over ``RULES_ERA_WEIGHT`` in (0, 1].
   If held-out log-loss is flat across the grid the term is not identified by
   prediction, and the honest default is 1.0 -- full admission -- because a
   number the data cannot distinguish must not be asserted as if it could.

Note the asymmetry deliberately built into the reporting: the *board* effect of
admission is large and immediate (Randy Couture moves off the zero-mass tie),
while the *prediction* effect is necessarily tiny. Those are different claims
about different quantities and the run prints both without letting one stand in
for the other.

Usage::

    python build_rules_era_sweep.py data/snapshots/2026-08-13
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from ratings import prequential as PQ
from ratings.rules_era import RULES_ERA_PRE, UFC_28_DATE
from ratings.symon_score import career_skill_mass
from ratings.rate_snapshot import attach_bout_weights
from ratings.whr import run_whr

ARMS = {"ufc": "ufc", "pre_unified": "pre_unified"}
COMPARE_VARIANTS = [
    PQ.Variant("canonical", engine="glicko", stream="canonical"),
    PQ.Variant("method", engine="glicko", stream="method"),
]
DEFAULT_GRID = (0.1, 0.25, 0.5, 0.75, 1.0)

# The careers the boundary actually binds on: rated record starts at UFC 28 but
# the fighter was active before it.
WATCH = ["Randy Couture", "Vitor Belfort", "Tito Ortiz", "Chuck Liddell",
         "Frank Mir", "Matt Hughes", "Pedro Rizzo", "Jeremy Horn"]


def _board(fights: pd.DataFrame, *, rules_era_weight: float) -> pd.DataFrame:
    return career_skill_mass(
        run_whr(attach_bout_weights(fights, rules_era_weight=rules_era_weight))
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("snapshot_dir", type=Path)
    ap.add_argument("--events", type=int, default=200)
    ap.add_argument("--mode", default="all", choices=["recent", "stratified", "all"])
    ap.add_argument("--since-year", type=int, default=2010)
    ap.add_argument("--grid", default=",".join(str(g) for g in DEFAULT_GRID))
    ap.add_argument("--min-prior-fights", type=int, default=PQ.DEFAULT_MIN_PRIOR_FIGHTS)
    ap.add_argument("--out-dir", type=Path, default=Path("data/model_tuning/rules_era"))
    args = ap.parse_args()

    t0 = time.process_time()
    grid = [float(g) for g in args.grid.split(",") if g.strip()]
    inputs = {name: PQ.build_inputs(args.snapshot_dir, scope=scope)
              for name, scope in ARMS.items()}
    base = inputs["ufc"]
    joint = inputs["pre_unified"]

    era = joint.fights["rules_era"].astype(str)
    print(f"[scope] ufc {len(base.fights):,} bouts; "
          f"+pre-unified {len(joint.fights):,} "
          f"({int(era.eq(RULES_ERA_PRE).sum()):,} of them pre-unified)")

    # ---------------------------------------------------------------- boards
    board_rows = []
    boards = {}
    for weight in grid:
        b = _board(joint.fights, rules_era_weight=weight)
        boards[weight] = b
        top = b.head(100)
        board_rows.append({
            "rules_era_weight": weight,
            "ranked_places": int(b["rank"].max()),
            "top100_active_2024": int((top["last_year"] >= 2024).sum()),
            "top100_median_debut": int(top["first_year"].median()),
        })
    ufc_board = _board(base.fights, rules_era_weight=1.0)
    boards["ufc_only"] = ufc_board
    top = ufc_board.head(100)
    board_rows.insert(0, {
        "rules_era_weight": float("nan"),
        "ranked_places": int(ufc_board["rank"].max()),
        "top100_active_2024": int((top["last_year"] >= 2024).sum()),
        "top100_median_debut": int(top["first_year"].median()),
    })
    board_profile = pd.DataFrame(board_rows)

    watch = pd.DataFrame({"fighter": WATCH})
    watch["ufc_only"] = watch["fighter"].map(ufc_board.set_index("fighter")["rank"])
    for weight in grid:
        watch[f"w={weight:g}"] = watch["fighter"].map(boards[weight].set_index("fighter")["rank"])

    # ----------------------------------------------------------- prediction
    eval_events = PQ.choose_eval_events(
        base.fights, n_events=args.events, mode=args.mode, since_year=args.since_year)
    calib_events = PQ.split_calibration_events(base.fights, eval_events, n_events=60)
    eval_keys = set(zip(eval_events["event_date"], eval_events["event_name"]))
    calib_keys = set(zip(calib_events["event_date"], calib_events["event_name"]))

    # Score only unified-era bouts: both arms can predict those, and a
    # pre-unified bout is not something the UFC-only arm was ever asked about.
    unified_urls = set(base.fights.loc[
        pd.to_datetime(base.fights["event_date"]) >= UFC_28_DATE, "fight_url"])

    frames = []
    for arm_name, arm in inputs.items():
        for variant in COMPARE_VARIANTS:
            preds = PQ.online_predictions(arm, variant)
            preds = preds[preds["fight_url"].isin(unified_urls)]
            floor = (preds["prior_a"] >= args.min_prior_fights) & (
                preds["prior_b"] >= args.min_prior_fights)
            in_calib = np.array([(d, n) in calib_keys for d, n in
                                 zip(preds["event_date"], preds["event_name"])], dtype=bool)
            in_eval = np.array([(d, n) in eval_keys for d, n in
                                zip(preds["event_date"], preds["event_name"])], dtype=bool)
            calib = preds[in_calib & floor]
            temperature = (PQ.fit_temperature(calib["p_a"].to_numpy(), calib["y_a"].to_numpy())
                           if len(calib) else 1.0)
            held = preds[in_eval & floor].copy()
            held["p_a_calibrated"] = PQ.apply_temperature(held["p_a"].to_numpy(), temperature)
            held["variant"] = f"{arm_name}::{variant.name}"
            frames.append(held)

    allp = pd.concat(frames, ignore_index=True, sort=False)
    n_series = allp.groupby("fight_url")["variant"].nunique()
    keep = set(n_series[n_series == len(ARMS) * len(COMPARE_VARIANTS)].index)
    allp = PQ.symmetrize_sides(allp[allp["fight_url"].isin(keep)].reset_index(drop=True))

    # Bouts with at least one boundary-crossing fighter: the only population the
    # extra evidence can reach. An effect diluted across every modern bout is
    # not the same measurement.
    pre_fighters = set(joint.fights.loc[era.eq(RULES_ERA_PRE), "fighter_a"]) | set(
        joint.fights.loc[era.eq(RULES_ERA_PRE), "fighter_b"])
    allp["touches_pre_unified"] = np.where(
        allp["fighter_a"].isin(pre_fighters) | allp["fighter_b"].isin(pre_fighters),
        "crosser", "no_crosser")

    paired = []
    for variant in COMPARE_VARIANTS:
        for band in ("all", "crosser", "no_crosser"):
            subset = allp if band == "all" else allp[allp["touches_pre_unified"].eq(band)]
            for metric in ("log_loss", "accuracy"):
                row = PQ.paired_delta(subset, f"ufc::{variant.name}",
                                      f"pre_unified::{variant.name}",
                                      metric=metric, calibrated=True)
                row.update({"base_variant": variant.name, "population": band})
                paired.append(row)
    paired = pd.DataFrame(paired)

    out_dir = args.out_dir / Path(args.snapshot_dir).name
    out_dir.mkdir(parents=True, exist_ok=True)
    board_profile.to_parquet(out_dir / "rules_era_board_profile.parquet", index=False)
    watch.to_parquet(out_dir / "rules_era_watch_ranks.parquet", index=False)
    paired.to_parquet(out_dir / "rules_era_paired.parquet", index=False)

    identified = bool((paired["population"].eq("crosser")
                       & paired["metric"].eq("log_loss")
                       & (paired["hi"] < 0)).any())
    (out_dir / "rules_era_summary.json").write_text(json.dumps({
        "snapshot": Path(args.snapshot_dir).name,
        "pre_unified_bouts": int(era.eq(RULES_ERA_PRE).sum()),
        "grid": grid,
        "admission_helps_crossers": identified,
        "cpu_seconds": round(time.process_time() - t0, 1),
    }, indent=2))

    print("\n=== board: what the rules-era weight does to the top 100 ===")
    print(board_profile.to_string(index=False))
    print("\n=== rank of a career the boundary binds on (NaN = not rated) ===")
    print(watch.to_string(index=False))
    print("\n=== held-out unified-era UFC bouts: +pre_unified minus ufc ===")
    print(paired[["base_variant", "population", "metric", "n", "delta", "lo", "hi", "favours"]]
          .round(5).to_string(index=False))
    print("\nA 'neither' verdict on every row means the term is not identified by "
          "prediction, and 1.0 stays the default by that finding, not by preference.")
    print(f"\ncpu: {time.process_time() - t0:.0f}s")


if __name__ == "__main__":
    main()
