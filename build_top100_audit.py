"""Audit the published top 100 and compare its career-bar policy."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from ratings import prequential as PQ
from ratings.age import load_birth_dates
from ratings.connectivity import connectivity
from ratings.scope import DEFAULT_PUBLISHED_SCOPE
from ratings.symon_score import DEFAULT_CAREER_REFERENCE, career_skill_mass


def _ranked(score: pd.DataFrame, current: pd.DataFrame) -> pd.DataFrame:
    out = score.merge(current[["fighter", "rating_periods"]], on="fighter", how="left")
    out = out[(out["rating_periods"] >= 13) & (out["score"] > 0)].copy()
    out = out.sort_values(["score", "fighter"], ascending=[False, True]).reset_index(drop=True)
    out["rank"] = np.arange(1, len(out) + 1)
    return out


def build(snapshot: Path, *, scope: str, out_dir: Path) -> dict[str, object]:
    history = pd.read_parquet(snapshot / "ratings_history_whr.parquet")
    current = pd.read_parquet(snapshot / "ratings_current.parquet")
    published = _ranked(career_skill_mass(history), current)
    fixed_count = _ranked(career_skill_mass(history, reference="count:60"), current)
    comparison = published.merge(
        fixed_count[["fighter", "rank", "score"]],
        on="fighter",
        how="outer",
        suffixes=("_published", "_count60"),
    )
    comparison["rank_change_vs_count60"] = (
        comparison["rank_count60"] - comparison["rank_published"]
    )

    top = published.head(100).copy()
    appearances = (
        history.groupby("fighter", sort=False)
        .agg(first_appearance=("event_date", "min"), last_appearance=("event_date", "max"))
        .reset_index()
    )
    fights = PQ.load_fight_table(snapshot, scope=scope)
    canonical = pd.read_parquet(snapshot / "canonical_fights.parquet")
    sides = pd.concat(
        [
            fights[["fighter_a", "source"]].rename(columns={"fighter_a": "fighter"}),
            fights[["fighter_b", "source"]].rename(columns={"fighter_b": "fighter"}),
        ],
        ignore_index=True,
    )
    coverage = (
        sides.assign(is_ufc=sides["source"].eq("ufc"))
        .groupby("fighter", sort=False)
        .agg(total_bouts=("source", "size"), ufc_bouts=("is_ufc", "sum"))
        .reset_index()
    )
    top = top.merge(appearances, on="fighter", how="left").merge(coverage, on="fighter", how="left")
    core = set(canonical["fighter_a"]) | set(canonical["fighter_b"])
    core_counts = pd.concat([canonical["fighter_a"], canonical["fighter_b"]]).value_counts().to_dict()
    conn = connectivity(
        fights.rename(columns={"fighter_a": "fighter_a_id", "fighter_b": "fighter_b_id"}),
        core,
        core_bout_counts=core_counts,
        fighters=top["fighter"].tolist(),
    )[["fighter_id", "disjoint_paths", "rankable"]]
    top = top.merge(conn, left_on="fighter", right_on="fighter_id", how="left").drop(
        columns="fighter_id"
    )
    birth_dates = load_birth_dates(snapshot)
    top["birth_date_known"] = top["fighter"].isin(birth_dates)
    top["active_2024_plus"] = top["last_appearance"].dt.year.ge(2024)
    top["external_only"] = top["ufc_bouts"].fillna(0).eq(0)

    old_top = set(fixed_count.head(100)["fighter"])
    new_top = set(top["fighter"])
    summary: dict[str, object] = {
        "snapshot": snapshot.name,
        "scope": scope,
        "published_reference": str(DEFAULT_CAREER_REFERENCE),
        "ranked_fighters": int(len(published)),
        "top100_birth_date_coverage": round(float(top["birth_date_known"].mean()), 4),
        "top100_active_2024_plus": int(top["active_2024_plus"].sum()),
        "top100_external_only": int(top["external_only"].sum()),
        "top100_connectivity_rankable": int(top["rankable"].fillna(False).sum()),
        "external_only_names": top.loc[top["external_only"], "fighter"].tolist(),
        "top100_debut_before_2000": int(top["first_appearance"].dt.year.lt(2000).sum()),
        "top100_debut_2015_plus": int(top["first_appearance"].dt.year.ge(2015).sum()),
        "entered_vs_count60": sorted(new_top - old_top),
        "left_vs_count60": sorted(old_top - new_top),
        "top10": top.head(10)[["rank", "fighter", "score"]].to_dict("records"),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    comparison.to_parquet(out_dir / "top100_bar_comparison.parquet", index=False)
    top.to_parquet(out_dir / "top100_audit.parquet", index=False)
    top.to_csv(out_dir / "top100_audit.csv", index=False)
    (out_dir / "top100_audit.json").write_text(
        json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8"
    )
    return summary


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("snapshot_dir", type=Path)
    ap.add_argument("--scope", default=DEFAULT_PUBLISHED_SCOPE)
    ap.add_argument("--out-dir", type=Path, default=Path("data/model_tuning/top100-audit"))
    args = ap.parse_args()
    print(json.dumps(build(args.snapshot_dir, scope=args.scope, out_dir=args.out_dir), indent=2))


if __name__ == "__main__":
    main()
