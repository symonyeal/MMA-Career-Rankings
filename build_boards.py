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
    UNRANKED_AT_FLOOR_STATUS,
    completeness_gated_board,
    integrity_discounted_board,
    integrity_ledger,
)
from ratings.constants import SUSTAINED_PEAK_MIN_FIGHTS  # board eligibility floor
from ratings.scope import DEFAULT_PUBLISHED_SCOPE


# The public/core board may use the engine's unit-consistent career aggregate,
# but the integrity debit is denominated in rating points.  Until a debit is
# defined in rating-point-years, keep that judgement on a base WHR point scale.
CORE_RATING_CANDIDATES = (
    "public_legacy_score",
    "symon_career_skill_mass",
    "mu_whr",
)
INTEGRITY_RATING_CANDIDATES = (
    "mu_whr",
)

# Scores with a hard floor that means "no evidence of clearing the bar", not
# "the lowest measured level". Career Skill Mass sums a clipped positive excess,
# so zero is an abstention and every fighter sitting on it is tied, not ordered.
# Base WHR mu has no such floor and must not appear here.
RATING_FLOOR_IS_UNRANKED = {
    "public_legacy_score": 0.0,
    "symon_career_skill_mass": 0.0,
}


def _select_rating_col(
    current: pd.DataFrame,
    candidates: tuple[str, ...],
    *,
    board_name: str,
) -> str:
    for column in candidates:
        if column in current.columns:
            return column
    raise ValueError(
        f"cannot build {board_name}: none of the supported rating columns are present "
        f"({', '.join(candidates)})"
    )


def select_core_rating_col(current: pd.DataFrame) -> str:
    """Choose the lean headline score, never a retired weighted stream."""
    return _select_rating_col(current, CORE_RATING_CANDIDATES, board_name="core board")


def select_integrity_rating_col(current: pd.DataFrame) -> str:
    """Choose a base WHR point score compatible with the direct integrity debit."""
    return _select_rating_col(
        current,
        INTEGRITY_RATING_CANDIDATES,
        board_name="integrity-discounted board",
    )


def public_legacy_eligibility_override(current: pd.DataFrame) -> pd.Series:
    """Let proven UFC title resumes rank before the generic 13-period floor."""
    idx = current.index
    periods = pd.to_numeric(current.get("rating_periods", pd.Series(0, index=idx)), errors="coerce").fillna(0)
    score = pd.to_numeric(current.get("public_legacy_score", pd.Series(0, index=idx)), errors="coerce").fillna(0)
    title_wins = pd.to_numeric(
        current.get("public_legacy_title_wins", pd.Series(0, index=idx)), errors="coerce"
    ).fillna(0)
    title_defenses = pd.to_numeric(
        current.get("public_legacy_title_defenses", pd.Series(0, index=idx)), errors="coerce"
    ).fillna(0)
    ufc_bouts = pd.to_numeric(
        current.get("public_legacy_ufc_bouts", pd.Series(0, index=idx)), errors="coerce"
    ).fillna(0)
    return (
        periods.ge(8)
        & ufc_bouts.ge(8)
        & score.gt(0)
        & (title_wins.ge(3) | (title_wins.ge(2) & title_defenses.ge(1)))
    )


def _requested_core_rating_col(current: pd.DataFrame, requested: str | None) -> str:
    if requested is None:
        return select_core_rating_col(current)
    if "whr_integrity_performance" in requested:
        raise ValueError("retired whr_integrity_performance scores cannot be a core board")
    if requested not in current.columns:
        raise ValueError(f"requested core rating column is absent: {requested}")
    return requested


def _requested_integrity_rating_col(current: pd.DataFrame, requested: str | None) -> str:
    if requested is None:
        return select_integrity_rating_col(current)
    if requested not in INTEGRITY_RATING_CANDIDATES:
        raise ValueError(
            "the integrity debit is defined only for base WHR rating-point columns: "
            f"{', '.join(INTEGRITY_RATING_CANDIDATES)}"
        )
    if requested not in current.columns:
        raise ValueError(f"requested integrity rating column is absent: {requested}")
    return requested


def write_board_artifacts(
    snapshot_dir: Path,
    *,
    rating_col: str | None = None,
    integrity_rating_col: str | None = None,
    min_rating_periods: int = SUSTAINED_PEAK_MIN_FIGHTS,
    scope: str = DEFAULT_PUBLISHED_SCOPE,
    out_dir: Path | None = None,
) -> dict[str, object]:
    """Build and persist the three standard board views for one snapshot.

    ``rating_col`` controls the completeness-gated core view.  The integrity
    view deliberately has a separate selector because its debit is measured in
    ordinary rating points and therefore must not be applied to Career Skill
    Mass (rating-point-years).
    """
    snap = Path(snapshot_dir)
    current = pd.read_parquet(snap / "ratings_current.parquet")
    appearances = pd.read_parquet(snap / "integrity_appearances.parquet")
    fights = PQ.load_fight_table(snap, scope=scope)

    core_col = _requested_core_rating_col(current, rating_col)
    integrity_col = _requested_integrity_rating_col(current, integrity_rating_col)
    ledger = integrity_ledger(appearances, fights)
    board = integrity_discounted_board(current, ledger, rating_col=integrity_col)
    eligibility_override = (
        public_legacy_eligibility_override(current)
        if core_col == "public_legacy_score"
        else None
    )
    gated = completeness_gated_board(
        current,
        rating_col=core_col,
        min_rating_periods=min_rating_periods,
        eligibility_override=eligibility_override,
        unranked_at_or_below=RATING_FLOOR_IS_UNRANKED.get(core_col),
    )

    target = Path(out_dir) if out_dir is not None else (
        snap
        if not any(snap.glob("*_FINALIZED"))
        else Path("data/model_tuning") / snap.name
    )
    target.mkdir(parents=True, exist_ok=True)
    ledger.to_parquet(target / "integrity_ledger.parquet", index=False)
    board.to_parquet(target / "integrity_discounted_board.parquet", index=False)
    gated.to_parquet(target / "completeness_gated_board.parquet", index=False)

    return {
        "out_dir": target,
        "scope": scope,
        "core_rating_col": core_col,
        "integrity_rating_col": integrity_col,
        "ledger_rows": len(ledger),
        "ledger_fighters": ledger["fighter"].nunique() if len(ledger) else 0,
        "board_rows": len(board),
        "debited_fighters": int((board["integrity_cost"] > 0).sum()) if len(board) else 0,
        "ranked_fighters": int(gated["status"].eq("ranked").sum()) if len(gated) else 0,
        "withheld_fighters": int((~gated["status"].eq("ranked")).sum()) if len(gated) else 0,
        "unranked_at_floor": (
            int(gated["status"].eq(UNRANKED_AT_FLOOR_STATUS).sum()) if len(gated) else 0
        ),
        "eligibility_overrides": (
            int(gated.get("eligibility_override", pd.Series(False, index=gated.index)).sum())
            if len(gated) else 0
        ),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("snapshot_dir", type=Path)
    ap.add_argument(
        "--rating-col",
        default=None,
        help="Core completeness-board score; defaults to Career Skill Mass, then base WHR.",
    )
    ap.add_argument(
        "--integrity-rating-col",
        choices=INTEGRITY_RATING_CANDIDATES,
        default=None,
        help="Base WHR point score for the direct integrity debit.",
    )
    ap.add_argument("--min-rating-periods", type=int, default=SUSTAINED_PEAK_MIN_FIGHTS)
    ap.add_argument("--scope", default=DEFAULT_PUBLISHED_SCOPE)
    ap.add_argument("--top", type=int, default=25)
    ap.add_argument("--out-dir", type=Path, default=None)
    args = ap.parse_args()

    summary = write_board_artifacts(
        args.snapshot_dir,
        rating_col=args.rating_col,
        integrity_rating_col=args.integrity_rating_col,
        min_rating_periods=args.min_rating_periods,
        scope=args.scope,
        out_dir=args.out_dir,
    )
    out = Path(summary["out_dir"])
    ledger = pd.read_parquet(out / "integrity_ledger.parquet")
    board = pd.read_parquet(out / "integrity_discounted_board.parquet")
    gated = pd.read_parquet(out / "completeness_gated_board.parquet")
    core_col = str(summary["core_rating_col"])
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
          f"{len(gated) - len(ranked):,} withheld")
    print(gated.loc[~gated["status"].eq("ranked"), "status"].value_counts().to_string())
    print(ranked.head(args.top)[["rank", "fighter", core_col]].round(1).to_string(index=False))
    print(f"\nwritten to {out}")


if __name__ == "__main__":
    main()
