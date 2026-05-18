"""Ingest the mdabbert "Ultimate UFC Dataset" historical odds.

Pulls per-fight American moneyline odds for ~6,900 UFC bouts spanning
~2010-2026 from ``ufc-master.csv`` into the snapshot's
``odds_lines.parquet``. Distributed under Apache-2.0 by the upstream
project (``ultimate_ufc_dataset``), so the cached CSV may be redistributed
with attribution — see ``data/SOURCE_MATRIX.md``.

The CSV carries a ``date`` column, so this loader's pair-and-date join is
more reliable than the legacy ``jasonchanhku`` ingest (pair-only); rematches
disambiguate naturally.

Output schema matches ``loaders/odds_loader.py``'s raw schema:
    fight_url, event_date, event_name,
    fighter_a, fighter_b,
    odds_source, odds_fighter_a, odds_fighter_b,
    american_odds_a, american_odds_b,
    decimal_odds_a, decimal_odds_b
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from loaders.odds_loader import (
    RAW_ODDS_COLUMNS,
    american_to_decimal,
    compute_implied_probs,
)
from project_helpers import normalize_name_key


ODDS_SOURCE_LABEL = "mdabbert-ultimate-v1"

_REQUIRED_COLUMNS = (
    "R_fighter",
    "B_fighter",
    "R_odds",
    "B_odds",
    "date",
)


def _pair_key(a: object, b: object) -> frozenset[str]:
    return frozenset({normalize_name_key(a), normalize_name_key(b)})


def load_master_csv(path: Path) -> pd.DataFrame:
    """Read the mdabbert ``ufc-master.csv`` into a typed DataFrame."""
    df = pd.read_csv(path, usecols=list(_REQUIRED_COLUMNS))
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date", "R_fighter", "B_fighter"])
    df["R_odds"] = pd.to_numeric(df["R_odds"], errors="coerce")
    df["B_odds"] = pd.to_numeric(df["B_odds"], errors="coerce")
    df = df[df["R_odds"].notna() & df["B_odds"].notna()].copy()
    df["pair_key"] = df.apply(lambda r: _pair_key(r["R_fighter"], r["B_fighter"]), axis=1)
    return df


def build_odds_lines(canonical_fights: pd.DataFrame, mdabbert: pd.DataFrame) -> pd.DataFrame:
    """Join mdabbert rows to canonical fights and return the raw odds frame."""
    cf = canonical_fights[[
        "fight_url", "event_date", "event_name",
        "fighter_a", "fighter_b",
    ]].copy()
    cf["event_date"] = pd.to_datetime(cf["event_date"], errors="coerce")
    cf["pair_key"] = cf.apply(lambda r: _pair_key(r["fighter_a"], r["fighter_b"]), axis=1)

    md = mdabbert.copy()
    md.rename(columns={"date": "odds_date"}, inplace=True)
    joined = cf.merge(
        md[["pair_key", "odds_date", "R_fighter", "B_fighter", "R_odds", "B_odds"]],
        on="pair_key",
        how="inner",
    )
    joined["date_diff"] = (joined["event_date"] - joined["odds_date"]).abs().dt.days
    joined = joined[joined["date_diff"] <= 2].copy()
    # If multiple mdabbert rows match (rematches with same pair), pick the
    # closest by date.
    joined = (
        joined.sort_values(["fight_url", "date_diff"])
        .drop_duplicates("fight_url", keep="first")
    )

    out = pd.DataFrame(index=joined.index)
    out["fight_url"] = joined["fight_url"]
    out["event_date"] = joined["event_date"]
    out["event_name"] = joined["event_name"]
    out["fighter_a"] = joined["fighter_a"]
    out["fighter_b"] = joined["fighter_b"]
    out["odds_source"] = ODDS_SOURCE_LABEL

    # Decide which mdabbert column (R or B) maps to canonical fighter_a vs
    # fighter_b by normalized-name match.
    r_key = joined["R_fighter"].map(normalize_name_key)
    b_key = joined["B_fighter"].map(normalize_name_key)
    a_key = joined["fighter_a"].map(normalize_name_key)
    a_is_r = r_key == a_key
    a_is_b = b_key == a_key
    # If neither matches by exact normalized key (mismatch), drop the row —
    # we cannot place which odds belong to which fighter.
    valid = a_is_r | a_is_b
    out = out.loc[valid].copy()
    a_is_r = a_is_r.loc[valid]

    am_a = joined.loc[valid, "R_odds"].where(a_is_r, joined.loc[valid, "B_odds"])
    am_b = joined.loc[valid, "B_odds"].where(a_is_r, joined.loc[valid, "R_odds"])
    out["odds_fighter_a"] = out["fighter_a"]
    out["odds_fighter_b"] = out["fighter_b"]
    out["american_odds_a"] = pd.to_numeric(am_a, errors="coerce")
    out["american_odds_b"] = pd.to_numeric(am_b, errors="coerce")
    out["decimal_odds_a"] = out["american_odds_a"].map(american_to_decimal)
    out["decimal_odds_b"] = out["american_odds_b"].map(american_to_decimal)
    return out[list(RAW_ODDS_COLUMNS)].reset_index(drop=True)


def merge_with_existing(new_rows: pd.DataFrame, existing: pd.DataFrame) -> pd.DataFrame:
    """Union with the existing ``odds_lines.parquet``, mdabbert preferred."""
    if existing is None or existing.empty:
        return new_rows.copy()
    keep_existing = existing[~existing["fight_url"].isin(new_rows["fight_url"])]
    cols = list(RAW_ODDS_COLUMNS)
    out = pd.concat(
        [new_rows[cols], keep_existing[cols]],
        ignore_index=True,
        sort=False,
    )
    return out


def run(
    snapshot_dir: Path,
    csv_path: Path,
    *,
    keep_existing: bool = True,
) -> dict:
    snapshot_dir = Path(snapshot_dir).resolve()
    fights = pd.read_parquet(snapshot_dir / "canonical_fights.parquet")
    md = load_master_csv(Path(csv_path))
    new_rows = build_odds_lines(fights, md)

    out_path = snapshot_dir / "odds_lines.parquet"
    if keep_existing and out_path.exists():
        existing_raw = pd.read_parquet(out_path)
        # Only carry the raw columns; downstream compute_implied_probs re-derives.
        existing = existing_raw[[c for c in RAW_ODDS_COLUMNS if c in existing_raw.columns]].copy()
        merged = merge_with_existing(new_rows, existing)
    else:
        merged = new_rows

    enriched = compute_implied_probs(merged)
    enriched.to_parquet(out_path, index=False)

    by_source = (
        enriched["odds_source"].value_counts().to_dict()
        if "odds_source" in enriched.columns
        else {}
    )
    return {
        "snapshot_dir": str(snapshot_dir),
        "mdabbert_rows_loaded": int(len(md)),
        "mdabbert_rows_joined": int(len(new_rows)),
        "odds_lines_rows": int(len(enriched)),
        "rows_by_source": {str(k): int(v) for k, v in by_source.items()},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot-dir", required=True)
    parser.add_argument(
        "--csv",
        required=True,
        help="Path to the mdabbert ufc-master.csv (Apache-2.0 source).",
    )
    parser.add_argument(
        "--replace-existing",
        action="store_true",
        help="Overwrite the existing odds_lines.parquet rather than union.",
    )
    args = parser.parse_args()
    result = run(
        Path(args.snapshot_dir),
        Path(args.csv),
        keep_existing=not args.replace_existing,
    )
    print(result)


if __name__ == "__main__":
    main()
