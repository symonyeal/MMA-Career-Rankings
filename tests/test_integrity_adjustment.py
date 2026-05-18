"""Unit tests for the integrity sleeve (PED + DQ + missed-weight)."""
from __future__ import annotations

import pandas as pd
import pytest

from ratings.constants import (
    INTEGRITY_DQ_WIN_FACTOR,
    INTEGRITY_MISSED_WEIGHT_WIN_FACTOR,
    INTEGRITY_PED_FACTOR,
    SLEEVE_FACTOR_MIN,
)
from ratings.integrity_adjustment import build_integrity_appearances


def _bout(**overrides) -> dict:
    base = {
        "fight_url": "u/1",
        "fighter_a": "Alice",
        "fighter_b": "Bob",
        "winner": "Alice",
        "is_draw": False,
        "ped_confirmed": False,
        "ped_flagged_fighter": None,
        "is_dq": False,
        "dq_winner": None,
        "missed_weight": False,
        "missed_weight_fighter": None,
    }
    base.update(overrides)
    return base


def _row(df: pd.DataFrame, fighter: str) -> pd.Series:
    return df[df["fighter"] == fighter].iloc[0]


def test_clean_bout_emits_unit_weights():
    out = build_integrity_appearances(pd.DataFrame([_bout()]))
    assert _row(out, "Alice")["integrity_weight"] == 1.0
    assert _row(out, "Bob")["integrity_weight"] == 1.0


def test_dq_win_damps_winner_only():
    out = build_integrity_appearances(pd.DataFrame([_bout(
        is_dq=True, dq_winner="Alice",
    )]))
    assert _row(out, "Alice")["integrity_weight"] == pytest.approx(INTEGRITY_DQ_WIN_FACTOR)
    assert _row(out, "Bob")["integrity_weight"] == 1.0


def test_missed_weight_win_damps_winner_only():
    out = build_integrity_appearances(pd.DataFrame([_bout(
        missed_weight=True, missed_weight_fighter="Alice",
    )]))
    assert _row(out, "Alice")["integrity_weight"] == pytest.approx(INTEGRITY_MISSED_WEIGHT_WIN_FACTOR)
    assert _row(out, "Bob")["integrity_weight"] == 1.0


def test_ped_confirmed_damps_flagged_fighter_to_floor():
    out = build_integrity_appearances(pd.DataFrame([_bout(
        ped_confirmed=True, ped_flagged_fighter="Alice",
    )]))
    assert _row(out, "Alice")["integrity_weight"] == pytest.approx(INTEGRITY_PED_FACTOR)
    assert _row(out, "Bob")["integrity_weight"] == 1.0


def test_ped_confirmed_loser_is_not_damped():
    out = build_integrity_appearances(pd.DataFrame([_bout(
        winner="Alice", ped_confirmed=True, ped_flagged_fighter="Bob",
    )]))
    assert _row(out, "Alice")["integrity_weight"] == 1.0
    assert _row(out, "Bob")["integrity_weight"] == 1.0


def test_multiple_flags_compose_and_clamp_to_floor():
    out = build_integrity_appearances(pd.DataFrame([_bout(
        ped_confirmed=True, ped_flagged_fighter="Alice",
        is_dq=True, dq_winner="Alice",
        missed_weight=True, missed_weight_fighter="Alice",
    )]))
    # PED alone is already at the -20% floor; product clamps there.
    assert _row(out, "Alice")["integrity_weight"] == pytest.approx(SLEEVE_FACTOR_MIN)


def test_integrity_appearances_handles_empty_frame():
    out = build_integrity_appearances(pd.DataFrame())
    assert list(out.columns)[:2] == ["fight_url", "fighter"]
    assert out.empty
