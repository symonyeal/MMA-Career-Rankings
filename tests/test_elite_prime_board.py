"""The elite-tested Prime board: a floor on proven record, not on volume."""
from __future__ import annotations

import pathlib

import pandas as pd
import pytest

from ratings import boards

import build_boards
from ratings.boards import completeness_gated_board
from ratings.opponent_quality import (
    best_elite_decade,
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
    assert build_boards._elite_decade_map(tmp_path) is None


def test_quality_wins_are_unique_and_inside_the_selected_prime_window(tmp_path):
    """The decade holds every win it contains, and event joins cannot fan out."""
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

    decade = build_boards._elite_decade_map(tmp_path)

    assert decade is not None
    row = decade.set_index("fighter").loc["Window Fighter"]
    # All five wins fall inside one decade, and the duplicated same-event
    # rating row must not make bout-0 count twice.
    assert row["elite_wins"] == 5
    assert row["elite_window_start"] == inside_dates.min()
    assert row["elite_window_end"] == later_dates.max()


# --- Ordering: elite-win mass, not the bare level ---

def _mass(levels: dict[str, float], wins: dict[str, int], *, anchor: float):
    return boards.elite_win_mass(
        pd.Series(levels), pd.Series(wins), anchor=anchor
    ).sort_values(ascending=False)


FLOOR = 1784.6


def test_more_elite_wins_outrank_a_slightly_higher_level():
    """The first reported defect, with the numbers that produced it.

    Topuria held a higher Prime level than St-Pierre on 5 qualifying wins
    against 11, and the board ranked the bare level, so he placed above him.
    """
    order = _mass({"Topuria": 2111.7, "St-Pierre": 2073.3},
                  {"Topuria": 5, "St-Pierre": 11}, anchor=FLOOR)
    assert list(order.index) == ["St-Pierre", "Topuria"]


def test_volume_outweighs_a_higher_level_by_a_clear_margin():
    """The second: Silva's 11 wins must beat Nemkov's 5, not merely tie.

    Shrinking the level by evidence saturates, so no usable strength separated
    these two -- at k=20 they finished 1.2 points apart. The product does.
    """
    order = _mass({"Silva": 1925.1, "Nemkov": 2027.5},
                  {"Silva": 11, "Nemkov": 5}, anchor=FLOOR)
    assert list(order.index) == ["Silva", "Nemkov"]
    assert order["Silva"] > order["Nemkov"] * 1.2


def test_nine_tested_wins_outrank_six_at_a_similar_level():
    """Strickland over Anthony Johnson."""
    order = _mass({"Strickland": 1917.6, "Johnson": 1938.7},
                  {"Strickland": 9, "Johnson": 6}, anchor=FLOOR)
    assert list(order.index) == ["Strickland", "Johnson"]


def test_volume_cannot_overturn_a_large_level_gap():
    """It is a product, not a win count: Jones keeps first on 12 over 11."""
    order = _mass({"Jones": 2207.8, "St-Pierre": 2073.3},
                  {"Jones": 12, "St-Pierre": 11}, anchor=FLOOR)
    assert list(order.index) == ["Jones", "St-Pierre"]


def test_the_result_is_monotone_in_both_level_and_evidence():
    """No fighter may outrank another better on level AND evidence."""
    levels = {"weak_thin": 1900.0, "weak_thick": 1910.0,
              "strong_thin": 2100.0, "strong_thick": 2110.0}
    wins = {"weak_thin": 5, "weak_thick": 12, "strong_thin": 5, "strong_thick": 12}
    ranked = list(_mass(levels, wins, anchor=1850.0).index)
    for better in ("weak_thick", "strong_thick"):
        assert ranked.index(better) < ranked.index(better.replace("thick", "thin"))


def test_a_level_at_the_anchor_earns_nothing_however_many_wins():
    """The anchor is the qualifying floor; distance above it is what is credited."""
    got = boards.elite_win_mass(
        pd.Series({"A": 1784.6, "B": 1784.6}), pd.Series({"A": 5, "B": 50}),
        anchor=1784.6,
    )
    assert got["A"] == got["B"] == pytest.approx(0.0)


def test_the_published_board_has_no_dominated_pairs():
    """Property check on the real artifact, if the snapshot is present."""
    path = pathlib.Path("data/snapshots/2026-08-13/prime_elite_board.parquet")
    if not path.exists():
        pytest.skip("snapshot artifact not present")
    board = pd.read_parquet(path)
    ok = board[board["status"].eq("ranked")].sort_values("rank").reset_index(drop=True)
    level, wins = ok["elite_level"], ok["tested_opponent_wins"]
    for i in range(len(ok)):
        for j in range(i + 1, len(ok)):
            assert not (level[j] > level[i] and wins[j] >= wins[i]), (
                f"{ok.loc[i, 'fighter']} ranked above {ok.loc[j, 'fighter']}, "
                "who is better on both level and evidence"
            )


# --- Making the contender line legible on the published boards ---

def _snapshot_with_history(tmp_path):
    snap = tmp_path / "snap"
    snap.mkdir()
    pd.DataFrame({
        "fighter": ["A", "A", "A", "B", "B"],
        "event_date": pd.to_datetime(
            ["2020-01-01", "2021-01-01", "2022-01-01", "2020-01-01", "2021-01-01"]
        ),
        "mu_whr": [1700.0, 1900.0, 1800.0, 1600.0, 1650.0],
    }).to_parquet(snap / "ratings_history_whr.parquet", index=False)
    return snap


def test_peak_levels_take_the_highest_point_not_the_last(tmp_path):
    """A declined fighter's peak is what puts them on the contender scale."""
    peaks = build_boards.peak_levels(_snapshot_with_history(tmp_path))

    assert peaks["A"] == 1900.0   # not 1800, their final rating
    assert peaks["B"] == 1650.0


def test_missing_history_yields_no_peaks_rather_than_raising(tmp_path):
    assert build_boards.peak_levels(tmp_path).empty


def test_contender_line_reach_is_measured_over_established_fighters(tmp_path):
    """The published share must not be a hand-typed number that goes stale."""
    snap = _snapshot_with_history(tmp_path)
    current = pd.DataFrame({
        "fighter": ["A", "B", "C"],
        "rating_periods": [20, 20, 2],   # C is below the evidence floor
    })

    reach = build_boards.contender_line_reach(snap, current)

    # A peaked above the line, B did not, C is not established.
    assert reach == pytest.approx(0.5)


def test_the_published_board_prints_the_peak_on_the_contender_scale():
    """The score is a resume figure; the peak is what the line can be read against."""
    gated = pd.DataFrame({
        "rank": [1], "fighter": ["A"], "status": ["ranked"],
        "symon_prime_score": [2000.0],
    })
    current = pd.DataFrame({"fighter": ["A"], "peak_mu_whr": [1900.4]})

    table = build_boards.top_board_markdown(
        gated, current, rating_col="symon_prime_score", top=1
    )

    assert "Peak" in table.splitlines()[0]
    assert "1900" in table


# --- The window must be chosen by wins, not by the quietest rating stretch ---

def _wins(dates: list[str], fighter: str = "A") -> pd.DataFrame:
    return pd.DataFrame({"fighter": fighter, "event_date": pd.to_datetime(dates)})


def _history(pairs: list[tuple[str, float]], fighter: str = "A") -> pd.DataFrame:
    return pd.DataFrame({
        "fighter": fighter,
        "event_date": pd.to_datetime([d for d, _ in pairs]),
        "mu_whr": [m for _, m in pairs],
    })


def test_the_window_follows_the_wins_not_the_highest_rated_stretch():
    """Cormier's defect: an undefeated early run outscored his real prime.

    Choosing the window by mean rating picks the stretch with the fewest
    losses, because an undefeated record is rated above everyone in it. That
    made his 13-0 Strikeforce years his 'prime' and left his UFC title reign
    outside it, counting 2 qualifying wins where he has 8.
    """
    wins = _wins(["2015-01-01", "2016-01-01", "2017-01-01"])
    history = _history([
        ("2010-01-01", 2200.0), ("2011-01-01", 2200.0),   # quiet, unbeaten, no wins
        ("2015-01-01", 2000.0), ("2016-01-01", 2000.0), ("2017-01-01", 2000.0),
    ])

    got = best_elite_decade(wins, history).set_index("fighter")

    assert got.loc["A", "elite_wins"] == 3
    assert got.loc["A", "elite_window_start"] == pd.Timestamp("2015-01-01")
    assert got.loc["A", "elite_level"] == pytest.approx(2000.0)


def test_the_level_is_read_from_the_same_window_as_the_wins():
    """No leakage in either direction: one window supplies both numbers."""
    wins = _wins(["2022-01-01", "2023-01-01"])
    history = _history([
        ("2015-01-01", 1500.0),   # long before the elite stretch
        ("2022-01-01", 2100.0), ("2023-01-01", 2100.0),
    ])

    got = best_elite_decade(wins, history).set_index("fighter")

    assert got.loc["A", "elite_level"] == pytest.approx(2100.0)


def test_wins_further_apart_than_the_span_do_not_share_a_window():
    wins = _wins(["2000-01-01", "2001-01-01", "2020-01-01"])
    history = _history([("2000-01-01", 1900.0), ("2001-01-01", 1900.0),
                        ("2020-01-01", 1900.0)])

    got = best_elite_decade(wins, history).set_index("fighter")

    assert got.loc["A", "elite_wins"] == 2


def test_a_tie_on_count_goes_to_the_stronger_stretch():
    wins = _wins(["2000-01-01", "2020-01-01"])
    history = _history([("2000-01-01", 1800.0), ("2020-01-01", 2000.0)])

    got = best_elite_decade(wins, history).set_index("fighter")

    assert got.loc["A", "elite_wins"] == 1
    assert got.loc["A", "elite_level"] == pytest.approx(2000.0)


def test_no_qualifying_wins_yields_no_window():
    assert best_elite_decade(pd.DataFrame(columns=["fighter", "event_date"]),
                             _history([("2000-01-01", 1900.0)])).empty
