"""Compare UFC-only and public FightMatrix-cohort rating snapshots."""
from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pandas as pd

from project_helpers import normalize_name_key


SCORE_CANDIDATES = (
    "symon_career_skill_mass",
    "mu_whr",
)


def resolve_score_column(
    frames: Sequence[pd.DataFrame],
    requested: str | None = None,
) -> str:
    """Return the score column every scope carries, preferring the public one.

    Scopes are compared on one shared column or not at all: a scope missing the
    requested score is a data error, not a reason to score it differently.
    """
    if requested is not None:
        missing = [i for i, frame in enumerate(frames) if requested not in frame.columns]
        if missing:
            raise ValueError(f"score column is not present in every scope: {requested}")
        return requested
    for column in SCORE_CANDIDATES:
        if all(column in frame.columns for frame in frames):
            return column
    raise ValueError(
        "no common lean-core score column found; expected one of "
        + ", ".join(SCORE_CANDIDATES)
    )


def _ranked(frame: pd.DataFrame, prefix: str, score_column: str) -> pd.DataFrame:
    out = frame.copy()
    if "gender" in out.columns:
        out = out[out["gender"].eq("M")]
    out = out.dropna(subset=["fighter", score_column]).copy()
    out[f"{prefix}_rank"] = out[score_column].rank(method="min", ascending=False).astype(int)
    columns = ["fighter", score_column, f"{prefix}_rank"]
    if "rating_periods" in out.columns:
        columns.append("rating_periods")
    return out[columns].rename(columns={
        score_column: f"{prefix}_score",
        "rating_periods": f"{prefix}_rating_periods",
    })


def build_scope_comparison(
    ufc_snapshot: Path,
    public_snapshot: Path,
    *,
    output_path: Path | None = None,
    score_column: str | None = None,
) -> pd.DataFrame:
    """Return one row per fighter comparing the two source scopes."""
    ufc_snapshot = Path(ufc_snapshot)
    public_snapshot = Path(public_snapshot)
    ufc = pd.read_parquet(ufc_snapshot / "ratings_current.parquet")
    public = pd.read_parquet(public_snapshot / "ratings_current.parquet")
    score_column = resolve_score_column((ufc, public), score_column)
    out = _ranked(ufc, "ufc_only", score_column).merge(
        _ranked(public, "fightmatrix_public", score_column),
        on="fighter",
        how="outer",
    )
    out["score_delta_public_minus_ufc"] = (
        out["fightmatrix_public_score"] - out["ufc_only_score"]
    )
    out["rank_shift_public_minus_ufc"] = (
        out["fightmatrix_public_rank"] - out["ufc_only_rank"]
    )

    reference_path = public_snapshot / "fightmatrix_all_time.parquet"
    if not reference_path.exists():
        reference_path = ufc_snapshot / "fightmatrix_all_time.parquet"
    if reference_path.exists():
        ref = pd.read_parquet(reference_path)[["fighter", "rank", "points"]].copy()
        ref["name_key"] = ref["fighter"].map(lambda value: normalize_name_key(value, compact=True))
        ref = ref.rename(columns={
            "rank": "fightmatrix_reference_rank",
            "points": "fightmatrix_reference_points",
        }).drop(columns="fighter")
        out["name_key"] = out["fighter"].map(lambda value: normalize_name_key(value, compact=True))
        out = out.merge(ref, on="name_key", how="left").drop(columns="name_key")

    out = out.sort_values(
        ["ufc_only_rank", "fightmatrix_public_rank"], na_position="last"
    ).reset_index(drop=True)
    if output_path is not None:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        out.to_parquet(output_path, index=False)
    return out
