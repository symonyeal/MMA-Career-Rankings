"""Check that a returned elite Prime window contains its reported mean.

INPUT   five qualifying wins at 2100, then one nonqualifying bout at 1500.
OUTPUT  the returned window and its actual mean versus elite_level.
"""
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parents[3]))
from ratings.opponent_quality import best_elite_decade

dates = pd.to_datetime([f"{t}-01-01" for t in range(2000, 2005)])
wins = pd.DataFrame({"fighter": ["A"] * 5, "event_date": dates})
h = pd.DataFrame({
    "fighter": ["A"] * 6,
    "event_date": [*dates, pd.Timestamp("2009-01-01")],
    "mu_whr": [2100.] * 5 + [1500.],
})
r = best_elite_decade(wins, h).iloc[0]
inside = h.event_date.between(r.elite_window_start, r.elite_window_end)
print(json.dumps({
    "elite_wins": int(r.elite_wins),
    "elite_window_start": str(r.elite_window_start.date()),
    "elite_window_end": str(r.elite_window_end.date()),
    "reported_elite_level": float(r.elite_level),
    "mean_inside_returned_window": float(h.loc[inside, "mu_whr"].mean()),
    "mean_in_actual_ten_year_window": float(h.mu_whr.mean()),
}, indent=2))
