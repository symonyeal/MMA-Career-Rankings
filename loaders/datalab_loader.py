"""Load UFC-DataLab exports into project-local snapshot artifacts.

Source repo:
    https://github.com/komaksym/UFC-DataLab

The repo checkout is cached under `data/external/api_sources/UFC-DataLab`.
This loader reads the CSV exports that are already in that checkout and writes
parquet copies into the current snapshot folder for comparison/merge work.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATALAB_DIR = PROJECT_ROOT / "data" / "external" / "api_sources" / "UFC-DataLab"


DATASETS = {
    "datalab_bouts_all": {
        "path": Path("data/stats/stats_processed_all_bouts.csv"),
        "read_csv": {"sep": ";"},
    },
    "datalab_merged_stats_scorecards": {
        "path": Path("data/merged_stats_n_scorecards/merged_stats_n_scorecards.csv"),
        "read_csv": {},
    },
    "datalab_fighter_details": {
        "path": Path("data/external_data/raw_fighter_details.csv"),
        "read_csv": {},
    },
    "datalab_scorecards": {
        "path": Path("data/scorecards/OCR_parsed_scorecards/SCORECARDS.csv"),
        "read_csv": {"sep": ";"},
    },
}


def _clean_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [str(c).strip().lower().replace(" ", "_") for c in out.columns]
    return out


def _parse_dates(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "event_date" in out.columns:
        out["event_date"] = pd.to_datetime(out["event_date"], dayfirst=True, errors="coerce")
    return out


def load_datalab_dataset(datalab_dir: Path, dataset_key: str) -> pd.DataFrame:
    spec = DATASETS[dataset_key]
    path = datalab_dir / spec["path"]
    if not path.exists():
        raise FileNotFoundError(f"UFC-DataLab dataset not found: {path}")
    df = pd.read_csv(path, **spec["read_csv"])
    return _parse_dates(_clean_columns(df))


def build_snapshot(datalab_dir: Path, snapshot_dir: Path) -> dict[str, dict]:
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    summary: dict[str, dict] = {}

    for key in DATASETS:
        df = load_datalab_dataset(datalab_dir, key)
        out_path = snapshot_dir / f"{key}.parquet"
        df.to_parquet(out_path, index=False)
        summary[key] = {
            "rows": int(len(df)),
            "columns": list(df.columns),
            "output": str(out_path.relative_to(PROJECT_ROOT)),
        }
        if "event_date" in df.columns and df["event_date"].notna().any():
            summary[key]["min_event_date"] = str(df["event_date"].min().date())
            summary[key]["max_event_date"] = str(df["event_date"].max().date())

    summary_path = snapshot_dir / "datalab_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Load UFC-DataLab CSV exports into a snapshot.")
    parser.add_argument("--snapshot-dir", required=True, help="data/snapshots/<date>")
    parser.add_argument("--datalab-dir", default=str(DEFAULT_DATALAB_DIR), help="Path to UFC-DataLab checkout.")
    args = parser.parse_args()

    snapshot_dir = Path(args.snapshot_dir).resolve()
    datalab_dir = Path(args.datalab_dir).resolve()
    summary = build_snapshot(datalab_dir, snapshot_dir)

    print(f"[datalab] source = {datalab_dir}")
    for key, info in summary.items():
        date_span = ""
        if "min_event_date" in info:
            date_span = f" dates={info['min_event_date']}..{info['max_event_date']}"
        print(f"[datalab] {key}: rows={info['rows']:,} cols={len(info['columns'])}{date_span}")


if __name__ == "__main__":
    main()
