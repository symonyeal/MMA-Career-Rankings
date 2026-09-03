"""The Current board: what it ranks, and who it refuses to rank.

Current is the only board where "now" is part of the question, so it is the only
one carrying a recency bar. It is also the board most exposed to the standing
defect in this kind of model -- nothing caps an unbeaten record from above, so a
fighter who rarely loses in a weak field rates alongside one who has beaten
contenders. Ranked on the raw projected rating, the men's top thirty held six
Bellator and PFL fighters with Usman Nurmagomedov 2nd. These tests hold the two
screens and the exposure adjustment that answer that.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

import build_boards
from ratings.boards import completeness_gated_board, exposure_shrunk_level

SNAPSHOT = Path(__file__).resolve().parents[1] / "data" / "snapshots" / "2026-08-13"


# --- the exposure adjustment ------------------------------------------------

def test_full_exposure_leaves_a_rating_untouched():
    levels = pd.Series([2100.0, 1600.0])
    got = exposure_shrunk_level(levels, pd.Series([1.0, 1.0]), anchor=1750.0)
    assert got.tolist() == pytest.approx(levels.tolist())


def test_shrinkage_pulls_toward_the_anchor_from_both_sides():
    got = exposure_shrunk_level(
        pd.Series([2150.0, 1350.0]), pd.Series([0.5, 0.5]), anchor=1750.0
    )
    assert got.tolist() == pytest.approx([1950.0, 1550.0])


def test_the_adjustment_is_additive_not_multiplicative():
    """A rating is an interval scale, so the factor must not scale the value.

    ``0.85 * 2000 = 1700`` assumes the scale has an origin at zero. It has not,
    which is why the distance from the anchor is what shrinks.
    """
    got = float(exposure_shrunk_level(pd.Series([2000.0]), pd.Series([0.85]), anchor=1750.0).iloc[0])
    assert got == pytest.approx(1962.5)
    assert got != pytest.approx(1700.0)


def test_a_missing_exposure_factor_is_read_as_no_discount():
    got = exposure_shrunk_level(pd.Series([2000.0]), pd.Series([None]), anchor=1750.0)
    assert float(got.iloc[0]) == pytest.approx(2000.0)


def test_shrinkage_cannot_reorder_two_fighters_with_equal_exposure():
    levels = pd.Series([2100.0, 1900.0, 1800.0])
    got = exposure_shrunk_level(levels, pd.Series([0.6, 0.6, 0.6]), anchor=1750.0)
    assert got.is_monotonic_decreasing


# --- the recency bar --------------------------------------------------------

def _population(**overrides) -> pd.DataFrame:
    base = pd.DataFrame({
        "fighter": ["active", "retired", "unknown"],
        "score": [2000.0, 2100.0, 1900.0],
        "rating_periods": [20, 20, 20],
    })
    return base.assign(**overrides)


def test_a_fighter_past_the_recency_bar_is_withheld_not_ranked_last():
    idle = pd.Series({"active": 4.0, "retired": 60.0, "unknown": 4.0})
    board = completeness_gated_board(
        _population(), rating_col="score", min_rating_periods=13,
        months_inactive=idle, max_months_inactive=18.0,
    ).set_index("fighter")
    assert board.loc["active", "status"] == "ranked"
    assert pd.isna(board.loc["retired", "rank"])
    assert "not currently active enough" in board.loc["retired", "status"]


def test_an_unknown_last_bout_is_withheld_rather_than_assumed_active():
    idle = pd.Series({"active": 4.0, "retired": 60.0})
    board = completeness_gated_board(
        _population(), rating_col="score", min_rating_periods=13,
        months_inactive=idle, max_months_inactive=18.0,
    ).set_index("fighter")
    assert pd.isna(board.loc["unknown", "rank"])


def test_no_recency_bar_means_no_recency_gate():
    """Every retrospective board must be unaffected: a career does not expire."""
    board = completeness_gated_board(
        _population(), rating_col="score", min_rating_periods=13,
    )
    assert board["status"].eq("ranked").all()
    assert "months_inactive" not in board.columns


# --- the tested-record screen ----------------------------------------------

def test_the_gate_reason_names_the_evidence_the_caller_screened_on():
    bouts = pd.Series({"active": 12.0, "retired": 2.0, "unknown": 12.0})
    board = completeness_gated_board(
        _population(), rating_col="score", min_rating_periods=13,
        tested_wins=bouts, min_tested_wins=8, tested_wins_label="UFC bouts",
    ).set_index("fighter")
    assert board.loc["retired", "status"] == (
        "insufficient proven record to rank (< 8 UFC bouts)"
    )


def test_the_default_gate_reason_is_unchanged_for_the_prime_board():
    wins = pd.Series({"active": 6.0, "retired": 1.0, "unknown": 6.0})
    board = completeness_gated_board(
        _population(), rating_col="score", min_rating_periods=13,
        tested_wins=wins, min_tested_wins=5,
    ).set_index("fighter")
    assert board.loc["retired", "status"] == (
        "insufficient proven record to rank (< 5 wins over tested contenders)"
    )


# --- the published artifact -------------------------------------------------

def _published() -> pd.DataFrame:
    path = SNAPSHOT / "current_board.parquet"
    if not path.exists():
        pytest.skip("snapshot artifact not present")
    return pd.read_parquet(path)


def test_every_ranked_fighter_clears_both_published_screens():
    board = _published()
    ranked = board[board["status"].eq("ranked")]
    assert not ranked.empty
    assert (ranked["tested_opponent_wins"] >= build_boards.CURRENT_MIN_UFC_BOUTS).all()
    assert (ranked["months_inactive"] <= build_boards.CURRENT_MAX_MONTHS_INACTIVE).all()


def test_the_board_is_ordered_by_the_score_it_publishes():
    board = _published()
    ranked = board[board["status"].eq("ranked")].sort_values("rank")
    assert ranked[build_boards.CURRENT_SCORE_COL].is_monotonic_decreasing


def test_the_retired_champions_the_bar_exists_for_are_absent():
    """The two fighters whose placement made the recency bar necessary."""
    board = _published().set_index("fighter")
    for fighter in ("Khabib Nurmagomedov", "Georges St-Pierre"):
        if fighter in board.index:
            assert board.loc[fighter, "status"] != "ranked"


def test_the_current_board_is_not_a_re_sort_of_the_all_time_board():
    """Three boards, three questions. If Current agreed with All-time it would
    not be worth publishing, and a reader could add them together."""
    current = _published()
    all_time = pd.read_parquet(SNAPSHOT / "completeness_gated_board.parquet")
    top_current = list(current[current["status"].eq("ranked")].sort_values("rank")["fighter"].head(10))
    top_all_time = list(all_time[all_time["status"].eq("ranked")].sort_values("rank")["fighter"].head(10))
    assert top_current != top_all_time


# --- time away compounds ----------------------------------------------------

def _fight_snapshot(tmp_path, rows):
    snap = tmp_path / "snap"
    snap.mkdir()
    pd.DataFrame(rows).to_parquet(snap / "combined_fights.parquet", index=False)
    return snap


def test_a_fighter_active_every_year_has_no_idle_time(tmp_path):
    rows = [
        {"fighter_a": "busy", "fighter_b": "other",
         "event_date": pd.Timestamp(f"{year}-06-01"), "is_model_bout": True}
        for year in range(2017, 2027)
    ]
    idle = build_boards.recent_idle_years(_fight_snapshot(tmp_path, rows))
    assert idle["busy"] == pytest.approx(0.0)


def test_a_decade_gap_ending_in_a_comeback_is_still_idle_time(tmp_path):
    """The case the discount exists for: the layoff ended, so the recency bar
    sees an active fighter and the idle years are what charge the decade."""
    rows = [
        {"fighter_a": "comeback", "fighter_b": "other",
         "event_date": pd.Timestamp("2016-12-30"), "is_model_bout": True},
        {"fighter_a": "comeback", "fighter_b": "other",
         "event_date": pd.Timestamp("2026-05-16"), "is_model_bout": True},
    ]
    idle = build_boards.recent_idle_years(_fight_snapshot(tmp_path, rows))
    assert idle["comeback"] == pytest.approx(8.0)


def test_unrated_bouts_do_not_count_as_activity(tmp_path):
    rows = [
        {"fighter_a": "a", "fighter_b": "b",
         "event_date": pd.Timestamp("2026-05-16"), "is_model_bout": True},
        {"fighter_a": "a", "fighter_b": "b",
         "event_date": pd.Timestamp("2023-05-16"), "is_model_bout": False},
    ]
    idle = build_boards.recent_idle_years(_fight_snapshot(tmp_path, rows))
    assert idle["a"] == pytest.approx(9.0)


def test_the_discount_compounds_rather_than_accruing_a_fixed_charge():
    """Two idle years must cost more than twice one, on the remaining edge."""
    rate = build_boards.CURRENT_ANNUAL_RETENTION
    edge = 200.0
    one = edge * (1 - rate)
    two = edge * (1 - rate ** 2)
    assert two < 2 * one
    assert two > one


def test_eight_idle_years_leave_a_small_fraction_of_the_edge():
    """The Rousey case: a decade away must not be a rounding error."""
    retained = build_boards.CURRENT_ANNUAL_RETENTION ** 8
    assert retained < 0.20


def test_the_published_board_charges_idle_years_monotonically():
    """Equal ratings and exposure: more idle years can never score higher."""
    board = _published()
    ranked = board[board["status"].eq("ranked")]
    assert "current_idle_years" in ranked.columns
    assert (ranked["current_idle_years"] >= 0).all()
    assert ranked["current_idle_years"].max() > 0, "no idle time is being measured"


def test_the_comeback_fighter_is_below_the_published_womens_top_ten():
    path = SNAPSHOT / "current_board_women.parquet"
    if not path.exists():
        pytest.skip("snapshot artifact not present")
    women = pd.read_parquet(path).set_index("fighter")
    if "Ronda Rousey" not in women.index:
        pytest.skip("fighter not in this snapshot")
    row = women.loc["Ronda Rousey"]
    assert row["current_idle_years"] >= 8
    assert row["rank"] > 10, (
        "a decade-old rating is back inside the published women's top ten"
    )
