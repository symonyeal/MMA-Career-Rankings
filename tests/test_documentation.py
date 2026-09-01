from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote


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
    "BOARD:PRIME100",
    "BOARD:PRIMEWOMEN10",
    "BOARD:ELITEPRIME50",
    "BOARD:ELITEPRIMEWOMEN10",
)
# The business overview publishes the two headline boards beside the release
# facts they were built from. Every other table stays in the publication only.
OVERVIEW_MARKERS = ("PUBLICATION:RELEASE", "BOARD:TOP100", "BOARD:ELITEPRIME50")


def _marked_block(text: str, marker: str) -> str:
    begin, end = f"<!-- {marker}:BEGIN -->", f"<!-- {marker}:END -->"
    start = text.index(begin) + len(begin)
    return text[start : text.index(end, start)].strip("\n")


def test_generated_publication_carries_every_board():
    rankings = (PROJECT_ROOT / "RANKINGS.md").read_text(encoding="utf-8")
    for marker in PUBLICATION_MARKERS:
        assert rankings.count(f"<!-- {marker}:BEGIN -->") == 1
        assert rankings.count(f"<!-- {marker}:END -->") == 1


def test_business_overview_publishes_only_the_headline_boards():
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

    assert "## Business outputs" in readme
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
