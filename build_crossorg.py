"""Stage a snapshot that includes cross-org (PRIDE/StrikeForce/WEC/...) bouts.

Given a base UFC snapshot and a raw Sherdog scrape, this:
  1. shapes the scraped bouts like ``canonical_fights`` (method/round/time +
     UFC-division weight class + title flag),
  2. computes a bridge-calibrated per-fight weight from the UFC-caliber of the
     two fighters, with one-hop opponent inference for non-UFC greats,
  3. stages a new snapshot directory cloned from the base plus
     ``crossorg_fights.parquet`` and ``org_weights.json``.

Then ``ratings/rate_snapshot.run()`` over the new snapshot merges those bouts
into every rating stream. Re-running is cheap because the HTML is cached.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from project_helpers import normalize_name_key
from loaders.sherdog_loader import (
    DEFAULT_CACHE_DIR,
    build_crossorg_bouts,
    compute_fight_weights,
    compute_org_weights,
    to_canonical_fights,
)

# Files cloned from the base snapshot so rate_snapshot can run unchanged.
_CLONE_FILES = (
    "canonical_fights.parquet", "canonical_rounds.parquet",
    "canonical_fighters.parquet", "canonical_events.parquet",
    "canonical_fights.schema.json", "canonical_rounds.schema.json",
    "canonical_fighters.schema.json", "canonical_events.schema.json",
    "_excluded_bouts.csv", "odds_lines.parquet",
    "fightmatrix_rankings.parquet", "fightmatrix_summary.json",
    "datalab_bouts_all.parquet", "datalab_merged_stats_scorecards.parquet",
    "datalab_fighter_details.parquet", "datalab_scorecards.parquet",
    "datalab_summary.json",
    "ped_confirmed_bouts.csv", "missed_weight_bouts.csv",
)


def _name_maps(ratings_current: pd.DataFrame) -> tuple[dict[str, str], dict[str, str]]:
    db_name_map, division_map = {}, {}
    div_col = "recent_division" if "recent_division" in ratings_current.columns else "career_division"
    for _, row in ratings_current.iterrows():
        name = row["fighter"]
        if not isinstance(name, str):
            continue
        key = normalize_name_key(name, compact=True)
        db_name_map[key] = name
        div = row.get(div_col) or row.get("career_division")
        if isinstance(div, str) and div:
            division_map[key] = div
    return db_name_map, division_map


def build(
    base_snapshot: Path,
    new_snapshot: Path,
    *,
    raw_bouts_path: Path | None = None,
    scrape: bool = False,
    grappler_csv: Path | None = None,
) -> dict:
    base_snapshot, new_snapshot = Path(base_snapshot), Path(new_snapshot)
    ratings_current = pd.read_parquet(base_snapshot / "ratings_current.parquet")
    db_name_map, division_map = _name_maps(ratings_current)

    # 1. Raw scraped bouts (from cache/parquet, or scrape fresh).
    if scrape:
        names = _crossorg_fighter_names(grappler_csv, db_name_map)
        raw = build_crossorg_bouts(names, cache_dir=DEFAULT_CACHE_DIR, progress=True)
    else:
        raw = pd.read_parquet(raw_bouts_path or (DEFAULT_CACHE_DIR / "crossorg_bouts_raw.parquet"))

    # 2. Canonical-shaped cross-org bouts + PER-FIGHT bridge-calibrated weight.
    # The weight reflects the UFC caliber of the two fighters in the bout (not a
    # flat org discount), so an elite-vs-elite cross-org bout counts nearly
    # fully while a bout with an unproven org fighter counts less.
    crossorg = to_canonical_fights(raw, db_name_map, division_map)
    crossorg["org_weight"] = compute_fight_weights(crossorg, ratings_current).values
    org_weights = compute_org_weights(crossorg, ratings_current)  # org-level summary only

    # 3. Stage the new snapshot.
    new_snapshot.mkdir(parents=True, exist_ok=True)
    for fname in _CLONE_FILES:
        src = base_snapshot / fname
        if src.exists():
            shutil.copy2(src, new_snapshot / fname)
    crossorg.to_parquet(new_snapshot / "crossorg_fights.parquet", index=False)
    (new_snapshot / "org_weights.json").write_text(json.dumps(org_weights, indent=2))

    org_mean_weight = crossorg.groupby("org")["org_weight"].mean().round(3).to_dict()
    return {
        "raw_rows": int(len(raw)),
        "crossorg_bouts": int(len(crossorg)),
        "org_summary_percentile": org_weights,
        "mean_fight_weight_by_org": org_mean_weight,
        "by_org": crossorg["org"].value_counts().to_dict(),
        "new_snapshot": str(new_snapshot),
    }


def _crossorg_fighter_names(grappler_csv: Path | None, db_name_map: dict[str, str]) -> list[str]:
    if grappler_csv is None:
        raise ValueError("scrape=True requires grappler_csv")
    g = pd.read_csv(grappler_csv)
    ev = g["event"].astype(str).str.lower()
    mask = (ev.str.startswith("pride") | ev.str.contains("strikeforce")
            | ev.str.startswith("wec") | ev.str.contains("world extreme cagefighting")
            | ev.str.contains("pride fc"))
    out = []
    for nm in g[mask]["fighter_name"].dropna().unique():
        key = normalize_name_key(nm, compact=True)
        if key in db_name_map:
            out.append(db_name_map[key])
    return sorted(set(out))


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Stage a cross-org snapshot.")
    ap.add_argument("--base", required=True, help="base UFC snapshot dir")
    ap.add_argument("--out", required=True, help="new snapshot dir to stage")
    ap.add_argument("--raw", default=None, help="raw scraped bouts parquet")
    args = ap.parse_args()
    info = build(Path(args.base), Path(args.out), raw_bouts_path=Path(args.raw) if args.raw else None)
    print(json.dumps(info, indent=2, default=str))
