from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

import build_boards
from ratings.boards import (
    INTEGRITY_PENALTY_SCALE,
    UNRANKED_AT_FLOOR_STATUS,
    completeness_gated_board,
    integrity_discounted_board,
)
from ratings.constants import INTEGRITY_PED_FACTOR


def _current() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "fighter": ["Alice", "Bob", "Carl"],
            "rating_periods": [3, 3, 1],
            # Deliberately a different order from WHR to catch unit mixing.
            "symon_career_skill_mass": [20.0, 30.0, 40.0],
            "mu_whr": [1600.0, 1550.0, 1700.0],
            "sustained_peak_headline_mu_whr_integrity_performance": [9000.0, 8000.0, 7000.0],
        }
    )


def test_board_score_selection_is_lean_and_has_safe_fallbacks():
    current = _current()
    assert build_boards.select_core_rating_col(current) == "symon_career_skill_mass"
    assert build_boards.select_integrity_rating_col(current) == "mu_whr"

    without_symon = current.drop(columns="symon_career_skill_mass")
    assert build_boards.select_core_rating_col(without_symon) == "mu_whr"

    current_mu_only = current[["fighter", "mu_whr"]]
    assert build_boards.select_core_rating_col(current_mu_only) == "mu_whr"
    assert build_boards.select_integrity_rating_col(current_mu_only) == "mu_whr"

    retired_only = current[["fighter", "sustained_peak_headline_mu_whr_integrity_performance"]]
    with pytest.raises(ValueError, match="none of the supported rating columns"):
        build_boards.select_core_rating_col(retired_only)
    with pytest.raises(ValueError, match="none of the supported rating columns"):
        build_boards.select_integrity_rating_col(retired_only)


def test_write_board_artifacts_separates_core_score_from_integrity_units(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    snapshot = tmp_path / "snapshot"
    output = tmp_path / "boards"
    snapshot.mkdir()
    _current().to_parquet(snapshot / "ratings_current.parquet", index=False)

    appearances = pd.DataFrame(
        {
            "fight_url": ["u/1", "u/1"],
            "fighter": ["Alice", "Bob"],
            "integrity_factor_ped": [INTEGRITY_PED_FACTOR, 1.0],
            "integrity_factor_dq": [1.0, 1.0],
            "integrity_factor_missed_weight": [1.0, 1.0],
            "integrity_weight": [INTEGRITY_PED_FACTOR, 1.0],
        }
    )
    appearances.to_parquet(snapshot / "integrity_appearances.parquet", index=False)

    fights = pd.DataFrame(
        {
            "fight_url": ["u/1"],
            "event_date": [pd.Timestamp("2024-01-01")],
            "event_name": ["Event 1"],
            "fighter_a": ["Alice"],
            "fighter_b": ["Bob"],
            "winner": ["Alice"],
            "ped_confirmation_detail": ["confirmed test"],
        }
    )
    seen_scope = []

    def fake_load(_snapshot, *, scope):
        seen_scope.append(scope)
        return fights

    monkeypatch.setattr(build_boards.PQ, "load_fight_table", fake_load)

    summary = build_boards.write_board_artifacts(
        snapshot,
        min_rating_periods=2,
        out_dir=output,
    )

    assert summary["core_rating_col"] == "symon_career_skill_mass"
    assert seen_scope == ["majors,pre_unified"]
    assert summary["integrity_rating_col"] == "mu_whr"
    assert summary["ledger_rows"] == 1
    assert summary["ranked_fighters"] == 2
    assert summary["withheld_fighters"] == 1

    ledger = pd.read_parquet(output / "integrity_ledger.parquet")
    discounted = pd.read_parquet(output / "integrity_discounted_board.parquet")
    gated = pd.read_parquet(output / "completeness_gated_board.parquet")

    assert ledger.loc[0, "fighter"] == "Alice"
    assert ledger.loc[0, "reason"] == "ped"

    alice = discounted.set_index("fighter").loc["Alice"]
    expected_cost = (1.0 - INTEGRITY_PED_FACTOR) * INTEGRITY_PENALTY_SCALE
    assert alice["integrity_cost"] == pytest.approx(expected_cost)
    assert alice["integrity_discounted_rating"] == pytest.approx(1600.0 - expected_cost)
    assert "symon_career_skill_mass" not in discounted.columns

    ranked = gated[gated["status"].eq("ranked")]
    assert ranked["fighter"].tolist() == ["Bob", "Alice"]
    assert gated.set_index("fighter").loc["Carl", "status"].startswith(
        "insufficient observed history"
    )


def test_gated_board_shares_one_place_across_a_tie():
    """A tie is one place. It used to be a positional arange over a sort.

    With an ordinal rank, two fighters on an identical score printed at
    consecutive ranks, so the sort's own tie-break read as a rank difference.
    """
    current = pd.DataFrame(
        {
            "fighter": ["Alice", "Bob", "Carl", "Dana"],
            "rating_periods": [20, 20, 20, 20],
            "mu_whr": [1700.0, 1600.0, 1600.0, 1500.0],
        }
    )
    gated = completeness_gated_board(current, rating_col="mu_whr", min_rating_periods=5)
    rank = dict(zip(gated["fighter"], gated["rank"]))

    assert rank["Alice"] == 1
    assert rank["Bob"] == rank["Carl"] == 2
    assert rank["Dana"] == 4, "a min rank leaves the gap the tie consumed"


def test_gated_board_withholds_a_rank_at_the_score_floor():
    """Career Skill Mass zero means "no year above the bar", not "lowest rated".

    Every fighter on that floor is tied, so ranking them 116..400 published an
    ordering that measured nothing. They are withheld with a stated reason.
    """
    current = pd.DataFrame(
        {
            "fighter": ["Alice", "Bob", "Carl", "Dana"],
            "rating_periods": [20, 20, 20, 2],
            "symon_career_skill_mass": [180.0, 0.0, 0.0, 0.0],
        }
    )
    gated = completeness_gated_board(
        current,
        rating_col="symon_career_skill_mass",
        min_rating_periods=5,
        unranked_at_or_below=0.0,
    )
    status = dict(zip(gated["fighter"], gated["status"]))
    rank = dict(zip(gated["fighter"], gated["rank"]))

    assert status["Alice"] == "ranked" and rank["Alice"] == 1
    assert status["Bob"] == status["Carl"] == UNRANKED_AT_FLOOR_STATUS
    assert pd.isna(rank["Bob"]) and pd.isna(rank["Carl"])
    # The evidence gate still takes precedence over the floor reason.
    assert status["Dana"].startswith("insufficient observed history")

    # Without the floor the board keeps its old behaviour for scores that have
    # no such floor, and the tied zeros share one place rather than vanishing.
    ungated = completeness_gated_board(
        current, rating_col="symon_career_skill_mass", min_rating_periods=5
    )
    tied = ungated[ungated["fighter"].isin(["Bob", "Carl"])]["rank"]
    assert tied.nunique() == 1


def test_integrity_rank_change_is_zero_when_nothing_was_debited():
    """rank_change compared a positional rank to a min rank, so ties drifted."""
    current = pd.DataFrame(
        {
            "fighter": ["Alice", "Bob", "Carl"],
            "rating_periods": [20, 20, 20],
            "mu_whr": [1700.0, 1600.0, 1600.0],
        }
    )
    empty_ledger = pd.DataFrame(columns=["fighter", "reason"])
    board = integrity_discounted_board(current, empty_ledger, rating_col="mu_whr")

    assert (board["integrity_cost"] == 0).all()
    assert (board["rank_change"] == 0).all(), "no debit must cost nobody a place"
    assert sorted(board["rank"]) == [1, 2, 2]
