"""Build the local SQLite database from a snapshot bundle.

The database is a structured, queryable copy of the current parquet/CSV
snapshot. External sources are loaded either as staged comparison tables or,
when the snapshot contains them, as rated cross-organization bout inputs.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import pandas as pd

from loaders.odds_loader import compute_implied_probs
from project_helpers import date_range


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "ufc_rank_engine.sqlite"


@dataclass(frozen=True)
class TableSpec:
    table_name: str
    file_name: str
    source_name: str
    source_kind: str
    required: bool = True


TABLE_SPECS = [
    TableSpec("canonical_events", "canonical_events.parquet", "Greco", "canonical"),
    TableSpec("canonical_fights", "canonical_fights.parquet", "Greco", "canonical"),
    TableSpec("crossorg_fights", "crossorg_fights.parquet", "Sherdog", "canonical_extension", required=False),
    TableSpec("canonical_rounds", "canonical_rounds.parquet", "Greco", "canonical"),
    TableSpec("canonical_fighters", "canonical_fighters.parquet", "Greco", "canonical"),
    TableSpec("ratings_current", "ratings_current.parquet", "Rating engine", "ratings"),
    TableSpec("ratings_history", "ratings_history.parquet", "Rating engine", "ratings"),
    TableSpec(
        "ratings_history_method_integrity",
        "ratings_history_method_integrity.parquet",
        "Rating engine",
        "ratings",
        required=False,
    ),
    TableSpec(
        "ratings_history_method_performance",
        "ratings_history_method_performance.parquet",
        "Rating engine",
        "ratings",
        required=False,
    ),
    TableSpec(
        "ratings_history_method_integrity_performance",
        "ratings_history_method_integrity_performance.parquet",
        "Rating engine",
        "ratings",
        required=False,
    ),
    TableSpec(
        "ratings_history_whr",
        "ratings_history_whr.parquet",
        "WHR smoother",
        "ratings",
        required=False,
    ),
    TableSpec(
        "integrity_appearances",
        "integrity_appearances.parquet",
        "Rating engine",
        "derived",
        required=False,
    ),
    TableSpec(
        "performance_appearances",
        "performance_appearances.parquet",
        "Rating engine",
        "derived",
        required=False,
    ),
    TableSpec("fight_dominance", "fight_dominance.parquet", "Dominance model", "derived"),
    TableSpec("fighter_dominance", "fighter_dominance.parquet", "Dominance model", "derived"),
    TableSpec("calibration_residuals", "calibration_residuals.parquet", "Rating diagnostics", "diagnostic", required=False),
    TableSpec("sleeve_attribution", "sleeve_attribution.parquet", "Rating diagnostics", "diagnostic", required=False),
    TableSpec("division_entropy", "division_entropy.parquet", "Rating diagnostics", "diagnostic", required=False),
    TableSpec("division_resume", "division_resume.parquet", "Rating diagnostics", "diagnostic", required=False),
    TableSpec("excluded_bouts", "_excluded_bouts.csv", "Greco", "audit"),
    TableSpec("ped_confirmed_bouts", "ped_confirmed_bouts.csv", "Greco", "audit"),
    TableSpec("missed_weight_bouts", "missed_weight_bouts.csv", "Integrity flags", "audit", required=False),
    TableSpec("datalab_bouts_all", "datalab_bouts_all.parquet", "UFC-DataLab", "external", required=False),
    TableSpec(
        "datalab_merged_stats_scorecards",
        "datalab_merged_stats_scorecards.parquet",
        "UFC-DataLab",
        "external",
        required=False,
    ),
    TableSpec("datalab_fighter_details", "datalab_fighter_details.parquet", "UFC-DataLab", "external", required=False),
    TableSpec("datalab_scorecards", "datalab_scorecards.parquet", "UFC-DataLab", "external", required=False),
    TableSpec("fightmatrix_rankings", "fightmatrix_rankings.parquet", "FightMatrix", "external", required=False),
    TableSpec("fightmatrix_all_time", "fightmatrix_all_time.parquet", "FightMatrix", "external", required=False),
    TableSpec("fightmatrix_profiles", "fightmatrix_profiles.parquet", "FightMatrix", "external", required=False),
    TableSpec("fightmatrix_bouts", "fightmatrix_bouts.parquet", "FightMatrix", "external", required=False),
    TableSpec("fightmatrix_profile_queue", "fightmatrix_profile_queue.parquet", "FightMatrix expansion", "crawl_state", required=False),
    TableSpec("fightmatrix_profiles_expanded", "fightmatrix_profiles_expanded.parquet", "FightMatrix expansion", "external", required=False),
    TableSpec("fightmatrix_bouts_expanded", "fightmatrix_bouts_expanded.parquet", "FightMatrix expansion", "external", required=False),
    TableSpec("fightmatrix_profile_provenance", "fightmatrix_profile_provenance.parquet", "FightMatrix expansion", "provenance", required=False),
    TableSpec("fightmatrix_identity_map", "fightmatrix_identity_map.parquet", "FightMatrix expansion", "identity", required=False),
    TableSpec("fightmatrix_identity_exceptions", "fightmatrix_identity_exceptions.parquet", "FightMatrix expansion", "audit", required=False),
    TableSpec("fightmatrix_organization_map", "fightmatrix_organization_map.parquet", "FightMatrix expansion", "reference", required=False),
    TableSpec("fightmatrix_bout_reconciliation", "fightmatrix_bout_reconciliation.parquet", "FightMatrix expansion", "audit", required=False),
    TableSpec("fightmatrix_graph_metrics", "fightmatrix_graph_metrics.parquet", "FightMatrix expansion", "diagnostic", required=False),
    TableSpec("fightmatrix_fighter_completeness", "fightmatrix_fighter_completeness.parquet", "FightMatrix expansion", "diagnostic", required=False),
    TableSpec("fightmatrix_seed_opponent_coverage", "fightmatrix_seed_opponent_coverage.parquet", "FightMatrix expansion", "diagnostic", required=False),
    TableSpec("fightmatrix_component_sizes", "fightmatrix_component_sizes.parquet", "FightMatrix expansion", "diagnostic", required=False),
    TableSpec("fightmatrix_degree_distribution", "fightmatrix_degree_distribution.parquet", "FightMatrix expansion", "diagnostic", required=False),
    TableSpec("fightmatrix_exclusions", "fightmatrix_exclusions.parquet", "FightMatrix expansion", "audit", required=False),
    TableSpec("fightmatrix_model_eligible_bouts", "fightmatrix_model_eligible_bouts.parquet", "FightMatrix expansion", "canonical_extension", required=False),
    TableSpec("fightmatrix_policy_comparison", "fightmatrix_policy_comparison.parquet", "FightMatrix expansion", "diagnostic", required=False),
    TableSpec("fightmatrix_headline_eligibility", "fightmatrix_headline_eligibility.parquet", "FightMatrix expansion", "diagnostic", required=False),
    TableSpec("fightmatrix_notebook_data", "fightmatrix_notebook_data.parquet", "FightMatrix expansion", "diagnostic", required=False),
    TableSpec("fightmatrix_scope_validation", "fightmatrix_scope_validation.parquet", "Rating engine", "diagnostic", required=False),
    TableSpec("fightmatrix_historical_panel", "fightmatrix_historical_panel.parquet", "Rating engine", "diagnostic", required=False),
    TableSpec("fightmatrix_rank_movements", "fightmatrix_rank_movements.parquet", "Rating engine", "diagnostic", required=False),
    TableSpec("fightmatrix_anomaly_traces", "fightmatrix_anomaly_traces.parquet", "Rating engine", "diagnostic", required=False),
    TableSpec("fightmatrix_anomaly_summary", "fightmatrix_anomaly_summary.parquet", "Rating engine", "diagnostic", required=False),
    TableSpec(
        "fightmatrix_crossorg_fights",
        "fightmatrix_crossorg_fights.parquet",
        "FightMatrix",
        "canonical_extension",
        required=False,
    ),
    TableSpec(
        "fightmatrix_scope_comparison",
        "fightmatrix_scope_comparison.parquet",
        "Rating engine",
        "diagnostic",
        required=False,
    ),
    TableSpec(
        "odds_lines",
        "odds_lines.parquet",
        "Odds ingestion",
        "external",
        required=False,
    ),
]


INDEX_CANDIDATES = [
    "fighter",
    "fighter_a",
    "fighter_b",
    "winner",
    "loser",
    "red_fighter_name",
    "blue_fighter_name",
    "fighter_name",
    "event_date",
    "fight_url",
    "event_name",
    "division",
    "rank",
    "profile_id",
    "fightmatrix_profile_id",
    "opponent_profile_id",
    "discovery_depth",
    "parse_status",
    "canonical_organization",
    "market_favorite",
    "market_underdog",
    "odds_source",
]


COMPOSITE_INDEXES = {
    "canonical_fights": [("event_date", "event_name"), ("fighter_a", "fighter_b"), ("fight_url",)],
    "crossorg_fights": [("event_date", "event_name"), ("fighter_a", "fighter_b"), ("fight_url",), ("org",)],
    "canonical_rounds": [("fight_url", "fighter"), ("fighter", "event_date")],
    "ratings_history": [("fighter", "event_date")],
    "ratings_history_method_integrity": [("fighter", "event_date")],
    "ratings_history_method_performance": [("fighter", "event_date")],
    "ratings_history_method_integrity_performance": [("fighter", "event_date")],
    "ratings_history_whr": [("fighter", "event_date")],
    "integrity_appearances": [("fight_url", "fighter")],
    "performance_appearances": [("fight_url", "fighter"), ("event_date", "fighter")],
    "ratings_current": [("fighter",), ("last_event_date",)],
    "fight_dominance": [("fight_url",)],
    "fighter_dominance": [("fighter",)],
    "calibration_residuals": [("segment_type", "segment_value"), ("prob_bin",)],
    "sleeve_attribution": [("fighter", "event_date"), ("fight_url", "fighter")],
    "division_entropy": [("division", "year")],
    "division_resume": [("division", "division_score_whr"), ("fighter", "division")],
    "excluded_bouts": [("fight_url",), ("event_date", "event_name")],
    "ped_confirmed_bouts": [("fight_url",), ("ped_flagged_fighter",)],
    "missed_weight_bouts": [("fight_url",), ("missed_weight_fighter",)],
    "datalab_bouts_all": [("event_date", "event_name"), ("red_fighter_name", "blue_fighter_name")],
    "datalab_merged_stats_scorecards": [
        ("event_date", "event_name"),
        ("red_fighter_name", "blue_fighter_name"),
    ],
    "datalab_fighter_details": [("fighter_name",)],
    "datalab_scorecards": [("event_date",), ("red_fighter_name", "blue_fighter_name")],
    "fightmatrix_rankings": [("division", "rank"), ("fighter",)],
    "fightmatrix_all_time": [("rank",), ("fighter",)],
    "fightmatrix_profiles": [("profile_id",), ("fighter",), ("pro_debut_date",)],
    "fightmatrix_bouts": [
        ("fight_key",),
        ("event_date", "event_name"),
        ("fighter", "opponent"),
        ("org",),
    ],
    "fightmatrix_profile_queue": [("profile_id",), ("discovery_depth", "priority_score"), ("fetch_status", "parse_status")],
    "fightmatrix_profiles_expanded": [("profile_id",), ("fighter",), ("completeness_classification",)],
    "fightmatrix_bouts_expanded": [("fight_key",), ("fighter_profile_id", "opponent_profile_id"), ("event_date", "event_name")],
    "fightmatrix_profile_provenance": [("profile_id",), ("content_sha256",)],
    "fightmatrix_identity_map": [("fightmatrix_profile_id",), ("normalized_name",), ("ufc_fighter",)],
    "fightmatrix_identity_exceptions": [("exception_type",), ("normalized_name",)],
    "fightmatrix_organization_map": [("canonical_organization",), ("raw_organization",)],
    "fightmatrix_bout_reconciliation": [("deduplication_key",), ("deduplication_classification",)],
    "fightmatrix_fighter_completeness": [("profile_id",), ("fighter",), ("component_size",)],
    "fightmatrix_seed_opponent_coverage": [("profile_id",), ("fighter",)],
    "fightmatrix_degree_distribution": [("degree",)],
    "fightmatrix_exclusions": [("exclusion_stage",), ("deduplication_key",)],
    "fightmatrix_model_eligible_bouts": [("fight_url",), ("event_date", "event_name"), ("fighter_a", "fighter_b")],
    "fightmatrix_policy_comparison": [("policy",)],
    "fightmatrix_headline_eligibility": [("profile_id",), ("fighter",), ("headline_suppression_reason",)],
    "fightmatrix_scope_validation": [("scope",)],
    "fightmatrix_historical_panel": [("scope", "fighter"), ("model_rank",)],
    "fightmatrix_rank_movements": [("scope", "fighter"), ("rank_delta_vs_ufc",), ("absolute_reference_rank_error",)],
    "fightmatrix_anomaly_traces": [("fighter", "event_date"), ("opponent",)],
    "fightmatrix_anomaly_summary": [("scope", "fighter"), ("diagnostic_cause",)],
    "fightmatrix_crossorg_fights": [
        ("event_date", "event_name"),
        ("fighter_a", "fighter_b"),
        ("fight_url",),
        ("org",),
    ],
    "fightmatrix_scope_comparison": [
        ("fighter",),
        ("ufc_only_rank",),
        ("fightmatrix_public_rank",),
        ("fightmatrix_reference_rank",),
    ],
    "odds_lines": [
        ("fight_url",),
        ("event_date", "event_name"),
        ("fighter_a", "fighter_b"),
        ("market_favorite",),
        ("market_underdog",),
    ],
}


_SNAPSHOT_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def latest_snapshot_dir(project_root: Path = PROJECT_ROOT) -> Path:
    snapshots_root = project_root / "data" / "snapshots"
    if not snapshots_root.exists():
        raise FileNotFoundError(f"snapshot root not found: {snapshots_root}")
    candidates = [
        path for path in snapshots_root.iterdir()
        if path.is_dir()
        and _SNAPSHOT_DATE_RE.match(path.name)
        and (path / "canonical_fights.parquet").exists()
    ]
    if not candidates:
        raise FileNotFoundError(f"no usable snapshots found under {snapshots_root}")
    return sorted(candidates, key=lambda p: p.name)[-1]


def _read_source(path: Path, table_name: str | None = None) -> pd.DataFrame:
    if path.suffix.lower() == ".parquet":
        df = pd.read_parquet(path)
    if path.suffix.lower() == ".csv":
        df = pd.read_csv(path)
    elif path.suffix.lower() not in {".parquet", ".csv"}:
        raise ValueError(f"unsupported source file type: {path}")
    if table_name == "odds_lines":
        return compute_implied_probs(df)
    return df


def _sqlite_ready(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[col]):
            out[col] = out[col].dt.strftime("%Y-%m-%d")
    return out.where(pd.notna(out), None)


def _iso_file_mtime(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(timespec="seconds")


def _date_range(df: pd.DataFrame) -> tuple[str | None, str | None]:
    return date_range(df)


def _safe_identifier(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]+", "_", value).strip("_").lower()


def _write_df(con: sqlite3.Connection, table_name: str, df: pd.DataFrame) -> None:
    _sqlite_ready(df).to_sql(table_name, con, if_exists="replace", index=False)


def _table_columns(con: sqlite3.Connection, table_name: str) -> set[str]:
    return {row[1] for row in con.execute(f'PRAGMA table_info("{table_name}")').fetchall()}


def _create_indexes(con: sqlite3.Connection, table_name: str) -> int:
    columns = _table_columns(con, table_name)
    created = 0

    for column in INDEX_CANDIDATES:
        if column not in columns:
            continue
        index_name = _safe_identifier(f"idx_{table_name}_{column}")
        con.execute(f'CREATE INDEX IF NOT EXISTS "{index_name}" ON "{table_name}" ("{column}")')
        created += 1

    for composite in COMPOSITE_INDEXES.get(table_name, []):
        if not set(composite).issubset(columns):
            continue
        suffix = "_".join(composite)
        index_name = _safe_identifier(f"idx_{table_name}_{suffix}")
        col_sql = ", ".join(f'"{col}"' for col in composite)
        con.execute(f'CREATE INDEX IF NOT EXISTS "{index_name}" ON "{table_name}" ({col_sql})')
        created += 1

    return created


def _sqlite_tables(con: sqlite3.Connection) -> list[str]:
    rows = con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    return [row[0] for row in rows]


def _sqlite_index_count(con: sqlite3.Connection) -> int:
    return int(con.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'"
    ).fetchone()[0])


def _row_counts(con: sqlite3.Connection, table_names: Iterable[str]) -> pd.DataFrame:
    rows = []
    for table_name in table_names:
        count = con.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()[0]
        rows.append({"table_name": table_name, "row_count": int(count)})
    return pd.DataFrame(rows).sort_values("table_name").reset_index(drop=True)


def _source_gaps(missing_optional: list[TableSpec]) -> pd.DataFrame:
    missing_table_names = {spec.table_name for spec in missing_optional}
    if "crossorg_fights" in missing_table_names:
        crossorg_row = {
            "gap_key": "cross_org_bouts_not_integrated",
            "severity": "known_gap",
            "status": "pending",
            "notes": (
                "No crossorg_fights.parquet in this snapshot; PRIDE, Strikeforce, "
                "WEC, and other non-UFC bouts are not merged into the headline stream."
            ),
        }
    else:
        crossorg_row = {
            "gap_key": "cross_org_bouts_integrated",
            "severity": "info",
            "status": "loaded",
            "notes": (
                "crossorg_fights.parquet is present; non-UFC bouts are merged into "
                "the rating streams with per-fight caliber weights."
            ),
        }
    if "fightmatrix_bouts" in missing_table_names:
        fightmatrix_history_row = {
            "gap_key": "fightmatrix_per_bout_history_not_loaded",
            "severity": "known_gap",
            "status": "pending",
            "notes": "FightMatrix public per-bout profile histories are not staged in this snapshot.",
        }
    else:
        fightmatrix_history_row = {
            "gap_key": "fightmatrix_ranked_cohort_history_loaded",
            "severity": "info",
            "status": "loaded",
            "notes": (
                "Public profile histories for the current-ranked and all-time seed cohorts are staged; "
                "opponent links were not recursively crawled."
            ),
        }
    rows = [
        crossorg_row,
        fightmatrix_history_row,
        {
            "gap_key": "official_historical_ufc_rankings_not_loaded",
            "severity": "known_gap",
            "status": "pending",
            "notes": (
                "The performance sleeve uses pre-fight model top-15 and inferred "
                "title lineage as a no-leak ranking/champ/P4P proxy. Official "
                "date-stamped UFC ranking snapshots are not yet loaded."
            ),
        },
        {
            "gap_key": "datalab_not_canonical_authority",
            "severity": "design_note",
            "status": "staged",
            "notes": "UFC-DataLab tables are retained as external comparison/scorecard sources.",
        },
    ]
    # Promote the absence of `odds_lines` to a named gap (more useful to a
    # human reader than a generic `missing_optional_odds_lines` row).
    if "odds_lines" in missing_table_names:
        rows.append({
            "gap_key": "odds_source_not_ingested",
            "severity": "known_gap",
            "status": "pending",
            "notes": (
                "No odds_lines.parquet in this snapshot — performance sleeve's "
                "odds sub-factor is inactive. Candidate ingestion: mdabbert "
                "Ultimate UFC Dataset (Apache-2.0), BestFightOdds.com (primary), "
                "OddsPortal.com (cross-check), or the jasonchanhku CSV (starter). "
                "See data/SOURCE_MATRIX.md."
            ),
        })
    else:
        rows.append({
            "gap_key": "odds_source_ingested",
            "severity": "info",
            "status": "loaded",
            "notes": (
                "odds_lines.parquet is present; performance sleeve's odds "
                "sub-factor active."
            ),
        })
    for spec in missing_optional:
        if spec.table_name == "odds_lines":
            # Already represented by the named gap above.
            continue
        rows.append({
            "gap_key": f"missing_optional_{spec.table_name}",
            "severity": "missing_optional_source",
            "status": "missing",
            "notes": f"{spec.file_name} was not present in the source snapshot.",
        })
    return pd.DataFrame(rows)


def build_database(
    snapshot_dir: Path,
    db_path: Path = DEFAULT_DB_PATH,
    replace: bool = True,
) -> dict[str, int]:
    """Build a SQLite database from `snapshot_dir` and return summary counts."""
    snapshot_dir = Path(snapshot_dir).resolve()
    db_path = Path(db_path).resolve()
    if not snapshot_dir.exists():
        raise FileNotFoundError(f"snapshot not found: {snapshot_dir}")
    if db_path.exists() and not replace:
        raise FileExistsError(f"database already exists: {db_path}")

    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    manifest_rows = []
    missing_optional: list[TableSpec] = []
    loaded_tables: list[str] = []

    with sqlite3.connect(db_path) as con:
        con.execute("PRAGMA journal_mode=DELETE")
        con.execute("PRAGMA foreign_keys=OFF")

        for spec in TABLE_SPECS:
            source_path = snapshot_dir / spec.file_name
            if not source_path.exists():
                if spec.required:
                    raise FileNotFoundError(f"required snapshot source missing: {source_path}")
                missing_optional.append(spec)
                continue

            df = _read_source(source_path, spec.table_name)
            _write_df(con, spec.table_name, df)
            loaded_tables.append(spec.table_name)
            min_date, max_date = _date_range(df)
            manifest_rows.append({
                "table_name": spec.table_name,
                "source_name": spec.source_name,
                "source_kind": spec.source_kind,
                "source_path": str(source_path.relative_to(PROJECT_ROOT)),
                "row_count": int(len(df)),
                "column_count": int(len(df.columns)),
                "columns_json": json.dumps(list(df.columns)),
                "min_date": min_date,
                "max_date": max_date,
                "file_modified_utc": _iso_file_mtime(source_path),
            })

        _write_df(con, "source_manifest", pd.DataFrame(manifest_rows))
        _write_df(con, "source_gaps", _source_gaps(missing_optional))

        built_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        snapshot_manifest = pd.DataFrame([
            {"manifest_key": "snapshot_date", "manifest_value": snapshot_dir.name},
            {"manifest_key": "snapshot_dir", "manifest_value": str(snapshot_dir.relative_to(PROJECT_ROOT))},
            {"manifest_key": "database_path", "manifest_value": str(db_path.relative_to(PROJECT_ROOT))},
            {"manifest_key": "built_at_utc", "manifest_value": built_at},
            {"manifest_key": "loaded_source_tables", "manifest_value": str(len(loaded_tables))},
        ])
        _write_df(con, "snapshot_manifest", snapshot_manifest)

        attempted_index_count = 0
        for table_name in loaded_tables + ["source_manifest", "source_gaps", "snapshot_manifest"]:
            attempted_index_count += _create_indexes(con, table_name)

        tables_before_counts = _sqlite_tables(con)
        counts = _row_counts(con, tables_before_counts)
        counts = pd.concat(
            [
                counts,
                pd.DataFrame([{
                    "table_name": "table_row_counts",
                    "row_count": int(len(counts) + 1),
                }]),
            ],
            ignore_index=True,
        )
        _write_df(con, "table_row_counts", counts)
        attempted_index_count += _create_indexes(con, "table_row_counts")

        sqlite_table_count = len(_sqlite_tables(con))
        sqlite_index_count = _sqlite_index_count(con)
        con.execute(
            "INSERT INTO snapshot_manifest (manifest_key, manifest_value) VALUES (?, ?)",
            ("sqlite_table_count", str(sqlite_table_count)),
        )
        con.execute(
            "INSERT INTO snapshot_manifest (manifest_key, manifest_value) VALUES (?, ?)",
            ("sqlite_index_count", str(sqlite_index_count)),
        )
        con.execute(
            "INSERT INTO snapshot_manifest (manifest_key, manifest_value) VALUES (?, ?)",
            ("sqlite_index_create_attempts", str(attempted_index_count)),
        )
        con.commit()

        existing_tables = set(_sqlite_tables(con))
        def table_count(name: str) -> int:
            if name in existing_tables:
                return con.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
            return 0

        key_counts = {
            "canonical_fights": table_count("canonical_fights"),
            "ratings_current": table_count("ratings_current"),
            "datalab_bouts_all": table_count("datalab_bouts_all"),
            "fightmatrix_rankings": table_count("fightmatrix_rankings"),
            "fightmatrix_all_time": table_count("fightmatrix_all_time"),
            "sqlite_table_count": sqlite_table_count,
            "sqlite_index_count": sqlite_index_count,
        }
    return {k: int(v) for k, v in key_counts.items()}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build data/ufc_rank_engine.sqlite from a snapshot bundle.")
    parser.add_argument("--snapshot-dir", default=None, help="Snapshot directory. Defaults to newest data/snapshots/<date>.")
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH), help="Output SQLite path.")
    parser.add_argument("--no-replace", action="store_true", help="Fail if the SQLite database already exists.")
    args = parser.parse_args()

    snapshot_dir = Path(args.snapshot_dir).resolve() if args.snapshot_dir else latest_snapshot_dir()
    summary = build_database(snapshot_dir=snapshot_dir, db_path=Path(args.db_path), replace=not args.no_replace)

    print(f"[database] snapshot = {snapshot_dir}")
    print(f"[database] sqlite   = {Path(args.db_path).resolve()}")
    for key, value in summary.items():
        print(f"[database] {key}: {value:,}")


if __name__ == "__main__":
    main()
