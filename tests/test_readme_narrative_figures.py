"""Pin the README's hand-typed figures to the snapshot they describe.

The generated tables cannot drift -- ``build_boards.py`` rewrites them between
markers and refuses a partial update. The prose around them can, and did: on
2026-09-03 the overview still called Demetrious Johnson 6th when the rebuilt
board had him 7th, quoted resume scores of 1,170 and 1,000 against actual values
of 1,139 and 1,009, an exposure factor of 0.904 against 0.897, and said 70 men
qualified for a board 72 had qualified for. Every one of those numbers is
readable from the snapshot, so a test can hold them to it.

These assertions are deliberately about figures a reader would check. Narrative
about *why* a fighter places where they do is not pinned here -- only the
quantities the narrative asserts.
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = PROJECT_ROOT / "data" / "snapshots" / "2026-08-13"
README = PROJECT_ROOT / "README.md"


def _readme() -> str:
    return README.read_text(encoding="utf-8")


def _require(path: Path) -> pd.DataFrame:
    if not path.exists():
        pytest.skip(f"snapshot artifact not present: {path.name}")
    return pd.read_parquet(path)


def _ranked(name: str) -> pd.DataFrame:
    board = _require(SNAPSHOT / name)
    return board[board["status"].eq("ranked")]


def test_the_narrative_board_positions_match_the_published_board():
    ranks = _ranked("completeness_gated_board.parquet").set_index("fighter")["rank"]
    text = _readme()
    for fighter, ordinal in (("Demetrious Johnson", "7th"), ("Fedor Emelianenko", "23rd")):
        expected = int(ranks[fighter])
        assert f"{fighter} is {ordinal}" in text or f"{fighter} {ordinal}" in text, (
            f"README no longer states a position for {fighter}"
        )
        assert ordinal.rstrip("stnrdh") == str(expected), (
            f"README calls {fighter} {ordinal}; the published board has {expected}"
        )


def test_the_narrative_component_scores_match_the_snapshot():
    current = _require(SNAPSHOT / "ratings_current.parquet").set_index("fighter")
    text = _readme()
    dj, fedor = current.loc["Demetrious Johnson"], current.loc["Fedor Emelianenko"]

    title = re.search(r"which scores ([\d,]+) against ([\d,]+)", text)
    assert title, "README no longer quotes the two title scores"
    assert [int(v.replace(",", "")) for v in title.groups()] == [
        round(dj["public_legacy_title_score"]),
        round(fedor["public_legacy_title_score"]),
    ]

    resume = re.search(r"contender wins to \d+, scoring ([\d,]+) against ([\d,]+)", text)
    assert resume, "README no longer quotes the two resume scores"
    assert [int(v.replace(",", "")) for v in resume.groups()] == [
        round(dj["public_legacy_resume_score"]),
        round(fedor["public_legacy_resume_score"]),
    ]

    exposure = re.search(r"exposure factor is ([\d.]+) against\s+Johnson's ([\d.]+)", text)
    assert exposure, "README no longer quotes the two exposure factors"
    assert [float(v) for v in exposure.groups()] == [
        pytest.approx(fedor["public_legacy_exposure_factor"], abs=5e-4),
        pytest.approx(dj["public_legacy_exposure_factor"], abs=5e-4),
    ]


def test_the_stated_prime_qualifier_counts_match_the_boards():
    text = _readme()
    men = re.search(r"(\d+) men qualify", text)
    assert men, "README no longer states how many men qualify for the Prime board"
    assert int(men.group(1)) == len(_ranked("prime_elite_board.parquet"))

    women = re.search(r"Only (\d+) women do", text)
    assert women, "README no longer states how many women qualify"
    assert int(women.group(1)) == len(_ranked("prime_elite_board_women.parquet"))


def _top100_prime_column() -> dict[str, int]:
    """Fighter -> the Prime figure printed in the README's own top-100 table."""
    text = _readme()
    begin = text.index("<!-- BOARD:TOP100:BEGIN -->")
    block = text[begin : text.index("<!-- BOARD:TOP100:END -->", begin)]
    out: dict[str, int] = {}
    for line in block.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 4 or not cells[0].isdigit():
            continue
        if cells[3].isdigit():
            out[cells[1]] = int(cells[3])
    return out


def test_levels_quoted_beside_the_contender_line_match_the_table_they_cite():
    """The Prime column is a best-decade level, not a career peak.

    The overview used to say a fighter "peaked at" the figure it prints, which
    is a different quantity: Anthony Pettis reads 1,759 there and peaked at
    1,882. The paragraph tells the reader to look at the top-100 table above, so
    that table is what the four quoted figures are checked against -- which also
    catches naming a fighter who is not on it, as Frank Mir was.
    """
    from ratings.opponent_quality import CONTENDER_LINE_MU

    printed = _top100_prime_column()
    assert printed, "the README top-100 table has no readable Prime column"
    text = _readme()

    over = re.search(
        r"([\w' .-]+?) rates ([\d,]+) and ([\w' .-]+?)\s+([\d,]+), both just\s+over the line",
        text,
    )
    assert over, "README no longer names the two fighters just over the contender line"
    under = re.search(
        r"over the line; ([\w' .-]+?) at ([\d,]+) and ([\w' .-]+?) at ([\d,]+)\s+sit just under it",
        text,
    )
    assert under, "README no longer names the two fighters just under the contender line"

    for name, value, side in (
        (over.group(1).strip(), over.group(2), "over"),
        (over.group(3).strip(), over.group(4), "over"),
        (under.group(1).strip(), under.group(2), "under"),
        (under.group(3).strip(), under.group(4), "under"),
    ):
        quoted = int(value.replace(",", ""))
        assert name in printed, f"README reads {name} off the top-100 table, but they are not on it"
        assert printed[name] == quoted, (
            f"README gives {name} a Prime level of {quoted}; the table prints {printed[name]}"
        )
        if side == "over":
            assert quoted >= CONTENDER_LINE_MU
        else:
            assert quoted < CONTENDER_LINE_MU


def test_the_career_coverage_figures_match_the_coverage_ledger():
    from loaders.career_coverage import coverage_summary

    summary = coverage_summary(_require(SNAPSHOT / "career_coverage.parquet"))
    text = _readme()
    match = re.search(r"held for ([\d,]+) of the\s+([\d,]+) fighters this can affect", text)
    assert match, "README no longer states the career-coverage figures"
    assert int(match.group(1).replace(",", "")) == summary["whole_career_merged"]
    assert int(match.group(2).replace(",", "")) == summary["eligible"]
