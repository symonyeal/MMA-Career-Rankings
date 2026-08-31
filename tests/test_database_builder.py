from pathlib import Path
import sqlite3

import pandas as pd
import pytest

from build_database import TABLE_SPECS, build_database


def _tables(con: sqlite3.Connection) -> set[str]:
    rows = con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return {row[0] for row in rows}


def _indexes(con: sqlite3.Connection, table_name: str) -> set[str]:
    return {row[1] for row in con.execute(f'PRAGMA index_list("{table_name}")').fetchall()}


def _synthetic_snapshot(path: Path) -> Path:
    """Small complete bundle: database tests should test structure, not old data."""
    path.mkdir(parents=True)
    one_fight = {
        "fight_url": ["fight/1"],
        "event_date": [pd.Timestamp("2024-01-01")],
        "event_name": ["Event 1"],
        "fighter_a": ["Alice"],
        "fighter_b": ["Bob"],
        "winner": ["Alice"],
    }
    frames = {
        "canonical_events.parquet": pd.DataFrame(
            {"event_date": [pd.Timestamp("2024-01-01")], "event_name": ["Event 1"]}
        ),
        "canonical_fights.parquet": pd.DataFrame(one_fight),
        "canonical_rounds.parquet": pd.DataFrame(
            {
                "fight_url": ["fight/1"],
                "fighter": ["Alice"],
                "event_date": [pd.Timestamp("2024-01-01")],
            }
        ),
        "canonical_fighters.parquet": pd.DataFrame({"fighter": ["Alice", "Bob"]}),
        "ratings_current.parquet": pd.DataFrame(
            {
                "fighter": ["Alice", "Bob"],
                "last_event_date": [pd.Timestamp("2024-01-01")] * 2,
            }
        ),
        "ratings_history.parquet": pd.DataFrame(
            {
                "fighter": ["Alice", "Bob"],
                "event_date": [pd.Timestamp("2024-01-01")] * 2,
            }
        ),
        "fight_dominance.parquet": pd.DataFrame({"fight_url": ["fight/1"]}),
        "fighter_dominance.parquet": pd.DataFrame({"fighter": ["Alice", "Bob"]}),
        "prime_board.parquet": pd.DataFrame(
            {
                "rank": [1],
                "fighter": ["Alice"],
                "symon_prime_score": [1700.0],
                "status": ["ranked"],
            }
        ),
    }
    for name, frame in frames.items():
        frame.to_parquet(path / name, index=False)
    pd.DataFrame(
        columns=["fight_url", "event_date", "event_name"]
    ).to_csv(path / "_excluded_bouts.csv", index=False)
    pd.DataFrame(columns=["fight_url", "ped_flagged_fighter"]).to_csv(
        path / "ped_confirmed_bouts.csv", index=False
    )
    return path


def test_board_artifacts_are_optional_database_views():
    specs = {spec.table_name: spec for spec in TABLE_SPECS}
    expected = {
        "integrity_ledger": "integrity_ledger.parquet",
        "integrity_discounted_board": "integrity_discounted_board.parquet",
        "completeness_gated_board": "completeness_gated_board.parquet",
        "completeness_gated_board_women": "completeness_gated_board_women.parquet",
        "prime_board": "prime_board.parquet",
        "prime_board_women": "prime_board_women.parquet",
    }
    for table_name, file_name in expected.items():
        assert specs[table_name].file_name == file_name
        assert specs[table_name].required is False


def test_build_database_contains_core_tables_counts_and_indexes(tmp_path: Path):
    snapshot = _synthetic_snapshot(tmp_path / "snapshot")
    database = tmp_path / "ufc_rank_engine.sqlite"
    summary = build_database(snapshot, database)

    assert summary["canonical_fights"] == 1
    assert summary["ratings_current"] == 2
    assert summary["sqlite_table_count"] >= 14

    with sqlite3.connect(database) as con:
        tables = _tables(con)
        assert {
            "canonical_events",
            "canonical_fights",
            "canonical_rounds",
            "canonical_fighters",
            "ratings_current",
            "ratings_history",
            "fight_dominance",
            "fighter_dominance",
            "excluded_bouts",
            "ped_confirmed_bouts",
            "prime_board",
            "source_manifest",
            "snapshot_manifest",
            "table_row_counts",
            "source_gaps",
        }.issubset(tables)

        counts = dict(con.execute("SELECT table_name, row_count FROM table_row_counts").fetchall())
        assert counts["canonical_fights"] == summary["canonical_fights"]
        assert counts["ratings_current"] == summary["ratings_current"]

        canonical_fight_indexes = _indexes(con, "canonical_fights")
        assert "idx_canonical_fights_fight_url" in canonical_fight_indexes
        assert "idx_canonical_fights_event_date" in canonical_fight_indexes
        assert "idx_canonical_fights_event_name" in canonical_fight_indexes

        ratings_history_indexes = _indexes(con, "ratings_history")
        assert "idx_ratings_history_fighter_event_date" in ratings_history_indexes

        assert "idx_prime_board_rank_fighter" in _indexes(con, "prime_board")

        gaps = dict(con.execute("SELECT gap_key, status FROM source_gaps").fetchall())
        assert (
            gaps.get("cross_org_bouts_not_integrated") == "pending"
            or gaps.get("cross_org_bouts_integrated") == "loaded"
        )
        assert (
            gaps.get("odds_source_not_ingested") == "pending"
            or gaps.get("odds_source_ingested") == "loaded"
        )


def test_failed_rebuild_preserves_the_last_good_database(tmp_path: Path):
    snapshot = _synthetic_snapshot(tmp_path / "snapshot")
    database = tmp_path / "ufc_rank_engine.sqlite"
    build_database(snapshot, database)
    before = database.read_bytes()

    (snapshot / "canonical_fights.parquet").unlink()
    with pytest.raises(FileNotFoundError, match="required snapshot source missing"):
        build_database(snapshot, database)

    assert database.read_bytes() == before
    assert not database.with_name(f"{database.name}.building").exists()


def test_mid_build_failure_cleans_staging_and_preserves_database(tmp_path: Path):
    snapshot = _synthetic_snapshot(tmp_path / "snapshot")
    database = tmp_path / "ufc_rank_engine.sqlite"
    build_database(snapshot, database)
    before = database.read_bytes()

    # The path still passes required-source preflight, but parsing fails after
    # the sibling database has been opened and partially populated.
    (snapshot / "ratings_history.parquet").write_bytes(b"not a parquet file")
    with pytest.raises(Exception):
        build_database(snapshot, database)

    assert database.read_bytes() == before
    assert not database.with_name(f"{database.name}.building").exists()


def test_retired_sleeve_histories_are_not_database_views():
    names = {spec.table_name for spec in TABLE_SPECS}
    assert "ratings_history_method_integrity" not in names
    assert "ratings_history_method_performance" not in names
    assert "ratings_history_method_integrity_performance" not in names
    assert "sleeve_attribution" not in names
