"""Integrity sleeve: per-fighter-appearance damp for tainted results.

The integrity sleeve operates on the **method** rating stream only. It
NEVER touches the canonical rating. The sleeve attaches a multiplicative
per-fight update weight that damps:

* PED-confirmed offences — the flagged winner's result is damped at the -20%
  floor (``INTEGRITY_PED_FACTOR``). Flagged losses are not damped because
  dampening a loss would soften the penalty.
* DQ wins — the winner of a disqualification bout is damped by 8%
  (``INTEGRITY_DQ_WIN_FACTOR``). The loser (the disqualified fighter)
  carries no extra damp; they already lost.
* Missed-weight wins — the winner who missed weight is damped by 12%
  (``INTEGRITY_MISSED_WEIGHT_WIN_FACTOR``).

Multiple flags compose multiplicatively and are clamped to
``[SLEEVE_FACTOR_MIN, 1.0]`` — integrity only penalises, never rewards.
A fighter without any flag on a fight gets a weight of 1.0 and the
weighted Glicko update reduces exactly to the unweighted update.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ratings.constants import (
    INTEGRITY_DQ_WIN_FACTOR,
    INTEGRITY_MISSED_WEIGHT_WIN_FACTOR,
    INTEGRITY_PED_FACTOR,
    SLEEVE_FACTOR_MIN,
)


INTEGRITY_APPEARANCE_COLUMNS = (
    "fight_url",
    "fighter",
    "integrity_factor_ped",
    "integrity_factor_dq",
    "integrity_factor_missed_weight",
    "integrity_weight",
)


def _explode_to_appearances(fights: pd.DataFrame) -> pd.DataFrame:
    """Two rows per fight: one per fighter, plus the bout's integrity flags."""
    cols = [
        "fight_url",
        "fighter_a",
        "fighter_b",
        "winner",
        "is_draw",
        "ped_confirmed",
        "ped_flagged_fighter",
        "is_dq",
        "dq_winner",
        "missed_weight",
        "missed_weight_fighter",
    ]
    available = [c for c in cols if c in fights.columns]
    base = fights[available].copy()
    a = base.rename(columns={"fighter_a": "fighter", "fighter_b": "opponent"})
    b = base.rename(columns={"fighter_b": "fighter", "fighter_a": "opponent"})
    return pd.concat([a, b], ignore_index=True, sort=False)


def build_integrity_appearances(fights: pd.DataFrame) -> pd.DataFrame:
    """Produce the per-(fight, fighter) integrity weight table.

    Required columns on ``fights`` (any missing defaults to "flag off"):
    ``fight_url``, ``fighter_a``, ``fighter_b``, ``winner``, ``is_draw``,
    ``ped_confirmed``, ``ped_flagged_fighter``,
    ``is_dq``, ``dq_winner``, ``missed_weight``, ``missed_weight_fighter``.
    """
    if fights is None or fights.empty:
        return pd.DataFrame(columns=list(INTEGRITY_APPEARANCE_COLUMNS))

    appear = _explode_to_appearances(fights)
    is_draw = appear.get("is_draw", pd.Series(False, index=appear.index)).fillna(False).astype(bool)
    is_winner = appear["winner"].eq(appear["fighter"]) & ~is_draw

    ped_flag = (
        appear.get("ped_confirmed", pd.Series(False, index=appear.index)).fillna(False).astype(bool)
        & is_winner
        & appear.get("ped_flagged_fighter", pd.Series(None, index=appear.index)).eq(appear["fighter"])
    )
    dq_flag = (
        appear.get("is_dq", pd.Series(False, index=appear.index)).fillna(False).astype(bool)
        & is_winner
        & appear.get("dq_winner", pd.Series(None, index=appear.index)).eq(appear["fighter"])
    )
    mw_flag = (
        appear.get("missed_weight", pd.Series(False, index=appear.index)).fillna(False).astype(bool)
        & is_winner
        & appear.get("missed_weight_fighter", pd.Series(None, index=appear.index)).eq(appear["fighter"])
    )

    appear["integrity_factor_ped"] = np.where(ped_flag, INTEGRITY_PED_FACTOR, 1.0)
    appear["integrity_factor_dq"] = np.where(dq_flag, INTEGRITY_DQ_WIN_FACTOR, 1.0)
    appear["integrity_factor_missed_weight"] = np.where(mw_flag, INTEGRITY_MISSED_WEIGHT_WIN_FACTOR, 1.0)

    product = (
        appear["integrity_factor_ped"]
        * appear["integrity_factor_dq"]
        * appear["integrity_factor_missed_weight"]
    )
    appear["integrity_weight"] = product.clip(lower=SLEEVE_FACTOR_MIN, upper=1.0)

    return appear[list(INTEGRITY_APPEARANCE_COLUMNS)].copy()
