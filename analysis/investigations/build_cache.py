"""Pre-warm every cached artifact the top-100 era-skew notebook reads.

The notebook builds these itself when they are absent, so this script is only a
convenience: it moves the ~40 minutes of refits off the notebook's first run and
into a terminal, where progress is visible.

Usage::

    python -m analysis.investigations.build_cache
    python -m analysis.investigations.build_cache --force
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from analysis.investigations import era_skew as es


def step(label: str, fn) -> object:
    t0 = time.perf_counter()
    out = fn()
    size = len(out) if hasattr(out, "__len__") else "-"
    print(f"[{label}] {size} rows in {time.perf_counter() - t0:.0f}s", flush=True)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--snapshot", type=Path, default=es.DEFAULT_SNAPSHOT)
    ap.add_argument("--force", action="store_true", help="rebuild even if cached")
    args = ap.parse_args()

    fights = es.load_fights(args.snapshot)
    history = es.load_history(args.snapshot)

    step("w2_sweep", lambda: es.w2_sweep(fights, force=args.force))
    step("prequential_w2", lambda: es.prequential_w2(fights, force=args.force))
    step("truncation", lambda: es.truncation_population(fights, history, force=args.force))

    majors = pd.read_parquet(PROJECT_ROOT / "data/external/sherdog/majors_bouts.parquet")
    majors["event_date"] = pd.to_datetime(majors["event_date"])
    identity = step("identity", lambda: es.identity_map(fights, majors, force=args.force))
    joint = es.joint_fights(fights, majors, identity)
    print(f"[joint] {len(joint):,} bouts", flush=True)
    step("joint_history", lambda: es.joint_history(joint, force=args.force))

    step("bootstrap_ufc60", lambda: es.bootstrap_board(
        fights, replicates=60, cache_name="bootstrap_ufc60", force=args.force))
    step("bootstrap_joint", lambda: es.bootstrap_board(
        joint, replicates=60, cache_name="bootstrap_joint", force=args.force))

    print(f"cache ready: {es.CACHE_DIR}")


if __name__ == "__main__":
    main()
