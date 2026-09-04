from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote

from ratings.constants import (
    INTEGRITY_DQ_WIN_FACTOR,
    INTEGRITY_MISSED_WEIGHT_WIN_FACTOR,
    INTEGRITY_PED_FACTOR,
)
from ratings.gender import GENDER_GAUGE_NOTE


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CURRENT_DOCS = [
    PROJECT_ROOT / "README.md",
    PROJECT_ROOT / "RANKINGS.md",
    PROJECT_ROOT / "data" / "SOURCE_MATRIX.md",
    PROJECT_ROOT / "data" / "CHANGELOG.md",
    *sorted((PROJECT_ROOT / "docs").glob("*.md")),
]
MARKDOWN_LINK = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")


def test_current_markdown_links_resolve_locally():
    broken: list[str] = []
    for document in CURRENT_DOCS:
        for raw_target in MARKDOWN_LINK.findall(document.read_text(encoding="utf-8")):
            target = raw_target.split("#", 1)[0].strip().strip("<>")
            if not target or "://" in target or target.startswith("mailto:"):
                continue
            resolved = (document.parent / unquote(target)).resolve()
            if not resolved.exists():
                broken.append(f"{document.relative_to(PROJECT_ROOT)} -> {raw_target}")
    assert not broken, "broken current-document links:\n" + "\n".join(broken)


PUBLICATION_MARKERS = (
    "PUBLICATION:RELEASE",
    "BOARD:TOP100",
    "BOARD:WOMEN10",
    "BOARD:ELITEPRIME50",
    "BOARD:ELITEPRIMEWOMEN10",
    "BOARD:CURRENT30",
    "BOARD:CURRENTWOMEN10",
)
# The overview publishes the three men's headline boards beside the release
# facts they were built from. Every women's table stays in the publication only.
OVERVIEW_MARKERS = (
    "PUBLICATION:RELEASE",
    "BOARD:TOP100",
    "BOARD:ELITEPRIME50",
    "BOARD:CURRENT30",
)


def _marked_block(text: str, marker: str) -> str:
    begin, end = f"<!-- {marker}:BEGIN -->", f"<!-- {marker}:END -->"
    start = text.index(begin) + len(begin)
    return text[start : text.index(end, start)].strip("\n")


def test_generated_publication_carries_every_board():
    rankings = (PROJECT_ROOT / "RANKINGS.md").read_text(encoding="utf-8")
    for marker in PUBLICATION_MARKERS:
        assert rankings.count(f"<!-- {marker}:BEGIN -->") == 1
        assert rankings.count(f"<!-- {marker}:END -->") == 1


def test_overview_publishes_only_the_headline_boards():
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

    assert "## What is published" in readme
    for marker in OVERVIEW_MARKERS:
        assert readme.count(f"<!-- {marker}:BEGIN -->") == 1
        assert readme.count(f"<!-- {marker}:END -->") == 1
    for marker in set(PUBLICATION_MARKERS) - set(OVERVIEW_MARKERS):
        assert f"<!-- {marker}:BEGIN -->" not in readme


def test_overview_boards_are_the_published_release_not_a_copy_that_drifted():
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    rankings = (PROJECT_ROOT / "RANKINGS.md").read_text(encoding="utf-8")

    for marker in OVERVIEW_MARKERS:
        assert _marked_block(readme, marker) == _marked_block(rankings, marker), (
            f"{marker} differs between README.md and RANKINGS.md; republish both "
            "with build_boards.py --write-readme"
        )


def test_gender_explanation_is_stated_once_in_the_publication():
    rankings = (PROJECT_ROOT / "RANKINGS.md").read_text(encoding="utf-8")
    assert rankings.count(GENDER_GAUGE_NOTE) == 1


def test_source_matrix_integrity_factors_match_the_code():
    matrix = (PROJECT_ROOT / "data" / "SOURCE_MATRIX.md").read_text(encoding="utf-8")
    expected = {
        "PED-confirmed": INTEGRITY_PED_FACTOR,
        "DQ winner": INTEGRITY_DQ_WIN_FACTOR,
        "Missed-weight winner": INTEGRITY_MISSED_WEIGHT_WIN_FACTOR,
    }

    for label, factor in expected.items():
        discount = 1.0 - factor
        pattern = (
            rf"{re.escape(label)}[^\n]*factor `{factor:.2f}`[^\n]*"
            rf"\(-{discount:.0%}"
        )
        assert re.search(pattern, matrix), f"Source Matrix has a stale {label} factor"


def test_the_inferred_weight_class_error_rate_is_quoted_consistently():
    """One rate, three documents.

    The rate moved when the rule became a four-neighbour vote and only one of
    the three places that quote it was updated, so the docs disagreed with each
    other and with the code.
    """
    quoted = re.compile(r"(\d+)%\*{0,2} of (?:the )?filled (?:weight classes|labels)")
    found = {
        document.name: set(quoted.findall(document.read_text(encoding="utf-8")))
        for document in CURRENT_DOCS
    }
    stated = {name: rates for name, rates in found.items() if rates}
    assert stated, "no document states the inferred weight-class error rate"
    assert set().union(*stated.values()) == {"11"}, stated


def test_the_board_column_glossary_is_one_sentence_in_both_documents():
    """The two documents show the same table, so they must explain it the same.

    They had drifted to "the next board" against "the Prime board below", and
    both then re-defined Prime a few lines under the section that defines it.
    This is a column guide now. The wording belongs in the generated block at
    the next publish; until then this keeps the two copies from separating.
    """
    glossary = (
        "**Prime** and **Prime rank** come from the Prime board below, and **Elite\n"
        "wins** is the evidence behind that rank. A blank rank means the fighter did not\n"
        "qualify, not that they placed last."
    )
    for name in ("README.md", "RANKINGS.md"):
        text = (PROJECT_ROOT / name).read_text(encoding="utf-8")
        assert text.count(glossary) == 1, f"{name} does not state the glossary exactly once"
