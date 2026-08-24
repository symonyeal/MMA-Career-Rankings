from __future__ import annotations

import pandas as pd
import pytest

from ratings.legacy_resume import (
    MULTI_DIVISION_TITLE_POINTS,
    RANK_CONTEXT_WIN_POINTS,
    TITLE_APPEARANCE_POINTS,
    TITLE_DEFENSE_POINTS,
    TITLE_WIN_POINTS,
    championship_resume_ledger,
    public_legacy_score_rows,
    source_title_resume_ledger,
)


def _appearance(
    fighter: str,
    division: str,
    *,
    title: bool,
    won: bool,
    entered_champ: bool = False,
) -> dict[str, object]:
    return {
        "fighter": fighter,
        "division": division,
        "actual_score": 1.0 if won else 0.0,
        "is_championship_bout": title,
        "is_interim_title_bout": False,
        "fighter_entered_as_champion": entered_champ,
        "fighter_entered_as_interim_champion": False,
    }


def test_championship_resume_ledger_counts_title_wins_defenses_and_divisions():
    appearances = pd.DataFrame(
        [
            _appearance("Champion", "Lightweight", title=True, won=True),
            _appearance("Champion", "Lightweight", title=True, won=True, entered_champ=True),
            _appearance("Champion", "Welterweight", title=True, won=True),
            _appearance("Champion", "Welterweight", title=False, won=True),
            _appearance("Contender", "Lightweight", title=True, won=False),
        ]
    )

    ledger = championship_resume_ledger(appearances).set_index("fighter")

    assert ledger.loc["Champion", "public_legacy_title_appearances"] == 3
    assert ledger.loc["Champion", "public_legacy_title_wins"] == 3
    assert ledger.loc["Champion", "public_legacy_title_defenses"] == 1
    assert ledger.loc["Champion", "public_legacy_title_win_divisions"] == 2
    assert ledger.loc["Contender", "public_legacy_title_appearances"] == 1
    assert ledger.loc["Contender", "public_legacy_title_wins"] == 0


def test_public_legacy_score_lifts_proven_title_resume_above_raw_skill_mass():
    current = pd.DataFrame(
        {
            "fighter": ["Clean Record", "Title Reign"],
            "symon_career_skill_mass": [2000.0, 900.0],
        }
    )
    appearances = pd.DataFrame(
        [
            _appearance("Title Reign", "Flyweight", title=True, won=True),
            _appearance("Title Reign", "Flyweight", title=True, won=True, entered_champ=True),
            _appearance("Title Reign", "Flyweight", title=True, won=True, entered_champ=True),
            _appearance("Title Reign", "Flyweight", title=True, won=True, entered_champ=True),
            _appearance("Title Reign", "Bantamweight", title=True, won=True),
            _appearance("Clean Record", "Lightweight", title=False, won=True),
        ]
    )

    scored = public_legacy_score_rows(current, appearances).set_index("fighter")
    expected_title_score = (
        5 * TITLE_APPEARANCE_POINTS
        + 5 * TITLE_WIN_POINTS
        + 3 * TITLE_DEFENSE_POINTS
        + MULTI_DIVISION_TITLE_POINTS
    )

    assert scored.loc["Title Reign", "public_legacy_title_score"] == pytest.approx(
        expected_title_score
    )
    assert scored.loc["Title Reign", "public_legacy_score"] == pytest.approx(
        900.0 + expected_title_score
    )
    assert scored.loc["Title Reign", "public_legacy_score"] > scored.loc[
        "Clean Record",
        "public_legacy_score",
    ]


def test_public_legacy_score_keeps_raw_skill_mass_as_auditable_component():
    current = pd.DataFrame(
        {"fighter": ["A"], "symon_career_skill_mass": [123.0]}
    )
    scored = public_legacy_score_rows(current, pd.DataFrame()).iloc[0]

    assert scored["public_legacy_skill_mass"] == pytest.approx(123.0)
    assert scored["public_legacy_title_score"] == pytest.approx(0.0)
    assert scored["public_legacy_schedule_score"] == pytest.approx(0.0)
    assert scored["public_legacy_score"] == pytest.approx(123.0)


def test_public_legacy_schedule_score_counts_rank_context_on_wins_only():
    current = pd.DataFrame(
        {"fighter": ["Schedule"], "symon_career_skill_mass": [100.0]}
    )
    appearances = pd.DataFrame(
        [
            {
                **_appearance("Schedule", "Lightweight", title=False, won=True),
                "perf_factor_rank_context": 1.08,
            },
            {
                **_appearance("Schedule", "Lightweight", title=False, won=False),
                "perf_factor_rank_context": 1.08,
            },
        ]
    )

    scored = public_legacy_score_rows(current, appearances).iloc[0]

    assert scored["public_legacy_rank_context_win_mass"] == pytest.approx(0.08)
    assert scored["public_legacy_schedule_score"] == pytest.approx(
        0.08 * RANK_CONTEXT_WIN_POINTS
    )
    assert scored["public_legacy_score"] == pytest.approx(196.0)


def test_source_title_resume_ledger_uses_full_scope_title_flags():
    fights = pd.DataFrame(
        [
            {
                "fight_url": "1",
                "event_date": "2020-01-01",
                "event_name": "Bellator Title",
                "org": "Bellator",
                "weight_class": "Lightweight",
                "fighter_a": "Champion",
                "fighter_b": "Challenger A",
                "winner": "Champion",
                "is_draw": False,
                "is_title_fight": True,
            },
            {
                "fight_url": "2",
                "event_date": "2020-06-01",
                "event_name": "Bellator Defense",
                "org": "Bellator",
                "weight_class": "Lightweight",
                "fighter_a": "Champion",
                "fighter_b": "Challenger B",
                "winner": "Champion",
                "is_draw": False,
                "is_title_fight": True,
            },
            {
                "fight_url": "3",
                "event_date": "2021-01-01",
                "event_name": "Second Belt",
                "org": "Bellator",
                "weight_class": "Welterweight",
                "fighter_a": "Champion",
                "fighter_b": "Challenger C",
                "winner": "Champion",
                "is_draw": False,
                "is_title_fight": True,
            },
        ]
    )

    ledger = source_title_resume_ledger(fights).set_index("fighter")

    assert ledger.loc["Champion", "public_legacy_title_appearances"] == 3
    assert ledger.loc["Champion", "public_legacy_title_wins"] == 3
    assert ledger.loc["Champion", "public_legacy_title_defenses"] == 1
    assert ledger.loc["Champion", "public_legacy_title_win_divisions"] == 2
    assert ledger.loc["Champion", "public_legacy_source_title_score"] == pytest.approx(
        (3 * TITLE_APPEARANCE_POINTS + 3 * TITLE_WIN_POINTS + TITLE_DEFENSE_POINTS)
        * 0.65
        + MULTI_DIVISION_TITLE_POINTS * 0.65
    )


def test_source_title_resume_ledger_collapses_womens_and_open_title_labels():
    fights = pd.DataFrame(
        [
            {
                "fight_url": "ufc1",
                "event_date": "2017-01-01",
                "event_name": "UFC Title",
                "source": "ufc",
                "org": None,
                "weight_class": "UFC Women's Featherweight Title Bout",
                "fighter_a": "Champion",
                "fighter_b": "Challenger A",
                "winner": "Champion",
                "is_draw": False,
                "is_title_fight": True,
            },
            {
                "fight_url": "ufc2",
                "event_date": "2018-01-01",
                "event_name": "UFC Defense",
                "source": "ufc",
                "org": None,
                "weight_class": "UFC Women's Featherweight Title Bout",
                "fighter_a": "Champion",
                "fighter_b": "Challenger B",
                "winner": "Champion",
                "is_draw": False,
                "is_title_fight": True,
            },
            {
                "fight_url": "bellator1",
                "event_date": "2020-01-01",
                "event_name": "Bellator Title",
                "source": "sherdog_majors",
                "org": "Bellator",
                "weight_class": "Featherweight",
                "fighter_a": "Champion",
                "fighter_b": "Challenger C",
                "winner": "Champion",
                "is_draw": False,
                "is_title_fight": True,
            },
        ]
    )

    ledger = source_title_resume_ledger(fights).set_index("fighter")

    assert ledger.loc["Champion", "public_legacy_title_win_divisions"] == 1
    assert ledger.loc["Champion", "public_legacy_source_title_score"] == pytest.approx(
        2 * TITLE_APPEARANCE_POINTS
        + 2 * TITLE_WIN_POINTS
        + TITLE_DEFENSE_POINTS
        + (TITLE_APPEARANCE_POINTS + TITLE_WIN_POINTS) * 0.65
    )


def test_public_legacy_score_uses_source_title_flags_when_appearance_context_is_narrow():
    current = pd.DataFrame(
        {"fighter": ["Champion"], "symon_career_skill_mass": [100.0]}
    )
    appearances = pd.DataFrame(
        [
            _appearance("Champion", "Lightweight", title=False, won=True),
            _appearance("Champion", "Lightweight", title=False, won=True),
        ]
    )
    source_fights = pd.DataFrame(
        [
            {
                "fight_url": "1",
                "event_date": "2020-01-01",
                "event_name": "Major Title",
                "source": "sherdog_majors",
                "org": "PRIDE",
                "weight_class": "Heavyweight",
                "fighter_a": "Champion",
                "fighter_b": "Challenger",
                "winner": "Champion",
                "is_draw": False,
                "is_title_fight": True,
            }
        ]
    )

    scored = public_legacy_score_rows(
        current,
        appearances,
        source_fights=source_fights,
    ).iloc[0]

    assert scored["public_legacy_title_appearances"] == 1
    assert scored["public_legacy_title_wins"] == 1
    assert scored["public_legacy_title_score"] == pytest.approx(
        (TITLE_APPEARANCE_POINTS + TITLE_WIN_POINTS) * 0.95
    )
    assert scored["public_legacy_exposure_factor"] == pytest.approx(0.95)
    assert scored["public_legacy_skill_score"] == pytest.approx(95.0)


def test_source_title_resume_ledger_infers_defenses_with_blank_org():
    fights = pd.DataFrame(
        [
            {
                "fight_url": "1",
                "event_date": "2020-01-01",
                "event_name": "UFC Title",
                "source": "ufc",
                "org": None,
                "weight_class": "UFC Middleweight Title Bout",
                "fighter_a": "Champion",
                "fighter_b": "Challenger A",
                "winner": "Champion",
                "is_draw": False,
                "is_title_fight": True,
            },
            {
                "fight_url": "2",
                "event_date": "2020-06-01",
                "event_name": "UFC Defense",
                "source": "ufc",
                "org": None,
                "weight_class": "UFC Middleweight Title Bout",
                "fighter_a": "Champion",
                "fighter_b": "Challenger B",
                "winner": "Champion",
                "is_draw": False,
                "is_title_fight": True,
            },
        ]
    )

    ledger = source_title_resume_ledger(fights).set_index("fighter")

    assert ledger.loc["Champion", "public_legacy_title_defenses"] == 1
