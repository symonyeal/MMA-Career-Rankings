"""History lookups: pre-event filter states and strictly earlier opponent ratings.

The two operations differ for same-day tournaments and are kept explicit.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def opponent_ratings(wins: pd.DataFrame, history: pd.DataFrame) -> pd.DataFrame:
    """Join sorted wins to sorted WHR history, excluding every rating on the bout date."""
    return pd.merge_asof(
        wins, history.rename(columns={"fighter": "opponent", "mu_whr": "opponent_mu"}),
        on="event_date", by="opponent", allow_exact_matches=False,
    )


def prefight_ratings(history: pd.DataFrame) -> pd.DataFrame:
    """Per-(fighter, event) pre-event ``mu`` snapshot from ``ratings_history``."""
    if history is None or history.empty:
        return pd.DataFrame(columns=["fighter", "event_date", "event_name", "prefight_mu"])
    h = history[["fighter", "event_date", "event_name", "mu_canonical"]].copy()
    h["event_date"] = pd.to_datetime(h["event_date"], errors="coerce")
    # A tournament can put one fighter in several history rows on one event.
    # The lookup joined below is event-grained, so returning all of those rows
    # turns each fight into a many-to-many merge (three rows for one fighter and
    # two for the opponent produce six copies of the appearance).  Preserve the
    # engine's within-day order, take the state before the first row of the
    # event, and expose exactly one lookup row per event.
    h["_history_order"] = np.arange(len(h))
    h = h.sort_values(
        ["fighter", "event_date", "_history_order"], kind="stable"
    )
    h["prefight_mu"] = h.groupby("fighter")["mu_canonical"].shift(1).fillna(1500.0)
    return (
        h.drop_duplicates(["fighter", "event_date", "event_name"], keep="first")
        [["fighter", "event_date", "event_name", "prefight_mu"]]
        .reset_index(drop=True)
    )
