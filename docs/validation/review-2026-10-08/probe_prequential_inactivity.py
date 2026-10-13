"""Compare reconstructed Glicko forecasts with its entering-event states.

INPUT   A beats B ten times, then both return after twenty years.
OUTPUT  forecast probabilities and deviations before and after lazy inflation.
"""
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parents[3]))
from ratings.glicko2_engine import RatingEngine, predict_win_prob_from_ratings
from ratings.prequential import Inputs, Variant, online_predictions

rows = [{
    "fight_url": str(k),
    "event_date": pd.Timestamp("2000-01-01") + pd.Timedelta(days=k * 10),
    "event_name": f"E{k}", "fighter_a": "A", "fighter_b": "B",
    "winner": "A", "is_draw": False, "method_score_winner": 1.,
} for k in range(10)]
rows.append({
    **rows[-1], "fight_url": "return", "event_name": "Return",
    "event_date": pd.Timestamp("2020-01-01"),
})
f = pd.DataFrame(rows)
p = online_predictions(
    Inputs(snapshot_dir=Path("."), fights=f, history=pd.DataFrame()),
    Variant("canonical", engine="glicko"),
)
e = RatingEngine()
for r in rows[:-1]:
    e.process_event(r["event_date"], r["event_name"], [r])
old_phi = e.states["A"].canonical.phi
for j in ("A", "B"):
    e._inflate(j, rows[-1]["event_date"])
a, b = e.states["A"].canonical, e.states["B"].canonical
print(json.dumps({
    "reconstructed_probability": float(p.loc[p.fight_url.eq("return"), "p_a"].iloc[0]),
    "actual_entering_event_probability": predict_win_prob_from_ratings(a.mu, a.phi, b.mu, b.phi),
    "previous_post_event_phi": old_phi,
    "actual_entering_event_phi": a.phi,
}, indent=2))
