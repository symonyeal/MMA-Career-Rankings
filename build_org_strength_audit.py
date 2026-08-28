"""Evaluate candidate organization evidence weights against top-100 sanity.

This is deliberately an audit, not a production switch. Production stays on
unit weights unless a candidate improves prediction/top-100 diagnostics without
leaking future fighter quality into past bouts.

Usage:

    python build_org_strength_audit.py data/snapshots/2026-08-13
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from build_top100_audit import (
    WATCH_BELOW_40,
    _anchor_rank,
    _anchors_for_snapshot,
    _has_public_anchor,
    _key,
)
from loaders.combined_fights import load_combined_fights
from ratings.age import load_birth_dates
from ratings.org_strength import (
    apply_org_weight_model,
    default_org_weight_specs,
    organization_bridge_table,
)
from ratings.rate_snapshot import attach_bout_weights
from ratings.scope import DEFAULT_PUBLISHED_SCOPE
from ratings.symon_score import DEFAULT_CAREER_REFERENCE, career_skill_mass, parse_reference
from ratings.whr import run_whr


def _coverage(fights: pd.DataFrame) -> pd.DataFrame:
    sides = pd.concat(
        [
            fights[["fighter_a", "source_corpus"]].rename(columns={"fighter_a": "fighter"}),
            fights[["fighter_b", "source_corpus"]].rename(columns={"fighter_b": "fighter"}),
        ],
        ignore_index=True,
        sort=False,
    ).dropna(subset=["fighter"])
    sides["is_ufc"] = sides["source_corpus"].isin({"ufc", "pre_unified"})
    return (
        sides.groupby("fighter", sort=False)
        .agg(total_bouts=("source_corpus", "size"), ufc_bouts=("is_ufc", "sum"))
        .reset_index()
    )


def _rank_career(career: pd.DataFrame) -> pd.DataFrame:
    out = career.rename(columns={"score": "career_skill_mass"}).copy()
    out["career_skill_mass"] = pd.to_numeric(out["career_skill_mass"], errors="coerce")
    out = out[out["career_skill_mass"].gt(0)].copy()
    out = out.sort_values(["career_skill_mass", "fighter"], ascending=[False, True]).reset_index(drop=True)
    out["model_rank"] = out.index + 1
    return out


def _top100_metrics(
    ranked: pd.DataFrame,
    fights: pd.DataFrame,
    *,
    anchors: dict[str, list[dict[str, object]]],
) -> dict[str, object]:
    top = ranked.head(100).merge(_coverage(fights), on="fighter", how="left")
    top["anchor_rank"] = top["fighter"].map(lambda name: _anchor_rank(name, anchors))
    top["has_public_anchor"] = top["fighter"].map(lambda name: _has_public_anchor(name, anchors))
    top["delta_vs_anchor"] = top["model_rank"] - top["anchor_rank"]
    top["external_only"] = top["ufc_bouts"].fillna(0).eq(0)

    rank_by_key = {_key(row.fighter): int(row.model_rank) for row in ranked.itertuples()}
    watch_missing_or_low = [
        name for name in WATCH_BELOW_40
        if rank_by_key.get(_key(name)) is None or int(rank_by_key[_key(name)]) > 40
    ]
    anchored = top[top["anchor_rank"].notna()]
    severe_over = anchored[anchored["delta_vs_anchor"].le(-40)]
    severe_under = anchored[anchored["delta_vs_anchor"].ge(40)]
    return {
        "ranked_fighters": int(len(ranked)),
        "top100_public_anchor_count": int(top["has_public_anchor"].sum()),
        "top25_unanchored_count": int((~top.head(25)["has_public_anchor"]).sum()),
        "top100_external_only": int(top["external_only"].sum()),
        "severe_overplacements": int(len(severe_over)),
        "severe_underplacements": int(len(severe_under)),
        "watch_names_below_40_or_missing": watch_missing_or_low,
        "top10": top.head(10)[["model_rank", "fighter", "career_skill_mass"]].to_dict("records"),
    }


def build(snapshot_dir: Path, *, scope: str, reference: str | float, out_dir: Path) -> dict[str, object]:
    snapshot_dir = Path(snapshot_dir)
    out_dir = Path(out_dir)
    fights, combined_summary = load_combined_fights(snapshot_dir, scope=scope, label="org-strength")
    if "is_excluded" in fights.columns:
        fights = fights[~fights["is_excluded"].fillna(False).astype(bool)].copy()
    fights = fights.reset_index(drop=True)
    anchors, _ = _anchors_for_snapshot(snapshot_dir)
    birth_dates = load_birth_dates(snapshot_dir)

    bridge = organization_bridge_table(fights)
    specs = default_org_weight_specs()
    rows = []
    top_frames = []
    for spec in specs:
        weighted = apply_org_weight_model(fights, spec)
        whr = run_whr(
            attach_bout_weights(weighted),
            birth_dates=birth_dates,
            age_drift=True,
        )
        career = career_skill_mass(whr, reference=reference)
        ranked = _rank_career(career)
        metrics = _top100_metrics(ranked, weighted, anchors=anchors)
        org_weight = pd.to_numeric(weighted["org_weight"], errors="coerce")
        rows.append(
            {
                "model": spec.label(),
                "min_org_weight": float(org_weight.min()) if len(org_weight) else None,
                "mean_org_weight": float(org_weight.mean()) if len(org_weight) else None,
                "non_ufc_mean_org_weight": (
                    float(org_weight[~weighted["source_corpus"].isin({"ufc", "pre_unified"})].mean())
                    if (~weighted["source_corpus"].isin({"ufc", "pre_unified"})).any()
                    else None
                ),
                **metrics,
            }
        )
        top = ranked.head(100).copy()
        top["model"] = spec.label()
        top_frames.append(top)
        print(f"[org-strength] {spec.label()}: top25_unanchored={metrics['top25_unanchored_count']} "
              f"external_only={metrics['top100_external_only']}")

    out_dir.mkdir(parents=True, exist_ok=True)
    summary_rows = pd.DataFrame(rows)
    summary_rows.to_parquet(out_dir / "org_strength_audit.parquet", index=False)
    if top_frames:
        pd.concat(top_frames, ignore_index=True, sort=False).to_parquet(
            out_dir / "org_strength_top100.parquet",
            index=False,
        )
    bridge.to_parquet(out_dir / "org_bridge_support.parquet", index=False)
    summary = {
        "snapshot": snapshot_dir.name,
        "scope": scope,
        "reference": str(reference),
        "combined_fights": combined_summary,
        "models": rows,
        "bridge_orgs": int(len(bridge)),
    }
    (out_dir / "org_strength_audit.json").write_text(
        json.dumps(summary, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("snapshot_dir", type=Path)
    ap.add_argument("--scope", default=DEFAULT_PUBLISHED_SCOPE)
    ap.add_argument("--reference", default=str(DEFAULT_CAREER_REFERENCE))
    ap.add_argument("--out-dir", type=Path, default=Path("data/model_tuning/org-strength"))
    args = ap.parse_args()
    print(
        json.dumps(
            build(
                args.snapshot_dir,
                scope=args.scope,
                reference=parse_reference(args.reference),
                out_dir=args.out_dir,
            ),
            indent=2,
            default=str,
        )
    )


if __name__ == "__main__":
    main()
