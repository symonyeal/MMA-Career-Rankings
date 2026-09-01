"""The elite-tested Prime board: a floor on proven record, not on volume."""
from __future__ import annotations

import pandas as pd

import build_boards
from ratings.boards import completeness_gated_board
from ratings.opponent_quality import (
    CONTENDER_LINE_MU,
    MIN_QUALITY_WINS,
    quality_win_record,
)


def _bouts(fighter: str, opponent_mus: list[float], results: list[bool]) -> pd.DataFrame:
    return pd.DataFrame({
        "fighter": fighter,
        "opponent": [f"opp{i}" for i in range(len(opponent_mus))],
        "opponent_mu": opponent_mus,
        "is_winner": results,
    })


def test_only_opponents_above_the_contender_line_are_counted():
    below = CONTENDER_LINE_MU - 0.1
    rows = _bouts("A", [CONTENDER_LINE_MU, below, below], [True, True, True])

    record = quality_win_record(rows, min_opponent_mu=CONTENDER_LINE_MU).set_index("fighter")

    assert record.loc["A", "quality_bouts"] == 1
    assert record.loc["A", "quality_wins"] == 1


def test_a_loss_to_a_contender_is_a_bout_but_not_a_win():
    """This is what separates a contender from a durable gatekeeper.

    Ranking by opponent strength alone treated these two records as identical,
    which put fighters who lost to everyone above fighters who beat them.
    """
    beat = _bouts("Winner", [1900.0] * 5, [True] * 5)
    lost = _bouts("Gatekeeper", [1900.0] * 5, [False] * 5)
    record = quality_win_record(
        pd.concat([beat, lost]), min_opponent_mu=CONTENDER_LINE_MU
    ).set_index("fighter")

    assert record.loc["Winner", "quality_bouts"] == record.loc["Gatekeeper", "quality_bouts"] == 5
    assert record.loc["Winner", "quality_wins"] == 5
    assert record.loc["Gatekeeper", "quality_wins"] == 0


def test_one_physical_bout_cannot_be_counted_twice():
    rows = _bouts("A", [1900.0, 1900.0], [True, True]).assign(
        fight_url=["same-bout", "same-bout"]
    )

    record = quality_win_record(rows, min_opponent_mu=CONTENDER_LINE_MU).iloc[0]

    assert record["quality_bouts"] == 1
    assert record["quality_wins"] == 1


def test_volume_of_soft_wins_does_not_clear_the_floor():
    """The defect the board exists to remove: a long record nobody tested."""
    current = pd.DataFrame({
        "fighter": ["Proven", "Padded"],
        "symon_prime_score": [1800.0, 2100.0],
        "rating_periods": [14, 56],
    })
    wins = pd.Series({"Proven": MIN_QUALITY_WINS, "Padded": MIN_QUALITY_WINS - 1})

    board = completeness_gated_board(
        current,
        rating_col="symon_prime_score",
        min_rating_periods=13,
        tested_wins=wins,
        min_tested_wins=MIN_QUALITY_WINS,
    ).set_index("fighter")

    assert board.loc["Proven", "status"] == "ranked"
    assert board.loc["Proven", "rank"] == 1
    assert "proven record" in board.loc["Padded", "status"]
    assert pd.isna(board.loc["Padded", "rank"])


def test_an_unmeasured_fighter_is_withheld_not_admitted():
    """An undefeated record with no measured opponents is not a pass."""
    current = pd.DataFrame({
        "fighter": ["Unbeaten"],
        "symon_prime_score": [2200.0],
        "rating_periods": [30],
    })

    board = completeness_gated_board(
        current,
        rating_col="symon_prime_score",
        min_rating_periods=13,
        tested_wins=pd.Series(dtype=float),
        min_tested_wins=MIN_QUALITY_WINS,
    ).set_index("fighter")

    assert "proven record" in board.loc["Unbeaten", "status"]
    assert pd.isna(board.loc["Unbeaten", "tested_opponent_wins"])


def test_the_gate_does_not_reorder_the_survivors():
    """It admits and withholds; the rating alone decides where a fighter lands."""
    current = pd.DataFrame({
        "fighter": ["Low", "High"],
        "symon_prime_score": [1800.0, 1900.0],
        "rating_periods": [20, 20],
    })
    wins = pd.Series({"Low": 20, "High": MIN_QUALITY_WINS})

    board = completeness_gated_board(
        current,
        rating_col="symon_prime_score",
        min_rating_periods=13,
        tested_wins=wins,
        min_tested_wins=MIN_QUALITY_WINS,
    ).set_index("fighter")

    assert board.loc["High", "rank"] == 1
    assert board.loc["Low", "rank"] == 2


def test_the_gate_is_off_by_default():
    """Every existing caller keeps the previous board exactly."""
    current = pd.DataFrame({
        "fighter": ["A"],
        "symon_prime_score": [1900.0],
        "rating_periods": [30],
    })

    board = completeness_gated_board(
        current, rating_col="symon_prime_score", min_rating_periods=13
    )

    assert board.loc[0, "status"] == "ranked"
    assert "tested_opponent_wins" not in board.columns


def test_a_snapshot_without_the_inputs_publishes_no_elite_board(tmp_path):
    """No inputs means no gate, not a board that withholds everyone."""
    assert build_boards._quality_win_map(tmp_path) is None


def test_quality_wins_are_unique_and_inside_the_selected_prime_window(tmp_path):
    """Later wins cannot certify an earlier peak, and event joins cannot fan out."""
    inside_dates = pd.date_range("2020-01-01", periods=3, freq="180D")
    later_dates = pd.date_range("2023-01-01", periods=2, freq="180D")
    opponents = [f"Contender {number}" for number in range(5)]
    appearances = pd.DataFrame(
        {
            "fight_url": [f"bout-{number}" for number in range(5)],
            "fighter": "Window Fighter",
            "opponent": opponents,
            "event_date": [*inside_dates, *later_dates],
            "event_name": [f"Event {number}" for number in range(5)],
            "is_winner": True,
        }
    )
    appearances.to_parquet(tmp_path / "performance_appearances.parquet", index=False)

    history = appearances[["opponent", "event_date", "event_name"]].rename(
        columns={"opponent": "fighter"}
    )
    history["mu_whr"] = CONTENDER_LINE_MU + 100.0
    # A same-event tournament state used to duplicate bout-0 in the merge.
    history = pd.concat([history, history.iloc[[0]]], ignore_index=True)
    history.to_parquet(tmp_path / "ratings_history_whr.parquet", index=False)

    ufc_rows = []
    for opponent in opponents:
        for bout_number in range(8):
            ufc_rows.append(
                {
                    "fighter_a": opponent,
                    "fighter_b": f"Test opponent {opponent} {bout_number}",
                    "source_corpus": "ufc",
                    "is_model_bout": True,
                }
            )
    pd.DataFrame(ufc_rows).to_parquet(tmp_path / "combined_fights.parquet", index=False)

    windows = pd.DataFrame(
        {
            "fighter": ["Window Fighter"],
            "symon_prime_window_start": [inside_dates.min()],
            "symon_prime_window_end": [inside_dates.max()],
        }
    )
    wins = build_boards._quality_win_map(tmp_path, windows)

    assert wins is not None
    assert wins.loc["Window Fighter"] == 3

    current = windows.assign(symon_prime_score=2100.0, rating_periods=13)
    board = completeness_gated_board(
        current,
        rating_col="symon_prime_score",
        min_rating_periods=13,
        tested_wins=wins,
        min_tested_wins=MIN_QUALITY_WINS,
    ).set_index("fighter")
    assert "proven record" in board.loc["Window Fighter", "status"]
    assert pd.isna(board.loc["Window Fighter", "rank"])
