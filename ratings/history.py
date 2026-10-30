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


def entering_ratings(history: pd.DataFrame, mu_col: str, phi_col: str) -> pd.DataFrame:
    """Each history row's rating *entering* that appearance, plus prior fight count."""
    cols = ["fighter", "event_date", "event_name", f"pre_{mu_col}", f"pre_{phi_col}", "opponents_this_event"]
    h = history[cols].rename(columns={f"pre_{mu_col}": "pre_mu", f"pre_{phi_col}": "pre_phi"}).copy()
    h["event_date"] = pd.to_datetime(h["event_date"], errors="coerce")
    h = h.sort_values(["fighter", "event_date", "event_name"], kind="stable")
    h["prior_fights"] = h.groupby("fighter")["opponents_this_event"].cumsum() - h["opponents_this_event"]
    return h[["fighter", "event_date", "event_name", "pre_mu", "pre_phi", "prior_fights"]]


def attach_prefight_ratings(fights: pd.DataFrame, history: pd.DataFrame) -> pd.DataFrame:
    """Join each corner's tournament-safe pre-event rating, defaulting unknown states to the prior."""
    prior = prefight_ratings(history)
    out = fights
    for side in ("a", "b"):
        column = f"prefight_mu_{side}"
        out = out.merge(
            prior.rename(columns={"fighter": f"fighter_{side}", "prefight_mu": column}),
            on=[f"fighter_{side}", "event_date", "event_name"], how="left", validate="many_to_one",
        )
        out[column] = pd.to_numeric(out[column], errors="coerce").fillna(1500.0)
    return out
