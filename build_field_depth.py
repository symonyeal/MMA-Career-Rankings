"""Persist division-year field depth and opponent-quality percentiles.

Phase 0 of the whole-sport plan, and the only phase that changes no ratings.
Writes into the snapshot:

  field_depth.parquet             D(d, a), the contender line, field size
  field_percentiles.parquet       every fighter-division-year, scale-free
  opponent_quality_timeline.parquet   per-bout opponent quality, raw and relative

The last one is the diagnostic that relocates an era argument. Raw opponent
rating says Jon Jones's 2016-2019 opposition (1560) was about what he faced in
2008-2013 (1575); measured inside the contemporaneous field, 2008-2013 was an
ascent through the division and 2016-2019 was a decline away from its top. The
engine previously published neither column.

Usage::

    python build_field_depth.py data/snapshots/2026-08-13
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from ratings.field_depth import (
    DEFAULT_TOP_K,
    appearance_field,
    division_year_depth,
    field_percentile,
    opponent_quality_timeline,
)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("snapshot_dir", type=Path)
    ap.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    ap.add_argument("--history", default="ratings_history_whr.parquet")
    args = ap.parse_args()

    history = pd.read_parquet(args.snapshot_dir / args.history)
    fights = pd.read_parquet(args.snapshot_dir / "canonical_fights.parquet")

    appearances = appearance_field(history, fights)
    depth = division_year_depth(appearances, top_k=args.top_k)
    percentiles = field_percentile(appearances)
    timeline = opponent_quality_timeline(fights, appearances)

    depth.to_parquet(args.snapshot_dir / "field_depth.parquet", index=False)
    percentiles.to_parquet(args.snapshot_dir / "field_percentiles.parquet", index=False)
    timeline.to_parquet(args.snapshot_dir / "opponent_quality_timeline.parquet", index=False)

    summary = {
        "top_k": int(args.top_k),
        "appearances": int(len(appearances)),
        "division_years": int(len(depth)),
        "divisions": sorted(depth["division"].dropna().unique().tolist()),
        "thin_division_years": int(depth["thin_field"].sum()),
        "deepest": depth.nlargest(3, "depth")[["division", "year", "depth"]].to_dict("records"),
        "shallowest": depth.nsmallest(3, "depth")[["division", "year", "depth"]].to_dict("records"),
    }
    (args.snapshot_dir / "field_depth.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
