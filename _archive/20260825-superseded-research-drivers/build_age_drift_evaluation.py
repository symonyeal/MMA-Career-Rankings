"""Validate the empirical age-dependent WHR prior before production use."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from analysis.investigations.era_skew import unbeaten_cut
from ratings import prequential as PQ
from ratings.age import load_birth_dates
from ratings.rate_snapshot import attach_bout_weights
from ratings.whr import run_whr


def _event_delta(predictions: pd.DataFrame, *, segment: str) -> dict:
    base = predictions[predictions["variant"].eq("whr")].set_index("fight_url")
    age = predictions[predictions["variant"].eq("whr_age_drift")].set_index("fight_url")
    shared = base.index.intersection(age.index)
    a, b = base.loc[shared], age.loc[shared]
    if segment == "over_35":
        keep = a["involves_over_35"].fillna(False).astype(bool)
        a, b = a[keep], b[keep]
    y = a["y_a"].to_numpy(dtype=float)
    pa = np.clip(a["p_a"].to_numpy(dtype=float), 1e-6, 1 - 1e-6)
    pb = np.clip(b["p_a"].to_numpy(dtype=float), 1e-6, 1 - 1e-6)
    delta = -(y * np.log(pb) + (1 - y) * np.log(1 - pb))
    delta += y * np.log(pa) + (1 - y) * np.log(1 - pa)
    frame = pd.DataFrame({
        "event_date": a["event_date"].to_numpy(),
        "event_name": a["event_name"].to_numpy(),
        "delta": delta,
    })
    events = frame.groupby(["event_date", "event_name"])["delta"].agg(["sum", "size"])
    rng = np.random.default_rng(20260824)
    values = events.to_numpy(dtype=float)
    draws = rng.integers(0, len(values), size=(2000, len(values)))
    boot = values[draws, 0].sum(axis=1) / values[draws, 1].sum(axis=1)
    return {
        "segment": segment,
        "bouts": int(len(frame)),
        "events": int(len(events)),
        "log_loss_delta_age_minus_driftless": float(delta.mean()),
        "lo": float(np.quantile(boot, 0.025)),
        "hi": float(np.quantile(boot, 0.975)),
        "verdict": (
            "better" if np.quantile(boot, 0.975) < 0
            else "worse" if np.quantile(boot, 0.025) > 0
            else "unresolved"
        ),
    }


def _peak_at(history: pd.DataFrame, fighter: str) -> tuple[pd.Timestamp, float]:
    mine = history[history["fighter"].eq(fighter)]
    row = mine.loc[mine["mu_whr"].idxmax()]
    return pd.Timestamp(row["event_date"]), float(row["mu_whr"])


def _same_date(history: pd.DataFrame, fighter: str, date: pd.Timestamp) -> float:
    row = history[history["fighter"].eq(fighter) & history["event_date"].eq(date)]
    return float(row["mu_whr"].iloc[0])


def truncation_panel(
    fights: pd.DataFrame,
    birth_dates: dict[str, pd.Timestamp],
) -> pd.DataFrame:
    base_full = run_whr(attach_bout_weights(fights))
    age_full = run_whr(
        attach_bout_weights(fights), birth_dates=birth_dates, age_drift=True
    )
    rows = []
    for fighter in ("Tony Ferguson", "Anderson Silva", "BJ Penn", "Jon Jones"):
        cut = unbeaten_cut(fights, fighter)
        own = fights["fighter_a"].eq(fighter) | fights["fighter_b"].eq(fighter)
        train = fights[~(own & (fights["event_date"] > cut["cut_date"]))]
        base_truncated = run_whr(attach_bout_weights(train))
        age_truncated = run_whr(
            attach_bout_weights(train), birth_dates=birth_dates, age_drift=True
        )
        base_date, base_peak = _peak_at(base_truncated, fighter)
        age_date, age_peak = _peak_at(age_truncated, fighter)
        rows.append({
            "fighter": fighter,
            "cut_date": cut["cut_date"],
            "base_truncated_peak": base_peak,
            "base_full_same_date": _same_date(base_full, fighter, base_date),
            "base_revision": _same_date(base_full, fighter, base_date) - base_peak,
            "age_truncated_peak": age_peak,
            "age_full_same_date": _same_date(age_full, fighter, age_date),
            "age_revision": _same_date(age_full, fighter, age_date) - age_peak,
            "age_full_peak": float(
                age_full.loc[age_full["fighter"].eq(fighter), "mu_whr"].max()
            ),
            "base_full_peak": float(
                base_full.loc[base_full["fighter"].eq(fighter), "mu_whr"].max()
            ),
        })
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot_dir", type=Path)
    parser.add_argument("--events", type=int, default=30)
    parser.add_argument("--iterations", type=int, default=30)
    parser.add_argument("--out-dir", type=Path, default=Path("data/model_tuning/age-drift"))
    args = parser.parse_args()

    inputs = PQ.build_inputs(args.snapshot_dir, scope="ufc")
    events = PQ.choose_eval_events(
        inputs.fights, n_events=args.events, mode="stratified", since_year=2010
    )
    variants = [
        PQ.Variant("whr", engine="whr"),
        PQ.Variant("whr_age_drift", engine="whr", use_age_drift=True),
    ]
    predictions = pd.concat([
        PQ.whr_predictions(
            inputs, variant, events, iterations=args.iterations, progress=True
        )
        for variant in variants
    ], ignore_index=True)
    shared = predictions.groupby("fight_url")["variant"].nunique().eq(2)
    predictions = predictions[predictions["fight_url"].isin(shared[shared].index)]

    summary = {
        "snapshot": args.snapshot_dir.name,
        "events_requested": int(args.events),
        "iterations": int(args.iterations),
        "birth_dates": int(len(inputs.birth_dates)),
        "prediction": [
            _event_delta(predictions, segment="overall"),
            _event_delta(predictions, segment="over_35"),
        ],
    }
    panel = truncation_panel(inputs.fights, load_birth_dates(args.snapshot_dir))
    summary["truncation_panel"] = panel.to_dict("records")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    predictions.to_parquet(args.out_dir / "predictions.parquet", index=False)
    panel.to_parquet(args.out_dir / "truncation_panel.parquet", index=False)
    (args.out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
