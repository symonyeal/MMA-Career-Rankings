"""Birth-date inputs for the age-dependent WHR prior."""
from __future__ import annotations

from pathlib import Path

import pandas as pd


def load_birth_dates(snapshot_dir: Path) -> dict[str, pd.Timestamp]:
    """One date per rating identity, preferring UFCStats over other sources."""
    snapshot_dir = Path(snapshot_dir)
    frames = []

    canonical = snapshot_dir / "canonical_fighters.parquet"
    if canonical.exists():
        frame = pd.read_parquet(canonical)
        if {"fighter", "dob"} <= set(frame.columns):
            frames.append(frame[["fighter", "dob"]].assign(priority=0))

    sherdog = snapshot_dir / "sherdog_birth_dates.parquet"
    if sherdog.exists():
        frame = pd.read_parquet(sherdog)
        if {"fighter", "dob"} <= set(frame.columns):
            frames.append(frame[["fighter", "dob"]].assign(priority=1))

    fightmatrix = snapshot_dir / "fightmatrix_profiles.parquet"
    if fightmatrix.exists():
        frame = pd.read_parquet(fightmatrix)
        if {"fighter", "birth_date"} <= set(frame.columns):
            frames.append(
                frame[["fighter", "birth_date"]]
                .rename(columns={"birth_date": "dob"})
                .assign(priority=2)
            )

    if not frames:
        return {}
    out = pd.concat(frames, ignore_index=True)
    out["dob"] = pd.to_datetime(out["dob"], errors="coerce")
    out = (
        out.dropna(subset=["fighter", "dob"])
        .sort_values(["priority", "fighter"], kind="mergesort")
        .drop_duplicates("fighter", keep="first")
    )
    return dict(zip(out["fighter"].astype(str), out["dob"]))
