"""Compare the corrected solver with a Git revision on historical held-out cards.

INPUT   snapshot, baseline revision, evaluation years, coordinate passes, worker processes.
OUTPUT  paired predictions and event-bootstrap loss differences.
Each card costs two WHR fits on every earlier bout; cards run in parallel processes.
Missing birth dates imply neutral age drift; such a run does not reproduce a release.
"""
from __future__ import annotations

import argparse
import functools
import hashlib
import json
import subprocess
import sys
import types
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ratings.age import load_birth_dates
from ratings.constants import WHR_ITERATIONS, WHR_W2_PER_DAY
from ratings.prequential import load_fight_table, paired_delta
from ratings.rate_snapshot import attach_bout_weights
from ratings.whr import production_score_kwargs, project_age_rating, run_whr
from ratings.whr_backtest import _decided_bouts, elo_win_prob

SCOPE = "majors,pre_unified"
G: dict = {}  # per-process state, set once by _init


def _load(snapshot: Path) -> tuple[pd.DataFrame, dict]:
    f = attach_bout_weights(load_fight_table(snapshot, scope=SCOPE))
    return f, {str(k): v for k, v in load_birth_dates(snapshot).items()}


def _init(snapshot: Path, baseline: str, iterations: int) -> None:
    root = Path(__file__).resolve().parents[1]
    source = subprocess.check_output(["git", "show", f"{baseline}:ratings/whr.py"], cwd=root, text=True)
    old = types.ModuleType("whr_baseline")
    exec(compile(source, f"{baseline}:ratings/whr.py", "exec"), old.__dict__)  # noqa: S102 -- the baseline solver is this repo's own committed source
    f, dob = _load(snapshot)
    G.update(f=f, dob=dob, bouts=_decided_bouts(f), it=iterations,
             solvers=[("baseline", old.run_whr),
                      ("corrected", functools.partial(run_whr, center_each_pass=False))])


def _card(key: tuple[pd.Timestamp, str]) -> list[dict]:
    """Both solvers' forecasts for one card, fitted on bouts strictly before it."""
    t, event = key
    f, dob, bouts = G["f"], G["dob"], G["bouts"]
    train = f[f["event_date"] < t]
    card = bouts[bouts["event_date"].eq(t) & bouts["event_name"].eq(event) & bouts["org"].eq("UFC")]
    counts = pd.concat([train["fighter_a"], train["fighter_b"]]).value_counts()
    rows = []
    for name, solve in G["solvers"]:
        h = solve(train, iterations=G["it"], age_drift=True, birth_dates=dob, **production_score_kwargs(train))
        last = h.sort_values(["fighter", "event_date", "event_name"]).groupby("fighter").tail(1)
        drift = h.attrs["age_drift_elo_per_year"]
        mu = {r.fighter: project_age_rating(float(r.mu_whr), last_date=r.event_date, target_date=t,
                                            birth_date=dob.get(str(r.fighter)), drift_elo_per_year=drift)
              for r in last.itertuples(index=False)}
        for b in card.itertuples(index=False):
            a, c = b.fighter_a, b.fighter_b
            if counts.get(a, 0) < 3 or counts.get(c, 0) < 3:
                continue
            rows.append({"fight_url": b.fight_url, "event_date": t, "event_name": event,
                         "variant": name, "y_a": int(b.winner == a),
                         "p_a": float(np.clip(elo_win_prob(mu[a], mu[c]), 1e-6, 1 - 1e-6))})
    return rows


def compare(snapshot: Path, baseline: str, years: list[int], iterations: int,
            workers: int) -> tuple[pd.DataFrame, dict]:
    """Score every UFC card of ``years``; require three prior bouts per fighter."""
    f, dob = _load(snapshot)
    bouts = _decided_bouts(f)
    test = bouts[bouts["org"].eq("UFC") & bouts["event_date"].dt.year.isin(years)]
    keys = sorted(test.groupby(["event_date", "event_name"]).groups)
    rows = []
    with ProcessPoolExecutor(workers, initializer=_init, initargs=(snapshot, baseline, iterations)) as X:
        for k, r in enumerate(X.map(_card, keys), 1):
            rows += r
            print(f"scored {k}/{len(keys)} {keys[k - 1][0].date()} {keys[k - 1][1]}", flush=True)
    predictions = pd.DataFrame(rows)
    summary = {
        "baseline": baseline, "scope": SCOPE, "evaluation_years": years,
        "iterations": iterations, "w2_per_day": WHR_W2_PER_DAY, "birth_dates": len(dob),
        "limitation": "Production fit and age projection; no temperature calibration." if dob else
                      "Neutral age drift: no birth-date inputs in this snapshot.",
        "input_sha256": hashlib.sha256((snapshot / "combined_fights.parquet").read_bytes()).hexdigest(),
        "metrics": [paired_delta(predictions, "baseline", "corrected", metric=m)
                    for m in ["log_loss", "brier"]],
    }
    return predictions, summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--baseline", default="c0072b493cfbe2427d0c14744e7031dbd876ac74")
    parser.add_argument("--years", type=int, nargs="+", default=[2004])
    parser.add_argument("--iterations", type=int, default=WHR_ITERATIONS)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    predictions, summary = compare(args.snapshot, args.baseline, args.years, args.iterations, args.workers)
    args.out.mkdir(parents=True, exist_ok=True)
    predictions.to_csv(args.out / "predictions.csv", index=False)
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
