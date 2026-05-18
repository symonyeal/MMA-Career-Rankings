from pathlib import Path

import pandas as pd
import pytest

from loaders.ufcstats_loader import (
    UFC_28_DATE,
    build_canonical_fights,
    build_canonical_rounds,
    load_raw,
    parse_events,
)
from ratings.rate_snapshot import run as run_ratings


RAW_DIR = Path("data/raw/2026-05-13")


def test_loader_to_engine_roundtrip_on_ten_event_slice(tmp_path: Path):
    if not RAW_DIR.exists():
        pytest.skip(f"project-local raw source directory not present: {RAW_DIR}")

    raw = load_raw(RAW_DIR)
    events = parse_events(raw["events"])
    event_names = (
        events[events["event_date"] >= UFC_28_DATE]
        .sort_values("event_date")
        .head(10)["event_name"]
        .tolist()
    )
    assert len(event_names) == 10

    results_slice = raw["results"][raw["results"]["EVENT"].isin(event_names)].copy()
    stats_slice = raw["stats"][raw["stats"]["EVENT"].isin(event_names)].copy()

    fights_all = build_canonical_fights(results_slice, events)
    fights = fights_all[(fights_all["event_date"] >= UFC_28_DATE) & ~fights_all["is_excluded"]].copy()
    rounds = build_canonical_rounds(stats_slice, fights_all)
    rounds = rounds[rounds["fight_url"].isin(fights["fight_url"])].copy()

    assert len(fights) > 0
    assert len(rounds) > 0

    snapshot_dir = tmp_path / "loader_roundtrip_snapshot"
    snapshot_dir.mkdir(parents=True)
    fights.to_parquet(snapshot_dir / "canonical_fights.parquet", index=False)
    rounds.to_parquet(snapshot_dir / "canonical_rounds.parquet", index=False)

    summary = run_ratings(snapshot_dir)
    current = pd.read_parquet(snapshot_dir / "ratings_current.parquet")
    history = pd.read_parquet(snapshot_dir / "ratings_history.parquet")

    assert summary["events_processed"] == 10
    assert summary["current_fighters"] > 20
    assert summary["history_rows"] == len(history)
    assert current["mu_canonical"].max() > 1500
    assert current["mu_canonical"].min() < 1500
    assert current.sort_values("mu_canonical", ascending=False).iloc[0]["fighter"]
