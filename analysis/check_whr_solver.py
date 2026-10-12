"""Compare the corrected solver with a Git revision on historical held-out cards.

INPUT   snapshot, baseline revision, evaluation year, coordinate passes.
OUTPUT  paired predictions and event-bootstrap loss differences.
Missing birth dates imply neutral age drift; this does not reproduce a release.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import types
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ratings.constants import WHR_ITERATIONS, WHR_W2_PER_DAY
from ratings.prequential import load_fight_table, paired_delta
from ratings.rate_snapshot import attach_bout_weights
from ratings.whr import production_score_kwargs, run_whr
from ratings.whr_backtest import _decided_bouts, elo_win_prob


def compare(snapshot: Path, baseline: str, year: int, iterations: int) -> tuple[pd.DataFrame, dict]:
    """Fit only dates before each held-out UFC card; require three prior bouts."""
    root = Path(__file__).resolve().parents[1]
    source = subprocess.check_output(["git", "show", f"{baseline}:ratings/whr.py"], cwd=root, text=True)
    old = types.ModuleType("whr_baseline")
    exec(compile(source, f"{baseline}:ratings/whr.py", "exec"), old.__dict__)  # noqa: S102 -- the baseline solver is this repo's own committed source
    scope = "majors,pre_unified"
    f = attach_bout_weights(load_fight_table(snapshot, scope=scope))
    bouts = _decided_bouts(f)
    test = bouts[bouts["org"].eq("UFC") & bouts["event_date"].dt.year.eq(year)]
    rows = []
    for (t, event), card in test.groupby(["event_date", "event_name"]):
        train = f[f["event_date"] < t]
        counts = pd.concat([train["fighter_a"], train["fighter_b"]]).value_counts()
        for name, solve in [("baseline", old.run_whr), ("corrected", run_whr)]:
            h = solve(train, iterations=iterations, age_drift=True, birth_dates={},
                      **production_score_kwargs(train))
            mu = h.sort_values(["fighter", "event_date", "event_name"]).groupby("fighter").tail(1)
            mu = mu.set_index("fighter")["mu_whr"]
            for b in card.itertuples(index=False):
                a, c = b.fighter_a, b.fighter_b
                if counts.get(a, 0) < 3 or counts.get(c, 0) < 3:
                    continue
                rows.append({"fight_url": b.fight_url, "event_date": t, "event_name": event,
                             "variant": name, "y_a": int(b.winner == a),
                             "p_a": float(np.clip(elo_win_prob(mu[a], mu[c]), 1e-6, 1 - 1e-6))})
        print(f"scored {t.date()} {event}", flush=True)
    predictions = pd.DataFrame(rows)
    summary = {
        "baseline": baseline, "scope": scope, "evaluation_year": year,
        "iterations": iterations, "w2_per_day": WHR_W2_PER_DAY, "birth_dates": 0,
        "limitation": "Historical mechanism check with neutral age drift; release birth-date inputs absent.",
        "input_sha256": hashlib.sha256((snapshot / "combined_fights.parquet").read_bytes()).hexdigest(),
        "metrics": [paired_delta(predictions, "baseline", "corrected", metric=m)
                    for m in ["log_loss", "brier"]],
    }
    return predictions, summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--baseline", default="c0072b493cfbe2427d0c14744e7031dbd876ac74")
    parser.add_argument("--year", type=int, default=2004)
    parser.add_argument("--iterations", type=int, default=WHR_ITERATIONS)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    predictions, summary = compare(args.snapshot, args.baseline, args.year, args.iterations)
    args.out.mkdir(parents=True, exist_ok=True)
    predictions.to_csv(args.out / "predictions.csv", index=False)
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
