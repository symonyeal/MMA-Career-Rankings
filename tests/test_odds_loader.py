"""Phase A tests: odds conversions and pandas enrichment.

Covers `loaders/odds_loader.py` only. The empirical-distribution and
weight-assignment math is exercised in `test_odds_adjustment.py`.
"""
from __future__ import annotations

import math
from pathlib import Path

import pandas as pd
import pytest

from loaders.odds_loader import (
    ENRICHED_ODDS_COLUMNS,
    RAW_ODDS_COLUMNS,
    american_to_decimal,
    american_to_implied,
    compute_implied_probs,
    decimal_to_implied,
    has_odds_artifact,
    load_odds_lines,
    remove_vig,
)


# ---------------------------------------------------------------------------
# American odds

def test_american_plus_200_is_one_third():
    # +200 underdog -> 100 / (200 + 100) = 1/3
    assert american_to_implied(200) == pytest.approx(1.0 / 3.0)


def test_american_minus_200_is_two_thirds():
    # -200 favorite -> 200 / (200 + 100) = 2/3
    assert american_to_implied(-200) == pytest.approx(2.0 / 3.0)


def test_american_minus_110_is_near_coin_flip():
    # The classic juiced line: both sides at -110 imply 0.524 each.
    p = american_to_implied(-110)
    assert p == pytest.approx(110.0 / 210.0)
    assert 0.52 < p < 0.53


def test_american_invalid_inputs_return_none():
    assert american_to_implied(None) is None
    assert american_to_implied(0) is None
    assert american_to_implied(float("nan")) is None
    assert american_to_implied("not a number") is None


def test_american_to_decimal_round_trips_through_implied():
    # +200 -> decimal 3.0 -> implied 1/3.
    assert american_to_decimal(200) == pytest.approx(3.0)
    # -200 -> decimal 1.5 -> implied 2/3.
    assert american_to_decimal(-200) == pytest.approx(1.5)


# ---------------------------------------------------------------------------
# Decimal odds

def test_decimal_two_is_fifty_percent():
    assert decimal_to_implied(2.0) == pytest.approx(0.5)


def test_decimal_one_point_five_is_two_thirds():
    assert decimal_to_implied(1.5) == pytest.approx(2.0 / 3.0)


def test_decimal_invalid_inputs_return_none():
    assert decimal_to_implied(None) is None
    assert decimal_to_implied(1.0) is None       # 1.0 means no payout
    assert decimal_to_implied(0.5) is None       # nonsense
    assert decimal_to_implied(float("nan")) is None


# ---------------------------------------------------------------------------
# Vig removal

def test_remove_vig_sums_to_one_for_typical_juiced_line():
    # -110 / -110 raws are ~0.524 / ~0.524, sum 1.048 -> 0.5 / 0.5 after no-vig.
    p_a = american_to_implied(-110)
    p_b = american_to_implied(-110)
    nva, nvb = remove_vig(p_a, p_b)
    assert nva + nvb == pytest.approx(1.0, abs=1e-12)
    assert nva == pytest.approx(0.5)


def test_remove_vig_sums_to_one_for_lopsided_line():
    # -500 favorite vs +400 underdog
    p_a = american_to_implied(-500)  # ~0.833
    p_b = american_to_implied(400)   # 0.2
    nva, nvb = remove_vig(p_a, p_b)
    assert nva + nvb == pytest.approx(1.0, abs=1e-12)
    # favorite still favored after no-vig
    assert nva > nvb


def test_remove_vig_handles_missing_sides():
    assert remove_vig(None, 0.5) == (None, None)
    assert remove_vig(0.5, None) == (None, None)
    assert remove_vig(float("nan"), 0.5) == (None, None)


# ---------------------------------------------------------------------------
# DataFrame enrichment

def _sample_raw_odds() -> pd.DataFrame:
    """A small synthetic raw-odds frame covering each branch."""
    return pd.DataFrame([
        # 1. Clean American line, A is heavy favorite.
        {
            "fight_url": "u/fav-a", "event_date": "2024-01-01", "event_name": "E1",
            "fighter_a": "Alice", "fighter_b": "Bob",
            "odds_source": "fixture",
            "odds_fighter_a": "Alice", "odds_fighter_b": "Bob",
            "american_odds_a": -500, "american_odds_b": 400,
            "decimal_odds_a": None, "decimal_odds_b": None,
        },
        # 2. Decimal-only line, B is favorite.
        {
            "fight_url": "u/dec-b", "event_date": "2024-01-01", "event_name": "E1",
            "fighter_a": "Carol", "fighter_b": "Dan",
            "odds_source": "fixture",
            "odds_fighter_a": "Carol", "odds_fighter_b": "Dan",
            "american_odds_a": None, "american_odds_b": None,
            "decimal_odds_a": 3.0, "decimal_odds_b": 1.5,
        },
        # 3. Coin flip -110 / -110.
        {
            "fight_url": "u/flip", "event_date": "2024-02-01", "event_name": "E2",
            "fighter_a": "Eve", "fighter_b": "Frank",
            "odds_source": "fixture",
            "odds_fighter_a": "Eve", "odds_fighter_b": "Frank",
            "american_odds_a": -110, "american_odds_b": -110,
            "decimal_odds_a": None, "decimal_odds_b": None,
        },
        # 4. Missing side B -- should produce one_side_missing.
        {
            "fight_url": "u/missing-b", "event_date": "2024-03-01", "event_name": "E3",
            "fighter_a": "Gina", "fighter_b": "Hank",
            "odds_source": "fixture",
            "odds_fighter_a": "Gina", "odds_fighter_b": "Hank",
            "american_odds_a": -150, "american_odds_b": None,
            "decimal_odds_a": None, "decimal_odds_b": None,
        },
    ])


def test_compute_implied_probs_adds_expected_columns():
    df = compute_implied_probs(_sample_raw_odds())
    for col in ENRICHED_ODDS_COLUMNS:
        assert col in df.columns


def test_compute_implied_probs_identifies_american_favorite():
    df = compute_implied_probs(_sample_raw_odds()).set_index("fight_url")
    row = df.loc["u/fav-a"]
    assert row["market_favorite"] == "Alice"
    assert row["market_underdog"] == "Bob"
    assert row["market_favorite_prob"] > row["market_underdog_prob"]
    # no-vig pair sums to 1.0
    assert row["implied_prob_a_no_vig"] + row["implied_prob_b_no_vig"] == pytest.approx(1.0)
    assert row["odds_data_quality"] == "ok"


def test_compute_implied_probs_identifies_decimal_favorite():
    df = compute_implied_probs(_sample_raw_odds()).set_index("fight_url")
    row = df.loc["u/dec-b"]
    # decimal 1.5 = implied 0.667 = favorite; 3.0 = 0.333 = underdog
    assert row["market_favorite"] == "Dan"
    assert row["market_underdog"] == "Carol"
    assert row["odds_data_quality"] == "ok"


def test_compute_implied_probs_coinflip_has_no_favorite():
    df = compute_implied_probs(_sample_raw_odds()).set_index("fight_url")
    row = df.loc["u/flip"]
    # exact -110/-110 -> exact 0.5/0.5 after no-vig -> no defined favorite
    assert pd.isna(row["market_favorite"])
    assert pd.isna(row["market_underdog"])
    assert row["implied_prob_a_no_vig"] == pytest.approx(0.5)
    assert row["implied_prob_b_no_vig"] == pytest.approx(0.5)
    assert row["odds_data_quality"] == "ok"


def test_compute_implied_probs_flags_one_side_missing():
    df = compute_implied_probs(_sample_raw_odds()).set_index("fight_url")
    row = df.loc["u/missing-b"]
    assert row["odds_data_quality"] == "one_side_missing"
    assert pd.isna(row["market_favorite"])
    # raw prob for A is still computed
    assert row["implied_prob_a_raw"] == pytest.approx(american_to_implied(-150))
    # no-vig is undefined when one side is missing
    assert pd.isna(row["implied_prob_a_no_vig"])


def test_compute_implied_probs_on_empty_frame_returns_enriched_schema():
    raw = pd.DataFrame({c: pd.Series(dtype="object") for c in RAW_ODDS_COLUMNS})
    out = compute_implied_probs(raw)
    for col in ENRICHED_ODDS_COLUMNS:
        assert col in out.columns
    assert len(out) == 0


# ---------------------------------------------------------------------------
# Snapshot I/O

def test_load_odds_lines_absent_artifact_returns_empty(tmp_path: Path):
    snap = tmp_path / "snap"
    snap.mkdir()
    assert has_odds_artifact(snap) is False
    df = load_odds_lines(snap)
    assert df.empty
    # enriched schema still present so downstream merges don't KeyError
    for col in list(RAW_ODDS_COLUMNS) + list(ENRICHED_ODDS_COLUMNS):
        assert col in df.columns


def test_load_odds_lines_round_trip(tmp_path: Path):
    snap = tmp_path / "snap"
    snap.mkdir()
    raw = _sample_raw_odds()
    raw.to_parquet(snap / "odds_lines.parquet", index=False)
    assert has_odds_artifact(snap) is True

    df = load_odds_lines(snap)
    assert len(df) == 4
    # enriched columns populated
    for col in ENRICHED_ODDS_COLUMNS:
        assert col in df.columns
    qualities = set(df["odds_data_quality"])
    assert "ok" in qualities
    assert "one_side_missing" in qualities
