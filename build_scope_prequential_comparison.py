"""Does admitting a non-UFC corpus predict UFC fights better?

Phase E of the 2026-08-18 review, re-armed for blocker B1 and generalised to
any named scope. The expanded-scope decision was previously argued on rank
correlation against an external reference -- which defines success as
reproducing a system this project is not trying to be. This asks the question
the engine can actually be held to: holding the held-out bouts fixed, does a
model that has seen a fighter's non-UFC record forecast their next UFC fight
better than one that has not?

Arms
----
``ufc_only``
    the auditable production scope.
``<scope>_unweighted``
    the joint scope with every bout at weight 1.0. No organisation weight, so
    promotion strength is an output of the fit rather than an input to it.
``<scope>_weighted`` (FightMatrix only)
    the joint scope reading the staged ``org_weight``, which prices a 2003
    PRIDE bout by both participants' *eventual UFC* caliber percentiles. It
    exists to show what removing that leak costs, and it is not built for
    corpora that carry no staged weight.

The comparison is paired on identical held-out UFC bouts, so arms differ only
in what history they were allowed to learn from. Non-UFC bouts are never
scored -- only UFC bouts, which every arm can predict.

**The selection control is part of the run, not a footnote.** Coverage is
itself correlated with being good, so a naive delta partly reads that signal.
``crossorg_coverage`` bands each held-out bout by how many of its two fighters
have any non-UFC history in the joint table; the ``both`` band holds presence
constant and isolates the *content* of the extra history. That band is where
the audit's headline -0.01871 came from, and it had never been committed.

What the two corpora actually measured (2026-08-13 / depth-one, 2026-08-24)
--------------------------------------------------------------------------
=============  ==============================  ==========================
scope          both-covered log-loss delta      verdict
=============  ==============================  ==========================
`fightmatrix`  -0.01896 [-0.02376, -0.01397]    helps, and survives having
               (n=2,117; unweighted arm is      the leaked weight removed
               byte-identical to weighted for
               the two Glicko filters)
`majors`       +0.00391 [-0.00484, +0.01245]    **unresolved.** Not a gain
               (n=435)
=============  ==============================  ==========================

So the two corpora are justified on different grounds, and saying so is the
point of running this per scope. `fightmatrix` earns its place on prediction.
`majors` does not, and cannot be argued to: it back-fills 1997-2012 history for
fighters who are mostly retired before the 2010+ evaluation window opens, which
is why only 435 held-out bouts have both fighters covered at all. **`majors` is
justified on completeness, explicitly, and not on prediction** -- which is the
right claim for a corpus whose purpose is ranking history rather than
forecasting the next card.

Usage::

    python build_scope_prequential_comparison.py SNAPSHOT_DIR --scope majors
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from ratings import prequential as PQ
from ratings.scope import UFC_ONLY

BASELINE_ARM = "ufc_only"


def build_arms(scope: str) -> dict[str, tuple[str, bool]]:
    """arm name -> (scope spec, may the estimator read ``org_weight``).

    The weighted arm exists only to show what removing the weight costs. It is
    dropped for corpora that carry no staged weight, because an arm that is
    identical to another by construction is not a comparison -- it is the same
    number printed twice under two labels.
    """
    arms: dict[str, tuple[str, bool]] = {
        BASELINE_ARM: (UFC_ONLY, False),
        f"{scope}_unweighted": (scope, False),
    }
    if scope == "fightmatrix":
        arms[f"{scope}_weighted"] = (scope, True)
    return arms

# The two Glicko filters the 2026-08-18 Phase E table was built from, plus the
# weighted arm it also reported. Only the third reads ``org_weight`` at all:
# ``_run_canonical_engine`` takes W/L/D and the method score and no weights, so
# for ``canonical`` and ``method`` the weighted and unweighted joint arms are
# the same model. That is a result, not an oversight -- see the parity check
# printed at the end of the run.
COMPARE_VARIANTS = [
    PQ.Variant("canonical", engine="glicko", stream="canonical"),
    PQ.Variant("method", engine="glicko", stream="method"),
    PQ.Variant("method_integrity_performance", engine="weighted_glicko",
               score_mode="quality_method", weight="combined"),
]

COVERAGE_BANDS = ("both", "one", "neither")


def crossorg_coverage(predictions: pd.DataFrame, joint_fights: pd.DataFrame) -> pd.Series:
    """How many of a bout's two fighters have non-UFC history in the joint table.

    The selection control. The seed profiles were drawn from rankings, so
    *having* cross-org history correlates with being good; restricting to bouts
    where both fighters are covered holds that presence constant and leaves
    only the content of the extra history to explain a difference.
    """
    source = joint_fights.get("source", pd.Series("ufc", index=joint_fights.index))
    non_ufc = joint_fights[source.astype(str).ne("ufc")]
    covered = set(non_ufc["fighter_a"].dropna()) | set(non_ufc["fighter_b"].dropna())
    n = (predictions["fighter_a"].isin(covered).astype(int)
         + predictions["fighter_b"].isin(covered).astype(int))
    return n.map({2: "both", 1: "one", 0: "neither"}).astype(str)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("snapshot_dir", type=Path)
    ap.add_argument("--scope", default="fightmatrix",
                    help="the non-UFC scope to test against ufc-only")
    ap.add_argument("--events", type=int, default=200)
    ap.add_argument("--mode", default="all", choices=["recent", "stratified", "all"])
    ap.add_argument("--since-year", type=int, default=2010)
    ap.add_argument("--min-prior-fights", type=int, default=PQ.DEFAULT_MIN_PRIOR_FIGHTS)
    ap.add_argument("--out-dir", type=Path, default=Path("data/model_tuning/prequential"))
    args = ap.parse_args()

    t0 = time.process_time()
    arms = build_arms(args.scope)
    # Inputs depend only on the scope, so the weighted and unweighted arms of
    # one corpus share a build. Building them separately would repeat a full
    # Glicko sweep and a dominance pass over an identical frame.
    inputs_by_scope = {
        spec: PQ.build_inputs(args.snapshot_dir, scope=spec)
        for spec in sorted({spec for spec, _ in arms.values()})
    }
    for name, (spec, _) in arms.items():
        print(f"[{name}] scope={spec} {len(inputs_by_scope[spec].fights):,} rated bouts",
              flush=True)

    # Folds are defined on the UFC-only arm so every arm can predict every one.
    base = inputs_by_scope[UFC_ONLY]
    joint = inputs_by_scope[args.scope]
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
    for arm_name, (spec, use_org_weight) in arms.items():
        inputs = inputs_by_scope[spec]
        for variant in COMPARE_VARIANTS:
            armed = dataclasses.replace(variant, use_org_weight=use_org_weight)
            preds = PQ.online_predictions(inputs, armed)
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
    keep = set(n_series[n_series == len(arms) * len(COMPARE_VARIANTS)].index)
    allp = allp[allp["fight_url"].isin(keep)].reset_index(drop=True)
    allp = PQ.symmetrize_sides(allp)
    allp = PQ.attach_segments(allp, base.fights, odds=base.odds)
    allp["crossorg_coverage"] = crossorg_coverage(allp, joint.fights)

    segments = [*PQ.SEGMENTS, "crossorg_coverage"]
    scores = pd.concat([
        PQ.score_predictions(allp, calibrated=False, segments=segments),
        PQ.score_predictions(allp, calibrated=True, segments=segments),
    ], ignore_index=True, sort=False)

    challengers = [name for name in arms if name != BASELINE_ARM]
    paired = []
    for variant in COMPARE_VARIANTS:
        for arm in challengers:
            for band in ("all", *COVERAGE_BANDS):
                subset = allp if band == "all" else allp[allp["crossorg_coverage"].eq(band)]
                for metric in ("log_loss", "brier", "accuracy"):
                    for calibrated in (False, True):
                        row = PQ.paired_delta(
                            subset,
                            f"{BASELINE_ARM}::{variant.name}", f"{arm}::{variant.name}",
                            metric=metric, calibrated=calibrated)
                        row["base_variant"] = variant.name
                        row["arm"] = arm
                        row["coverage"] = band
                        row["calibrated"] = calibrated
                        paired.append(row)
    paired = pd.DataFrame(paired)

    # Does removing the weight change anything? For an estimator that never
    # reads org_weight the two joint arms are the same model, and the honest
    # report of that is an exact zero, not a small number.
    parity = []
    weighted_arm = f"{args.scope}_weighted"
    unweighted_arm = f"{args.scope}_unweighted"
    for variant in COMPARE_VARIANTS if weighted_arm in arms else []:
        w = allp[allp["variant"].eq(f"{weighted_arm}::{variant.name}")].set_index("fight_url")
        u = allp[allp["variant"].eq(f"{unweighted_arm}::{variant.name}")].set_index("fight_url")
        shared = w.index.intersection(u.index)
        gap = ((w.loc[shared, "p_a"] - u.loc[shared, "p_a"]).abs()
               if len(shared) else pd.Series(dtype=float))
        parity.append({
            "base_variant": variant.name,
            "n": int(len(shared)),
            "max_abs_p_gap": float(gap.max()) if len(gap) else float("nan"),
            "reads_org_weight": bool(len(gap) and gap.max() > 0.0),
        })
    parity = pd.DataFrame(parity)

    out_dir = args.out_dir / f"{Path(args.snapshot_dir).name}--{args.scope}"
    out_dir.mkdir(parents=True, exist_ok=True)
    allp.to_parquet(out_dir / "scope_comparison_predictions.parquet", index=False)
    scores.to_parquet(out_dir / "scope_comparison_scores.parquet", index=False)
    paired.to_parquet(out_dir / "scope_comparison_paired.parquet", index=False)
    parity.to_parquet(out_dir / "scope_comparison_weight_parity.parquet", index=False)
    (out_dir / "scope_comparison_summary.json").write_text(json.dumps({
        "snapshot": Path(args.snapshot_dir).name,
        "scope": args.scope,
        "arms": {k: {"scope": v[0], "use_org_weight": v[1]} for k, v in arms.items()},
        "held_out_ufc_bouts": int(len(keep)),
        "eval_events": int(len(eval_events)),
        "coverage_counts": allp.drop_duplicates("fight_url")["crossorg_coverage"]
                               .value_counts().to_dict(),
        "cpu_seconds": round(time.process_time() - t0, 1),
    }, indent=2))

    overall = scores[(scores.segment_type == "overall")
                     & (scores.prob_column == "p_a_calibrated")].sort_values("log_loss")
    print(f"\n=== held-out UFC bouts only, temperature-calibrated "
          f"(n={int(overall['n'].iloc[0]):,}) ===")
    print(overall[["variant", "log_loss", "brier", "accuracy", "auc",
                   "calibration_error"]].round(5).to_string(index=False))

    if len(parity):
        print("\n=== does removing org_weight change the forecast at all? ===")
        print(parity.to_string(index=False))
    else:
        print(f"\n[{args.scope}] carries no staged org_weight, so there is no "
              "weighted arm to compare against.")

    print(f"\n=== paired vs {BASELINE_ARM} (negative log-loss delta = the arm helps) ===")
    show = paired[paired.calibrated & paired.metric.eq("log_loss")]
    print(show[["base_variant", "arm", "coverage", "n", "delta", "lo", "hi", "favours"]]
          .round(5).to_string(index=False))
    print(f"\ncpu: {time.process_time() - t0:.0f}s")


if __name__ == "__main__":
    main()
