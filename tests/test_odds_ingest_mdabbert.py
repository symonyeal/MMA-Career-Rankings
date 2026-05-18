"""Smoke tests for the mdabbert Ultimate UFC Dataset odds ingest."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from loaders.odds_ingest_mdabbert import (
    build_odds_lines,
    load_master_csv,
    merge_with_existing,
)
from loaders.odds_loader import RAW_ODDS_COLUMNS


def _write_minimal_csv(path: Path) -> Path:
    df = pd.DataFrame([
        {"R_fighter": "Alice", "B_fighter": "Bob", "R_odds": 150, "B_odds": -180,
         "date": "2024-01-01"},
        {"R_fighter": "Carol", "B_fighter": "Dave", "R_odds": -120, "B_odds": 100,
         "date": "2024-02-01"},
        {"R_fighter": "Eve", "B_fighter": "Frank", "R_odds": None, "B_odds": None,
         "date": "2024-03-01"},
    ])
    df.to_csv(path, index=False)
    return path


def test_load_master_csv_drops_rows_with_missing_odds(tmp_path: Path):
    csv = _write_minimal_csv(tmp_path / "ufc-master.csv")
    df = load_master_csv(csv)
    # 3 input rows, 1 missing both odds -> 2 rows kept.
    assert len(df) == 2
    assert {"R_fighter", "B_fighter", "R_odds", "B_odds", "date", "pair_key"}.issubset(df.columns)


def test_build_odds_lines_matches_canonical_pair_and_date(tmp_path: Path):
    csv = _write_minimal_csv(tmp_path / "ufc-master.csv")
    md = load_master_csv(csv)
    cf = pd.DataFrame([
        {"fight_url": "u/1", "event_date": "2024-01-01", "event_name": "E1",
         "fighter_a": "Alice", "fighter_b": "Bob"},
        {"fight_url": "u/2", "event_date": "2024-02-01", "event_name": "E2",
         "fighter_a": "Carol", "fighter_b": "Dave"},
        {"fight_url": "u/3", "event_date": "2024-04-01", "event_name": "E3",
         "fighter_a": "Eve", "fighter_b": "Frank"},
    ])
    lines = build_odds_lines(cf, md)
    assert set(lines.columns) == set(RAW_ODDS_COLUMNS)
    assert {"u/1", "u/2"}.issubset(set(lines["fight_url"]))
    # u/3 is excluded because its mdabbert row lacked odds.
    assert "u/3" not in set(lines["fight_url"])
    # Decimal odds were derived from American.
    row = lines[lines["fight_url"] == "u/1"].iloc[0]
    assert row["american_odds_a"] == 150
    assert row["decimal_odds_a"] == pytest.approx(2.5, rel=1e-6)


def test_merge_with_existing_prefers_new_rows(tmp_path: Path):
    new_rows = pd.DataFrame([{
        "fight_url": "u/1", "event_date": pd.Timestamp("2024-01-01"),
        "event_name": "E1", "fighter_a": "Alice", "fighter_b": "Bob",
        "odds_source": "mdabbert-ultimate-v1",
        "odds_fighter_a": "Alice", "odds_fighter_b": "Bob",
        "american_odds_a": 150, "american_odds_b": -180,
        "decimal_odds_a": 2.5, "decimal_odds_b": None,
    }])
    existing = pd.DataFrame([{
        "fight_url": "u/1", "event_date": pd.Timestamp("2024-01-01"),
        "event_name": "E1", "fighter_a": "Alice", "fighter_b": "Bob",
        "odds_source": "legacy",
        "odds_fighter_a": "Alice", "odds_fighter_b": "Bob",
        "american_odds_a": 99, "american_odds_b": 99,
        "decimal_odds_a": None, "decimal_odds_b": None,
    }, {
        "fight_url": "u/legacy-only", "event_date": pd.Timestamp("2024-02-01"),
        "event_name": "E2", "fighter_a": "X", "fighter_b": "Y",
        "odds_source": "legacy",
        "odds_fighter_a": "X", "odds_fighter_b": "Y",
        "american_odds_a": 50, "american_odds_b": -55,
        "decimal_odds_a": None, "decimal_odds_b": None,
    }])
    merged = merge_with_existing(new_rows, existing)
    assert set(merged["fight_url"]) == {"u/1", "u/legacy-only"}
    # Conflict on u/1 -> the mdabbert row wins.
    assert merged[merged["fight_url"] == "u/1"].iloc[0]["odds_source"] == "mdabbert-ultimate-v1"
