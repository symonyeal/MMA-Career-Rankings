"""Check committed fight evidence and the inputs needed to rebuild the release."""
import json
import sys
from pathlib import Path

import pandas as pd

p = Path(__file__).parents[3]
sys.path.insert(0, str(p))
from loaders.combined_fights import load_combined_fights

d = p / "data/snapshots/2026-08-13"
f = pd.read_parquet(d / "combined_fights.parquet")
x, s = load_combined_fights(d, scope="majors,pre_unified")
r = json.loads((d / "rating_run.json").read_text(encoding="utf-8"))
y = x.loc[x.is_model_bout]
a = ["canonical_fights.parquet", "canonical_rounds.parquet", "canonical_fighters.parquet",
     "majors_fights.parquet", "career_coverage.parquet", "ratings_current.parquet",
     "ratings_history_whr.parquet", "prime_elite_board.parquet", "current_board.parquet"]
z = {
    "available_records": len(f),
    "selected_records": len(x),
    "model_bouts": int(x.is_model_bout.sum()),
    "model_fighters": pd.concat([y.fighter_a, y.fighter_b]).nunique(),
    "date_range": s["date_range"],
    "manifest_bouts_match": int(x.is_model_bout.sum()) == r["rated_bouts"],
    "manifest_fighters_match": pd.concat([y.fighter_a, y.fighter_b]).nunique() == r["current_fighters"],
    "self_bouts": int(y.fighter_a.eq(y.fighter_b).sum()),
    "invalid_decided_winner": int((~y.is_draw & ~y.winner.eq(y.fighter_a) & ~y.winner.eq(y.fighter_b)).sum()),
    "missing_date": int(y.event_date.isna().sum()),
    "missing_participant": int(y[["fighter_a", "fighter_b"]].isna().any(axis=1).sum()),
    "missing_release_inputs_or_artifacts": [k for k in a if not (d / k).exists()],
    "sherdog_attribution_present": (p / "data/external/sherdog/ATTRIBUTION.txt").exists(),
    "fightmatrix_attribution_present": (p / "data/external/fightmatrix/ATTRIBUTION.txt").exists(),
}
print(json.dumps(z, indent=2))
