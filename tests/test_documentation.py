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


def test_business_overview_and_generated_rankings_are_separate():
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    rankings = (PROJECT_ROOT / "RANKINGS.md").read_text(encoding="utf-8")

    assert "## Business outputs" in readme
    assert "<!-- BOARD:" not in readme
    for marker in (
        "PUBLICATION:RELEASE",
        "BOARD:TOP100",
        "BOARD:WOMEN10",
        "BOARD:PRIME100",
        "BOARD:PRIMEWOMEN10",
        "BOARD:ELITEPRIME50",
        "BOARD:ELITEPRIMEWOMEN10",
    ):
        assert rankings.count(f"<!-- {marker}:BEGIN -->") == 1
        assert rankings.count(f"<!-- {marker}:END -->") == 1
