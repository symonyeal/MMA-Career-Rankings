"""Keep business-facing release facts tied to the artifacts they describe."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = PROJECT_ROOT / "data" / "snapshots" / "2026-08-13"
PUBLICATIONS = (PROJECT_ROOT / "README.md", PROJECT_ROOT / "RANKINGS.md")


def _require(path: Path) -> pd.DataFrame:
    if not path.exists():
        pytest.skip(f"snapshot artifact not present: {path.name}")
    return pd.read_parquet(path)


def _ranked(name: str) -> pd.DataFrame:
    board = _require(SNAPSHOT / name)
    return board[board["status"].eq("ranked")]


def _release_value(document: Path, label: str) -> str:
    text = document.read_text(encoding="utf-8")
    match = re.search(rf"^\| {re.escape(label)} \| (.+) \|$", text, re.MULTILINE)
    assert match, f"{document.name} has no {label!r} release fact"
    return match.group(1)


def test_prime_qualifier_counts_match_both_boards():
    men = len(_ranked("prime_elite_board.parquet"))
    women = len(_ranked("prime_elite_board_women.parquet"))
    expected = f"{men:,} {'man' if men == 1 else 'men'}; {women:,} "
    expected += "woman" if women == 1 else "women"

    for document in PUBLICATIONS:
        assert _release_value(document, "Prime qualifiers") == expected


def test_career_coverage_matches_both_publications():
    from loaders.career_coverage import coverage_summary

    summary = coverage_summary(_require(SNAPSHOT / "career_coverage.parquet"))
    merged = summary["whole_career_merged"]
    eligible = summary["eligible"]
    expected = f"{merged:,} of {eligible:,} eligible fighters ({merged / eligible:.1%})"

    for document in PUBLICATIONS:
        assert _release_value(document, "Whole-career coverage") == expected


def test_release_volume_and_date_match_the_manifests():
    rating_run = json.loads((SNAPSHOT / "rating_run.json").read_text(encoding="utf-8"))
    combined = json.loads(
        (SNAPSHOT / "combined_fights_summary.json").read_text(encoding="utf-8")
    )
    expected = {
        "Data through": rating_run["combined_fights"]["date_range"][-1],
        "Rated fights": f"{rating_run['rated_bouts']:,}",
        "Rated fighters": f"{rating_run['current_fighters']:,}",
        "Available fight records": f"{combined['rows']:,}",
    }

    for document in PUBLICATIONS:
        for label, value in expected.items():
            assert _release_value(document, label) == value


def test_readme_explains_the_rules_that_change_the_rankings():
    text = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    article = text.split("## What is published", 1)[0]
    flat = " ".join(article.split())

    for heading in (
        "### Weight classes are different competitive worlds",
        "### The UFC is the anchor, not the whole sport",
        "### The result is not just win or loss",
        "### A later career can change the meaning of an earlier fight",
        "## Three questions, three boards",
    ):
        assert heading in article

    for implemented_rule in (
        "Career division is where most effective appearances occurred",
        "The UFC is `1.00`",
        "one neutral virtual bout—half a win and half a loss",
        "All-time = 30% championships + 17.5% career skill + 52.5% contender résumé",
        "Five wins are required",
        "eight UFC bouts",
        "within 18 months",
    ):
        assert implemented_rule in flat


def test_readme_policy_constants_are_the_ones_the_code_uses():
    """Every tuned number the overview quotes, read back from the source.

    The overview states the promotion factors, method scores, score weights and
    board thresholds outright. Those are the numbers a refit moves, so each is
    asserted against its constant rather than trusted to stay current. Words
    that spell a number out are checked against the constant's value too, so
    changing either half breaks this.
    """
    from build_boards import CURRENT_MAX_MONTHS_INACTIVE
    from ratings.constants import (
        METHOD_SCORE_DQ,
        METHOD_SCORE_FINISH,
        METHOD_SCORE_NON_UNANIMOUS_DECISION,
        METHOD_SCORE_UNANIMOUS,
        SUSTAINED_PEAK_MIN_FIGHTS,
    )
    from ratings.layoff import (
        MAX_EXCESS_TURNAROUNDS,
        OPPONENT_LAYOFF_ELO_PER_TURNAROUND,
    )
    from ratings.legacy_resume import (
        LEGACY_ACHIEVEMENT_WEIGHT,
        LEGACY_QUALITY_SKILL_SHARE,
        ORG_FACTOR_BY_CANONICAL,
        TITLE_QUALITY_MAJOR_FLOOR,
    )
    from ratings.opponent_quality import (
        CONTENDER_LINE_MU,
        MIN_OPPONENT_UFC_BOUTS,
        MIN_QUALITY_WINS,
    )
    from ratings.symon_score import DEFAULT_DIVISION_MIN_POPULATION
    from ratings.whr import _ELO_ANCHOR

    # Wrapped prose puts line breaks mid-phrase, so match on one flat line.
    readme = " ".join((PROJECT_ROOT / "README.md").read_text(encoding="utf-8").split())
    quality = 1.0 - LEGACY_ACHIEVEMENT_WEIGHT

    expected = {
        "achievement weight": f"{LEGACY_ACHIEVEMENT_WEIGHT:.0%} championships",
        "career skill share": f"{quality * LEGACY_QUALITY_SKILL_SHARE:.1%} career skill",
        "resume share": f"{quality * (1 - LEGACY_QUALITY_SKILL_SHARE):.1%} contender résumé",
        "finish score": f"submission scores `{METHOD_SCORE_FINISH:.2f}`",
        "unanimous score": f"unanimous decision `{METHOD_SCORE_UNANIMOUS:.2f}`",
        "split score": f"majority decision `{METHOD_SCORE_NON_UNANIMOUS_DECISION:.2f}`",
        "dq score": f"disqualification `{METHOD_SCORE_DQ:.2f}`",
        "draw score": "a draw `0.50` for each fighter",
        "contender line": f"rated at least {CONTENDER_LINE_MU:,.0f}"[:-2],
        "layoff charge": f"lose {abs(OPPONENT_LAYOFF_ELO_PER_TURNAROUND):.0f} points per excess",
        "title floor": f"carry a `{TITLE_QUALITY_MAJOR_FLOOR:.2f}` floor",
        "rated appearances": f"needs {SUSTAINED_PEAK_MIN_FIGHTS} rated appearances",
        "current window": f"within {CURRENT_MAX_MONTHS_INACTIVE:.0f} months",
        "division floor": f"fewer than {DEFAULT_DIVISION_MIN_POPULATION} fighter-years",
        "elo anchor": f"displayed around {_ELO_ANCHOR:,.0f}"[:-2],
    }
    missing = {k: v for k, v in expected.items() if v not in readme}
    assert not missing, f"README no longer states these as the code defines them: {missing}"

    # Spelled out in prose; pin the word and the constant behind it together.
    spelled = [
        (MIN_OPPONENT_UFC_BOUTS, 8, "at least eight UFC fights"),
        (MIN_QUALITY_WINS, 5, "Five wins are required"),
        (MAX_EXCESS_TURNAROUNDS, 4, "capped at four"),
    ]
    for constant, value, phrase in spelled:
        assert constant == value, f"{phrase!r} spells out {value}, code now says {constant}"
        assert phrase in readme, f"README no longer says {phrase!r}"

    for org, factor in ORG_FACTOR_BY_CANONICAL.items():
        assert org in readme, f"README omits promotion {org}"
        assert f"`{factor:.2f}`" in readme, f"README omits the {org} factor {factor:.2f}"


def test_the_promotion_gap_matches_the_rated_scope():
    """The one coverage figure stated in prose, read back from the table.

    It moved 64% -> 57% when event-card hydration landed, and nothing would
    have caught it: the release block regenerates itself, this sentence does
    not.
    """
    from loaders.combined_fights import load_combined_fights

    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    match = re.search(r"Promotion labels are missing from (\d+)% of rated fights", readme)
    assert match, "README no longer states the promotion gap"

    if not (SNAPSHOT / "combined_fights.parquet").exists():
        pytest.skip("combined_fights.parquet not present")
    fights, _ = load_combined_fights(SNAPSHOT, scope="majors,pre_unified", label="test")
    rated = fights[fights["is_model_bout"].astype(bool)]
    org = rated["org"].notna() & rated["org"].astype("string").str.strip().ne("")
    measured = round((~org).mean() * 100)
    assert int(match.group(1)) == measured, (
        f"README says {match.group(1)}% of rated fights lack a promotion; "
        f"the table says {measured}%"
    )
