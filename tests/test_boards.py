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
            "public_legacy_score": [25.0, 35.0, 45.0],
            "symon_career_skill_mass": [20.0, 30.0, 40.0],
            "mu_whr": [1600.0, 1550.0, 1700.0],
            "sustained_peak_headline_mu_whr_integrity_performance": [9000.0, 8000.0, 7000.0],
        }
    )


def test_board_score_selection_is_lean_and_has_safe_fallbacks():
    current = _current()
    assert build_boards.select_core_rating_col(current) == "public_legacy_score"
    assert build_boards.select_integrity_rating_col(current) == "mu_whr"

    without_legacy = current.drop(columns="public_legacy_score")
    assert build_boards.select_core_rating_col(without_legacy) == "symon_career_skill_mass"

    without_symon = current.drop(columns="symon_career_skill_mass")
    assert build_boards.select_core_rating_col(without_symon) == "public_legacy_score"

    without_legacy_or_symon = current.drop(
        columns=["public_legacy_score", "symon_career_skill_mass"]
    )
    assert build_boards.select_core_rating_col(without_legacy_or_symon) == "mu_whr"

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

    assert summary["core_rating_col"] == "public_legacy_score"
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
            "public_legacy_score": [180.0, 0.0, 0.0, 0.0],
        }
    )
    gated = completeness_gated_board(
        current,
        rating_col="public_legacy_score",
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
        current, rating_col="public_legacy_score", min_rating_periods=5
    )
    tied = ungated[ungated["fighter"].isin(["Bob", "Carl"])]["rank"]
    assert tied.nunique() == 1


def test_public_legacy_title_resume_can_override_generic_period_floor():
    current = pd.DataFrame(
        {
            "fighter": ["Champion", "Prospect"],
            "rating_periods": [10, 10],
            "public_legacy_score": [1000.0, 1100.0],
            "public_legacy_title_wins": [3, 0],
            "public_legacy_title_defenses": [1, 0],
            "public_legacy_ufc_bouts": [10, 10],
        }
    )
    override = build_boards.public_legacy_eligibility_override(current)
    gated = completeness_gated_board(
        current,
        rating_col="public_legacy_score",
        min_rating_periods=13,
        eligibility_override=override,
    )
    status = dict(zip(gated["fighter"], gated["status"]))

    assert status["Champion"] == "ranked"
    assert status["Prospect"].startswith("insufficient observed history")


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


def _published_board() -> tuple[pd.DataFrame, pd.DataFrame]:
    gated = pd.DataFrame(
        {
            "rank": [1.0, 2.0, 3.0],
            "fighter": ["Alice", "Bob", "Carl"],
            # 1000 + 500 + 1000, 500 + 1000 + 0, 100 + 0 + 200 (see below).
            "public_legacy_score": [2500.0, 1500.0, 300.0],
            "status": ["ranked", "ranked", "insufficient observed history"],
            "rating_periods": [26, 20, 2],
        }
    )
    current = pd.DataFrame(
        {
            "fighter": ["Alice", "Bob", "Carl"],
            "public_legacy_skill_score": [40.0, 20.0, 4.0],
            "public_legacy_title_score": [8.0, 16.0, 0.0],
            "public_legacy_resume_score": [50.0, 0.0, 10.0],
        }
    )
    return gated, current


def test_published_table_prints_the_level_and_the_evidence_not_components():
    """Every board prints the same two figures beside the score.

    The three normalised component columns were retired: they restated the
    score they add up to, and said nothing a reader could check the contender
    line against.
    """
    gated, current = _published_board()
    current = current.assign(elite_level=[2100.0, 1950.0, 1800.0][: len(current)],
                             elite_wins=[9, 6, 4][: len(current)])
    table = build_boards.top_board_markdown(
        gated, current, rating_col="public_legacy_score", top=100
    )
    lines = table.splitlines()

    assert lines[0] == "| # | Fighter | Score | Prime | Elite wins |"
    for retired in ("Skill", "Title", "Schedule"):
        assert f"| {retired} " not in lines[0]
    # Carl is withheld by the completeness gate and must not be published.
    assert len(lines) == 4
    assert "Carl" not in table

    alice = [cell.strip() for cell in lines[2].split("|")[1:-1]]
    assert alice[:2] == ["1", "Alice"]
    assert alice[3] == "2100"
    assert alice[4] == "9"


def test_a_fighter_with_no_elite_decade_prints_an_empty_cell():
    """A gap must stay a gap, not become a zero or turn the column into floats."""
    gated, current = _published_board()
    current = current.assign(elite_level=float("nan"), elite_wins=float("nan"))

    table = build_boards.top_board_markdown(
        gated, current, rating_col="public_legacy_score", top=100
    )

    assert "|  |  |" in table.splitlines()[2]


def test_published_table_honours_the_row_limit_and_needs_ranked_rows():
    gated, current = _published_board()
    table = build_boards.top_board_markdown(
        gated, current, rating_col="public_legacy_score", top=1
    )
    assert len(table.splitlines()) == 3
    assert "Bob" not in table

    withheld = gated.assign(status="insufficient observed history")
    with pytest.raises(ValueError, match="no ranked fighters"):
        build_boards.top_board_markdown(
            withheld, current, rating_col="public_legacy_score", top=100
        )


def test_all_time_table_prints_the_prime_board_position():
    """The all-time board carries where each fighter sits on the Prime board.

    The position comes from the published elite-tested board, so it is not
    monotone in the Prime level printed beside it: that board orders elite-win
    mass, and the level is a rate.
    """
    gated, current = _published_board()
    current = current.assign(
        elite_level=[2100.0, 1950.0, 1800.0][: len(current)],
        elite_wins=[9, 6, 4][: len(current)],
    )
    table = build_boards.top_board_markdown(
        gated,
        current,
        rating_col="public_legacy_score",
        top=100,
        # Bob cleared the all-time gate but not the elite-tested evidence floor.
        prime_ranks=pd.Series({"Alice": 7}),
    )
    lines = table.splitlines()

    assert lines[0] == "| # | Fighter | Score | Prime | Prime rank | Elite wins |"
    alice = [cell.strip() for cell in lines[2].split("|")[1:-1]]
    bob = [cell.strip() for cell in lines[3].split("|")[1:-1]]
    assert alice[3:] == ["2100", "7", "9"]
    # Withheld from the Prime board is an abstention, not rank zero or last.
    assert bob[4] == ""


def test_board_rank_map_reads_only_ranked_rows(tmp_path: Path):
    path = tmp_path / "prime_elite_board.parquet"
    pd.DataFrame(
        {
            "fighter": ["Ranked", "Withheld"],
            "rank": [3, pd.NA],
            "status": ["ranked", "insufficient observed history"],
        }
    ).to_parquet(path, index=False)

    positions = build_boards.board_rank_map(path)

    assert positions.to_dict() == {"Ranked": 3}
    assert build_boards.board_rank_map(tmp_path / "absent.parquet").empty


def test_elite_prime_table_publishes_the_evidence_count():
    gated = pd.DataFrame(
        {
            "rank": [1],
            "fighter": ["Proven Fighter"],
            "elite_prime_score": [1234.0],
            "status": ["ranked"],
            "elite_level": [2050.0],
            "elite_wins": [6],
        }
    )

    table = build_boards.top_board_markdown(
        gated,
        pd.DataFrame({"fighter": ["Proven Fighter"]}),
        rating_col=build_boards.ELITE_PRIME_RATING_COL,
        top=50,
    )

    # The mass the board is ordered by is not printed: its unit is rating points
    # times wins, which reads against nothing.
    assert table.splitlines()[0] == "| # | Fighter | Prime | Elite wins |"
    assert "| 1 | Proven Fighter | 2050 | 6 |" in table


def test_readme_board_block_is_replaced_in_place(tmp_path: Path):
    readme = tmp_path / "README.md"
    readme.write_text(
        "# Engine\n\n"
        f"{build_boards.README_BOARD_BEGIN}\n\nstale table\n\n"
        f"{build_boards.README_BOARD_END}\n\n## Next section\n",
        encoding="utf-8",
    )

    build_boards.update_publication_files(
        ((readme, ((build_boards.README_BOARD_BEGIN,
                    build_boards.README_BOARD_END,
                    "| # |\n| ---: |\n| 1 |"),)),)
    )
    text = readme.read_text(encoding="utf-8")

    assert "stale table" not in text
    assert "| 1 |" in text
    assert text.startswith("# Engine\n")
    assert text.endswith("## Next section\n"), "content after the block must survive"
    assert text.count(build_boards.README_BOARD_BEGIN) == 1


def test_readme_board_block_refuses_a_file_without_markers(tmp_path: Path):
    readme = tmp_path / "README.md"
    readme.write_text("# Engine\n\nno markers here\n", encoding="utf-8")

    with pytest.raises(ValueError, match="exactly one board block"):
        build_boards.update_publication_files(
            ((readme, ((build_boards.README_BOARD_BEGIN,
                        build_boards.README_BOARD_END,
                        "| # |"),)),)
        )
    assert readme.read_text(encoding="utf-8") == "# Engine\n\nno markers here\n"


# ---------------------------------------------------------------------------
# Separate men's and women's boards (2026-08-28)
#
# Men and women are disjoint components of the bout graph -- 0 of 80,697 rated
# bouts and 0 shared opponents join them -- so the offset between their rating
# levels is set by the prior, not by evidence. A mixed board publishes that
# unidentified gauge as a rank.


def _gendered_current() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "fighter": ["Ada", "Bea", "Cal", "Dan", "Eve"],
            "gender": ["F", "F", "M", "M", None],
            "rating_periods": [4, 4, 4, 4, 4],
            "public_legacy_score": [90.0, 70.0, 80.0, 60.0, 50.0],
            "symon_prime_score": [1900.0, 1800.0, 1850.0, 1750.0, 1700.0],
            "mu_whr": [1700.0, 1650.0, 1680.0, 1600.0, 1590.0],
        }
    )


def test_gender_partition_splits_the_two_components_and_keeps_the_unlabelled():
    parts = build_boards.gender_partition(_gendered_current())
    assert parts["F"]["fighter"].tolist() == ["Ada", "Bea"]
    # An unlabelled fighter stays on the default board rather than being
    # asserted into the women's one.
    assert parts["M"]["fighter"].tolist() == ["Cal", "Dan", "Eve"]


def test_gender_partition_falls_back_to_one_board_without_a_gender_column():
    current = _gendered_current().drop(columns="gender")
    parts = build_boards.gender_partition(current)
    assert set(parts) == {"M"}
    assert len(parts["M"]) == 5


def test_boards_rank_within_gender_and_publish_all_time_and_prime_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    snapshot = tmp_path / "snapshot"
    output = tmp_path / "boards"
    snapshot.mkdir()
    _gendered_current().to_parquet(snapshot / "ratings_current.parquet", index=False)
    pd.DataFrame(
        {
            "fight_url": ["u/1"],
            "fighter": ["Ada"],
            "integrity_factor_ped": [1.0],
            "integrity_factor_dq": [1.0],
            "integrity_factor_missed_weight": [1.0],
            "integrity_weight": [1.0],
        }
    ).to_parquet(snapshot / "integrity_appearances.parquet", index=False)
    monkeypatch.setattr(
        build_boards.PQ,
        "load_fight_table",
        lambda _snapshot, *, scope: pd.DataFrame(
            {
                "fight_url": ["u/1"],
                "event_date": [pd.Timestamp("2024-01-01")],
                "event_name": ["E"],
                "fighter_a": ["Ada"],
                "fighter_b": ["Bea"],
                "winner": ["Ada"],
            }
        ),
    )

    summary = build_boards.write_board_artifacts(
        snapshot, min_rating_periods=2, out_dir=output
    )
    assert summary["genders"] == ["F", "M"]
    assert summary["ranked_by_gender"] == {"F": 2, "M": 3}

    men = pd.read_parquet(output / "completeness_gated_board.parquet")
    women = pd.read_parquet(output / "completeness_gated_board_women.parquet")
    prime_men = pd.read_parquet(output / "prime_board.parquet")
    prime_women = pd.read_parquet(output / "prime_board_women.parquet")

    # No woman appears on the published default board, and vice versa.
    assert set(men["fighter"]) == {"Cal", "Dan", "Eve"}
    assert set(women["fighter"]) == {"Ada", "Bea"}
    # Each board's ranks start at 1: Ada outranks Bea among women even though
    # Cal sits between them on the mixed score.
    assert women.set_index("fighter").loc["Ada", "rank"] == 1
    assert men.set_index("fighter").loc["Cal", "rank"] == 1
    assert set(prime_men["fighter"]) == {"Cal", "Dan", "Eve"}
    assert set(prime_women["fighter"]) == {"Ada", "Bea"}
    assert summary["prime_ranked_by_gender"] == {"F": 2, "M": 3}


def test_readme_blocks_are_replaced_independently(tmp_path: Path):
    readme = tmp_path / "README.md"
    readme.write_text(
        "intro\n"
        f"{build_boards.README_BOARD_BEGIN}\nold men\n{build_boards.README_BOARD_END}\n"
        "middle\n"
        f"{build_boards.README_WOMEN_BEGIN}\nold women\n{build_boards.README_WOMEN_END}\n"
        "tail\n",
        encoding="utf-8",
    )
    build_boards.update_publication_files(
        ((readme, (
            (build_boards.README_BOARD_BEGIN,
             build_boards.README_BOARD_END,
             "| # | Fighter |"),
            (build_boards.README_WOMEN_BEGIN,
             build_boards.README_WOMEN_END,
             f"{build_boards.GENDER_GAUGE_NOTE}\n\n| # | Fighter W |"),
        )),)
    )
    text = readme.read_text(encoding="utf-8")

    assert "old men" not in text and "old women" not in text
    assert "| # | Fighter |" in text and "| # | Fighter W |" in text
    # The reason must travel with the women's block so it cannot be published
    # without the identification statement beside it.
    assert build_boards.GENDER_GAUGE_NOTE in text
    assert text.index("| # | Fighter |") < text.index("| # | Fighter W |")


def test_updating_a_missing_block_raises_rather_than_appending(tmp_path: Path):
    readme = tmp_path / "README.md"
    readme.write_text("no markers here\n", encoding="utf-8")
    with pytest.raises(ValueError, match="exactly one board block"):
        build_boards.update_publication_files(
            ((readme, ((build_boards.README_WOMEN_BEGIN,
                        build_boards.README_WOMEN_END,
                        "table"),)),)
        )


def test_multi_block_publication_validates_every_marker_before_writing(tmp_path: Path):
    readme = tmp_path / "README.md"
    original = (
        f"{build_boards.README_BOARD_BEGIN}\nold men\n"
        f"{build_boards.README_BOARD_END}\n"
        "prime marker is deliberately absent\n"
    )
    readme.write_text(original, encoding="utf-8")

    with pytest.raises(ValueError, match="exactly one board block"):
        build_boards.update_publication_files(
            ((
                readme,
                (
                    (
                        build_boards.README_BOARD_BEGIN,
                        build_boards.README_BOARD_END,
                        "new men",
                    ),
                    (
                        build_boards.README_ELITE_PRIME_BEGIN,
                        build_boards.README_ELITE_PRIME_END,
                        "new prime",
                    ),
                ),
            ),)
        )

    assert readme.read_text(encoding="utf-8") == original


def test_multi_block_publication_updates_all_four_boards_together(tmp_path: Path):
    readme = tmp_path / "RANKINGS.md"
    markers = (
        (build_boards.README_BOARD_BEGIN, build_boards.README_BOARD_END, "men"),
        (build_boards.README_WOMEN_BEGIN, build_boards.README_WOMEN_END, "women"),
        (build_boards.README_ELITE_PRIME_BEGIN, build_boards.README_ELITE_PRIME_END, "elite men"),
        (
            build_boards.README_ELITE_PRIME_WOMEN_BEGIN,
            build_boards.README_ELITE_PRIME_WOMEN_END,
            "prime women",
        ),
    )
    readme.write_text(
        "\n".join(f"{begin}\nold\n{end}" for begin, end, _ in markers) + "\n",
        encoding="utf-8",
    )

    build_boards.update_publication_files(((readme, markers),))
    text = readme.read_text(encoding="utf-8")

    assert "\nold\n" not in text
    for begin, end, body in markers:
        assert text.count(begin) == text.count(end) == 1
        assert f"{begin}\n\n{body}\n\n{end}" in text
    assert not readme.with_name(f"{readme.name}.building").exists()


def test_publication_and_overview_are_written_from_one_validated_build(tmp_path: Path):
    rankings = tmp_path / "RANKINGS.md"
    overview = tmp_path / "README.md"
    rankings.write_text(
        f"{build_boards.README_BOARD_BEGIN}\nold men\n{build_boards.README_BOARD_END}\n"
        f"{build_boards.README_ELITE_PRIME_BEGIN}\nold elite\n"
        f"{build_boards.README_ELITE_PRIME_END}\n",
        encoding="utf-8",
    )
    overview.write_text(
        f"# Overview\n\n{build_boards.README_BOARD_BEGIN}\nold men\n"
        f"{build_boards.README_BOARD_END}\n"
        f"{build_boards.README_ELITE_PRIME_BEGIN}\nold elite\n"
        f"{build_boards.README_ELITE_PRIME_END}\n",
        encoding="utf-8",
    )

    boards = (
        (build_boards.README_BOARD_BEGIN, build_boards.README_BOARD_END, "new men"),
        (
            build_boards.README_ELITE_PRIME_BEGIN,
            build_boards.README_ELITE_PRIME_END,
            "new elite",
        ),
    )
    build_boards.update_publication_files(((rankings, boards), (overview, boards)))

    for document in (rankings, overview):
        text = document.read_text(encoding="utf-8")
        assert "new men" in text and "new elite" in text
        assert "old men" not in text and "old elite" not in text
        assert not document.with_name(f"{document.name}.building").exists()
    assert "# Overview" in overview.read_text(encoding="utf-8")


def test_a_missing_overview_marker_leaves_the_publication_untouched(tmp_path: Path):
    rankings = tmp_path / "RANKINGS.md"
    overview = tmp_path / "README.md"
    original = (
        f"{build_boards.README_BOARD_BEGIN}\nold men\n{build_boards.README_BOARD_END}\n"
    )
    rankings.write_text(original, encoding="utf-8")
    overview.write_text("# Overview\n\nno markers here\n", encoding="utf-8")

    board = ((build_boards.README_BOARD_BEGIN, build_boards.README_BOARD_END, "new men"),)
    with pytest.raises(ValueError):
        build_boards.update_publication_files(((rankings, board), (overview, board)))

    assert rankings.read_text(encoding="utf-8") == original
    assert overview.read_text(encoding="utf-8") == "# Overview\n\nno markers here\n"
