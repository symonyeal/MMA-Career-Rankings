from pathlib import Path
import sqlite3

import pytest

from build_database import build_database


SNAPSHOT_DIR = Path("data/snapshots/2026-05-13")
DB_TMP = Path(".test_tmp/database_builder/ufc_rank_engine.sqlite")


def _tables(con: sqlite3.Connection) -> set[str]:
    rows = con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return {row[0] for row in rows}


def _indexes(con: sqlite3.Connection, table_name: str) -> set[str]:
    return {row[1] for row in con.execute(f'PRAGMA index_list("{table_name}")').fetchall()}


def test_build_database_contains_core_tables_counts_and_indexes():
    if not SNAPSHOT_DIR.exists():
        pytest.skip(f"snapshot not present: {SNAPSHOT_DIR}")

    DB_TMP.parent.mkdir(parents=True, exist_ok=True)
    if DB_TMP.exists():
        DB_TMP.unlink()
    summary = build_database(SNAPSHOT_DIR, DB_TMP)

    assert summary["canonical_fights"] > 8_000
    assert summary["ratings_current"] > 2_000
    assert summary["datalab_bouts_all"] > 8_000
    assert summary["fightmatrix_rankings"] > 100
    assert summary["sqlite_table_count"] >= 20

    with sqlite3.connect(DB_TMP) as con:
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
            "datalab_bouts_all",
            "datalab_merged_stats_scorecards",
            "datalab_fighter_details",
            "datalab_scorecards",
            "fightmatrix_rankings",
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

        gaps = dict(con.execute("SELECT gap_key, status FROM source_gaps").fetchall())
        assert (
            gaps.get("cross_org_bouts_not_integrated") == "pending"
            or gaps.get("cross_org_bouts_integrated") == "loaded"
        )
        assert (
            gaps.get("odds_source_not_ingested") == "pending"
            or gaps.get("odds_source_ingested") == "loaded"
        )


def test_build_database_loads_optional_sleeve_history_tables(tmp_path: Path):
    """Optional sleeve history tables surface in SQLite when their parquets exist."""
    import shutil
    import sqlite3 as _sqlite3
    import pandas as _pd

    if not SNAPSHOT_DIR.exists():
        pytest.skip(f"snapshot not present: {SNAPSHOT_DIR}")

    snap_copy = tmp_path / "snap"
    shutil.copytree(SNAPSHOT_DIR, snap_copy)

    # Minimal synthetic sleeve-history rows.
    for suffix in (
        "method_integrity",
        "method_performance",
        "method_integrity_performance",
    ):
        _pd.DataFrame([
            {
                "fighter": "A",
                "event_date": "2024-01-01",
                "event_name": "E1",
                f"mu_{suffix}": 1520.0,
                f"phi_{suffix}": 300.0,
                f"sigma_{suffix}": 0.06,
                "opponents_this_event": 1,
                "total_weight": 1.0,
            }
        ]).to_parquet(snap_copy / f"ratings_history_{suffix}.parquet", index=False)

    db = tmp_path / "ufc_rank_engine_sleeves.sqlite"
    build_database(snap_copy, db)
    with _sqlite3.connect(db) as con:
        tables = _tables(con)
        assert {
            "ratings_history_method_integrity",
            "ratings_history_method_performance",
            "ratings_history_method_integrity_performance",
        }.issubset(tables)
