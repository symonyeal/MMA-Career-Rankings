"""The README's narrative numbers are the published release's numbers.

Before 2026-10-23 the "points total" and era paragraphs were written by hand and
checked by nobody; a release that moved a score left them quoting the last one.
Each sentence below is rebuilt from :func:`analysis.readme_figures.figures`, so a
refit that moves any of them fails here until the README is updated.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from analysis.readme_figures import figures, write_readme

README = (Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def F():
    return figures()


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _n(x: float) -> str:
    return f"{round(x):,}"


def test_points_total_paragraph(F):
    want = (
        f"Jon Jones's {_n(F['score_a'])} against Georges St-Pierre's {_n(F['score_b'])} does not mean Jones was "
        f"{F['ratio']:.0%} better. It means his three parts add up to more points: title {_n(F['title_a'])} "
        f"against {_n(F['title_b'])}, résumé {_n(F['resume_a'])} against {_n(F['resume_b'])}, skill "
        f"{_n(F['skill_a'])} against {_n(F['skill_b'])}. Most of the résumé gap is two elite wins: "
        f"{F['elite_1_name']} at {_n(F['elite_1_above'])} points above the line and {F['elite_2_name']} at "
        f"{_n(F['elite_2_above'])}, where St-Pierre's best was {F['best_b_name']} at {_n(F['best_b_above'])}. "
        f"For who was better at their best, read Prime: {_n(F['prime_a'])} against {_n(F['prime_b'])}, an "
        f"{_n(F['prime_edge'])}-point edge, which the rating turns into about a {F['prime_win']:.0%} chance of winning."
    )
    assert want in _flat(README)


def test_era_drift_sentence(F):
    want = (
        f"the 60th-best man stood at {_n(F['era_lo'])} in 2007 and {_n(F['era_hi'])} in 2023, so without this era "
        f"adjustment a 2023 win would be priced on a scale about {5 * round(F['era_gap'] / 5)} points higher"
    )
    assert want in _flat(README)


def test_writer_updates_stale_figures_and_preserves_other_text(F, tmp_path):
    p = tmp_path / "README.md"
    p.write_text(README, encoding="utf-8")
    write_readme(F, p)
    assert p.read_text(encoding="utf-8") == README
    write_readme(dict(F, score_a=123456.0), p)
    changed = p.read_text(encoding="utf-8")
    assert "Jon Jones's 123,456" in changed
    assert changed.split("\n\n")[:10] == README.split("\n\n")[:10]
    write_readme(F, p)
    assert _flat(p.read_text(encoding="utf-8")) == _flat(README)


def test_writer_rejects_missing_paragraph_without_writing(F, tmp_path):
    p = tmp_path / "README.md"
    p.write_text("Unrelated document\n", encoding="utf-8")
    with pytest.raises(ValueError, match="expected one README paragraph"):
        write_readme(F, p)
    assert p.read_text(encoding="utf-8") == "Unrelated document\n"
