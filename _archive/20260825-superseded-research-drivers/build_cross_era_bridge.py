"""Measure the cross-era bridge and conditional debut-year gradient by scope."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from analysis.investigations.era_skew import graph_features, ols
from ratings import prequential as PQ
from ratings.rate_snapshot import attach_bout_weights
from ratings.scope import DEFAULT_PUBLISHED_SCOPE
from ratings.whr import run_whr
from ratings.age import load_birth_dates


def audit(snapshot_dir: Path, *, scope: str) -> tuple[dict, pd.DataFrame]:
    fights = PQ.load_fight_table(snapshot_dir, scope=scope)
    fights["org_weight"] = 1.0
    history = run_whr(
        attach_bout_weights(fights),
        birth_dates=load_birth_dates(snapshot_dir),
        age_drift=True,
    )

    h = history.assign(year=pd.to_datetime(history["event_date"]).dt.year)
    by_year = {
        int(year): set(group["fighter"])
        for year, group in h[h["year"] >= 2000].groupby("year")
    }
    years = sorted(by_year)
    chain = pd.DataFrame([
        {"year_a": a, "year_b": b, "shared_fighters": len(by_year[a] & by_year[b])}
        for a, b in zip(years, years[1:])
    ])
    narrowest = chain.loc[chain["shared_fighters"].idxmin()]
    span_bridge = len(
        set(h[h["year"].between(2000, 2004)]["fighter"])
        & set(h[h["year"] >= 2016]["fighter"])
    )

    graph = graph_features(fights, history)
    deep = graph[graph["bouts"] >= 8].dropna().copy()
    terms, r2 = ols(
        deep["peak"].to_numpy(dtype=float),
        deep[["bouts", "opp_mean_bouts", "two_hop", "debut_year"]],
    )
    debut = terms.set_index("term").loc["debut_year"]
    summary = {
        "snapshot": Path(snapshot_dir).name,
        "scope": scope,
        "rated_bouts": int(len(fights)),
        "rated_fighters": int(history["fighter"].nunique()),
        "narrowest_year_pair_since_2000": [int(narrowest["year_a"]), int(narrowest["year_b"])],
        "narrowest_shared_fighters": int(narrowest["shared_fighters"]),
        "fighters_active_in_2000_2004_and_2016_plus": int(span_bridge),
        "conditional_debut_year_coef": float(debut["coef"]),
        "conditional_debut_year_t": float(debut["t"]),
        "conditional_model_r2": float(r2),
        "conditional_fighters": int(len(deep)),
    }
    return summary, chain


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot_dir", type=Path)
    parser.add_argument("--scope", default=DEFAULT_PUBLISHED_SCOPE)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    summary, chain = audit(args.snapshot_dir, scope=args.scope)
    slug = args.scope.replace(",", "-")
    out = args.out or Path("data/model_tuning/cross-era-bridge") / (
        f"{args.snapshot_dir.name}-{slug}.json"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    chain.to_parquet(out.with_suffix(".parquet"), index=False)
    print(json.dumps(summary, indent=2))
    print(f"written: {out}")


if __name__ == "__main__":
    main()
