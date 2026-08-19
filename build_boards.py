"""Generate the boards that survived the 2026-08-18 differentiator audit.

Writes three artifacts next to the snapshot (or to ``--out-dir`` when the
snapshot is finalized):

* ``integrity_ledger.parquet`` — every discounted appearance, with the reason
* ``integrity_discounted_board.parquet`` — the judgement board and its bill
* ``completeness_gated_board.parquet`` — ranks who can be ranked, abstains otherwise

Usage::

    python build_boards.py data/snapshots/2026-08-13
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from ratings import prequential as PQ
from ratings.boards import (
    completeness_gated_board,
    integrity_discounted_board,
    integrity_ledger,
)
from ratings.constants import SUSTAINED_PEAK_MIN_FIGHTS


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("snapshot_dir", type=Path)
    ap.add_argument("--rating-col", default="sustained_peak_headline_mu_whr")
    ap.add_argument("--min-rating-periods", type=int, default=SUSTAINED_PEAK_MIN_FIGHTS)
    ap.add_argument("--top", type=int, default=25)
    ap.add_argument("--out-dir", type=Path, default=None)
    args = ap.parse_args()

    snap = Path(args.snapshot_dir)
    current = pd.read_parquet(snap / "ratings_current.parquet")
    appearances = pd.read_parquet(snap / "integrity_appearances.parquet")
    fights = PQ.load_fight_table(snap)

    ledger = integrity_ledger(appearances, fights)
    board = integrity_discounted_board(current, ledger, rating_col=args.rating_col)
    gated = completeness_gated_board(
        current, rating_col=args.rating_col, min_rating_periods=args.min_rating_periods)

    out = args.out_dir or (snap if not any(snap.glob("*_FINALIZED")) else Path("data/model_tuning") / snap.name)
    out.mkdir(parents=True, exist_ok=True)
    ledger.to_parquet(out / "integrity_ledger.parquet", index=False)
    board.to_parquet(out / "integrity_discounted_board.parquet", index=False)
    gated.to_parquet(out / "completeness_gated_board.parquet", index=False)

    debited = board[board["integrity_cost"] > 0]
    print(f"integrity ledger: {len(ledger):,} discounted appearances across "
          f"{ledger['fighter'].nunique() if len(ledger) else 0} fighters")
    if len(ledger):
        print(ledger["reason"].value_counts().to_string())
    print(f"\nboard: {len(board):,} rated fighters, {len(debited)} debited")
    if len(debited):
        print(debited[["rank", "undiscounted_rank", "rank_change", "fighter",
                       "integrity_cost", "discounted_fights"]]
              .sort_values("integrity_cost", ascending=False).round(1).to_string(index=False))

    ranked = gated[gated["status"].eq("ranked")]
    print(f"\ncompleteness-gated board: {len(ranked):,} ranked, "
          f"{len(gated) - len(ranked):,} withheld as insufficient history")
    print(ranked.head(args.top)[["rank", "fighter", args.rating_col]].round(1).to_string(index=False))
    print(f"\nwritten to {out}")


if __name__ == "__main__":
    main()
