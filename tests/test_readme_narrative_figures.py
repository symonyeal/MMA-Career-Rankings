"""Pin the README's hand-typed figures to the snapshot they describe.

The generated tables cannot drift -- ``build_boards.py`` rewrites them between
markers and refuses a partial update. The prose around them can, and did: on
2026-09-03 the overview quoted resume scores of 1,170 and 1,000 against actual
values of 1,139 and 1,009, and said 70 men qualified for a board 65 had
qualified for.

The 2026-09-03 rewrite replaced the long comparative narrative with the
principles it was illustrating, so the assertions that pinned that narrative
went with it. What is here covers every quantity the overview still states.
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


def _loose(name: str) -> str:
    """A name pattern that survives the README's line wrapping."""
    return r"\s+".join(re.escape(part) for part in name.split())


def test_the_stated_prime_qualifier_counts_match_the_boards():
    text = _readme()
    men = re.search(r"(\d+) men qualify", text)
    assert men, "README no longer states how many men qualify for the Prime board"
    assert int(men.group(1)) == len(_ranked("prime_elite_board.parquet"))

    women = re.search(r"Only (\d+) wom(?:a|e)n do(?:es)?", text)
    assert women, "README no longer states how many women qualify"
    assert int(women.group(1)) == len(_ranked("prime_elite_board_women.parquet"))


def test_the_career_coverage_figures_match_the_coverage_ledger():
    from loaders.career_coverage import coverage_summary

    summary = coverage_summary(_require(SNAPSHOT / "career_coverage.parquet"))
    match = re.search(
        r"held for ([\d,]+) of the\s+([\d,]+)\s+fighters this can affect", _readme()
    )
    assert match, "README no longer states the career-coverage figures"
    assert int(match.group(1).replace(",", "")) == summary["whole_career_merged"]
    assert int(match.group(2).replace(",", "")) == summary["eligible"]


def test_the_recency_bar_examples_last_fought_when_the_readme_says():
    """The overview names the two fighters the 18-month bar withholds.

    Both the dates and the exclusion are checkable, and both are the reason the
    paragraph is persuasive, so both are held here.
    """
    fights = _require(SNAPSHOT / "combined_fights.parquet")
    fights = fights[fights["is_model_bout"].astype(bool)]
    ranked = set(_ranked("current_board.parquet")["fighter"])
    text = _readme()

    for fighter in ("Jon Jones", "Shavkat Rakhmonov"):
        found = re.search(rf"{_loose(fighter)}[^.]*?(\d{{4}}-\d{{2}}-\d{{2}})", text)
        assert found, f"README no longer dates {fighter}'s last bout"
        rows = fights[
            fights["fighter_a"].eq(fighter) | fights["fighter_b"].eq(fighter)
        ]
        last = pd.to_datetime(rows["event_date"]).max().strftime("%Y-%m-%d")
        assert found.group(1) == last, (
            f"README says {fighter} last fought {found.group(1)}; "
            f"the snapshot says {last}"
        )
        assert fighter not in ranked, (
            f"README cites {fighter} as withheld, but the board ranks them"
        )
