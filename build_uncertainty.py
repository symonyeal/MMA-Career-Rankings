"""Bootstrap the public career board and persist its rank intervals.

Reruns the whole smoother under Dirichlet-reweighted events (see
``ratings/uncertainty.py``) and writes ``career_mass_uncertainty.parquet`` into
the snapshot, so the notebook can show every rank with the interval it deserves
instead of a bare integer.

Usage::

    python build_uncertainty.py data/snapshots/2026-08-13 --replicates 200
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import pandas as pd

from ratings.symon_score import DEFAULT_CAREER_REFERENCE
from ratings.uncertainty import career_mass_bootstrap


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("snapshot_dir", type=Path)
    ap.add_argument("--replicates", type=int, default=200)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--quantiles", default="0.025,0.975",
                    help="interval endpoints as lo,hi")
    # Follows the production bar by default: the snapshot once carried a
    # parquet built at the mean bar beside a summary json claiming 0.9, and a
    # reader had no way to tell which board the intervals described.
    ap.add_argument("--reference", default=str(DEFAULT_CAREER_REFERENCE),
                    help='yearly bar: "mean" or a quantile such as 0.9')
    ap.add_argument("--out", type=Path, default=None,
                    help="defaults to <snapshot>/career_mass_uncertainty.parquet")
    args = ap.parse_args()

    lo, hi = (float(x) for x in args.quantiles.split(","))
    reference = args.reference if args.reference == "mean" else float(args.reference)
    fights = pd.read_parquet(args.snapshot_dir / "canonical_fights.parquet")
    fights["event_date"] = pd.to_datetime(fights["event_date"])
    if "is_excluded" in fights.columns:
        fights = fights[~fights["is_excluded"].fillna(False).astype(bool)]

    print(f"[bootstrap] {len(fights):,} bouts, {args.replicates} replicates")
    t0 = time.perf_counter()
    board = career_mass_bootstrap(
        fights, replicates=args.replicates, seed=args.seed, lo=lo, hi=hi,
        mass_kwargs={"reference": reference},
    )
    wall = time.perf_counter() - t0

    out_path = args.out or (args.snapshot_dir / "career_mass_uncertainty.parquet")
    board.to_parquet(out_path, index=False)
    summary = {
        "replicates": int(args.replicates),
        "seed": int(args.seed),
        "interval": [lo, hi],
        "reference": str(reference),
        "fighters": int(len(board)),
        "wall_seconds": round(wall, 1),
        "median_rank_width_top50": float(
            (board.head(50)["rank_hi"] - board.head(50)["rank_lo"]).median()
        ),
    }
    (args.snapshot_dir / "career_mass_uncertainty.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8")
    print(f"[bootstrap] wrote {out_path} in {wall:.0f}s")
    print(json.dumps(summary, indent=2))
    top = board.head(20)[["fighter", "mass", "rank", "rank_lo", "rank_hi", "mass_sd"]]
    print(top.round(1).to_string(index=False))


if __name__ == "__main__":
    main()
