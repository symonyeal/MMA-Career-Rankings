from __future__ import annotations

import pandas as pd
import pytest

from ratings.legacy_resume import (
    PUBLIC_LEGACY_DISPLAY_SCALE,
    RANK_CONTEXT_WIN_POINTS,
    championship_resume_ledger,
    public_legacy_score_rows,
    source_title_resume_ledger,
    title_quality,
    title_quality_ledger,
    ufc_debut_dates_from,
)
from ratings.legacy_resume import _pool_offset


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
    """A title reign over real contenders outranks a bigger untested skill mass."""
    current = pd.DataFrame(
        {
            "fighter": ["Clean Record", "Title Reign"],
            "symon_career_skill_mass": [2000.0, 900.0],
        }
    )
    appearances = pd.DataFrame(
        [
            _appearance("Title Reign", "Flyweight", title=True, won=True),
            _appearance("Clean Record", "Lightweight", title=False, won=True),
        ]
    )
    fights = pd.DataFrame(
        [
            {
                "fight_url": "t%d" % i,
                "event_date": "202%d-01-01" % i,
                "event_name": "Title",
                "org": "UFC",
                "weight_class": "Flyweight",
                "fighter_a": "Title Reign",
                "fighter_b": "Contender %d" % i,
                "winner": "Title Reign",
                "is_draw": False,
                "is_title_fight": True,
            }
            for i in range(1, 4)
        ]
    )
    history = pd.DataFrame(
        [
            {"fighter": "Contender %d" % i, "event_date": "201%d-01-01" % i, "mu_whr": 2000.0}
            for i in range(1, 4)
        ]
        + [{"fighter": "Filler", "event_date": "2015-01-01", "mu_whr": 1500.0}]
    )

    scored = public_legacy_score_rows(
        current, appearances, source_fights=fights, history=history, reference="mean"
    ).set_index("fighter")

    assert scored.loc["Title Reign", "public_legacy_qualifying_title_wins"] == 3
    assert scored.loc["Title Reign", "public_legacy_title_quality"] > 0
    assert scored.loc["Clean Record", "public_legacy_title_score"] == pytest.approx(0.0)
    assert (
        scored.loc["Title Reign", "public_legacy_score"]
        > scored.loc["Clean Record", "public_legacy_score"]
    )


def test_title_quality_is_convex_and_never_zero():
    """Strictly positive and strongly convex.

    A hinge at the bar was tried and rejected: it zeroed the title component
    for 38 fighters with three or more title wins, Shevchenko and Usman among
    them. Beating a weak champion must be worth little, never nothing.
    """
    bar = pd.Series([1800.0] * 5)
    mu = pd.Series([1400.0, 1750.0, 1800.0, 1900.0, 2200.0])
    w = title_quality(mu, bar).to_numpy()

    assert (w > 0).all()
    assert list(w) == sorted(w)
    assert w[2] == pytest.approx(0.5 ** 4)
    # strongly convex: an elite opponent is worth many times a bar-level one
    assert w[4] / w[2] > 8.0
    # and a sub-contender is worth a small fraction of a bar-level one
    assert w[0] / w[2] < 0.05


def test_title_quality_ledger_prices_a_stacked_reign_over_a_padded_one():
    """Six wins over sub-contenders lose to two wins over real contenders.

    This is the defect the flat 45-points-per-title-win ledger could not
    express: it scored the padded reign three times higher purely on count.
    """
    padded = [
        {
            "fight_url": "p%d" % i,
            "event_date": "2020-0%d-01" % i,
            "event_name": "Regional",
            "org": "Bellator",
            "weight_class": "Lightweight",
            "fighter_a": "Padded",
            "fighter_b": "Weak %d" % i,
            "winner": "Padded",
            "is_draw": False,
            "is_title_fight": True,
        }
        for i in range(1, 7)
    ]
    stacked = [
        {
            "fight_url": "s%d" % i,
            "event_date": "2020-0%d-01" % i,
            "event_name": "Major",
            "org": "UFC",
            "weight_class": "Lightweight",
            "fighter_a": "Stacked",
            "fighter_b": "Elite %d" % i,
            "winner": "Stacked",
            "is_draw": False,
            "is_title_fight": True,
        }
        for i in range(1, 3)
    ]
    history = pd.DataFrame(
        [
            {"fighter": "Weak %d" % i, "event_date": "2019-01-01", "mu_whr": 1650.0}
            for i in range(1, 7)
        ]
        + [
            {"fighter": "Elite %d" % i, "event_date": "2019-01-01", "mu_whr": 2050.0}
            for i in range(1, 3)
        ]
        + [{"fighter": "Bar", "event_date": "2019-01-01", "mu_whr": 1700.0}]
    )

    ledger = title_quality_ledger(
        pd.DataFrame(padded + stacked), history, reference="mean"
    ).set_index("fighter")

    assert ledger.loc["Padded", "public_legacy_qualifying_title_wins"] == 0
    assert ledger.loc["Stacked", "public_legacy_qualifying_title_wins"] == 2
    # Six padded wins must not outscore two stacked ones -- the defect the flat
    # 45-points-per-win ledger could not express.
    assert (
        ledger.loc["Stacked", "public_legacy_title_quality"]
        > ledger.loc["Padded", "public_legacy_title_quality"]
    )
    # and the padded reign is still credited something, not zeroed
    assert ledger.loc["Padded", "public_legacy_title_quality"] > 0


def test_title_quality_ledger_ignores_the_bout_being_priced():
    """The opponent's rating must be PRE-fight, never the post-bout value."""
    fights = pd.DataFrame(
        [
            {
                "fight_url": "1",
                "event_date": "2020-01-01",
                "event_name": "T",
                "org": "UFC",
                "weight_class": "Lightweight",
                "fighter_a": "Winner",
                "fighter_b": "Opponent",
                "winner": "Winner",
                "is_draw": False,
                "is_title_fight": True,
            }
        ]
    )
    history = pd.DataFrame(
        [
            {"fighter": "Opponent", "event_date": "2020-01-01", "mu_whr": 2200.0},
            {"fighter": "Filler", "event_date": "2019-01-01", "mu_whr": 1500.0},
        ]
    )

    ledger = title_quality_ledger(fights, history, reference="mean")
    assert ledger.empty or ledger["public_legacy_title_quality"].sum() == pytest.approx(0.0)


def test_title_quality_ledger_without_history_is_empty_not_guessed():
    fights = pd.DataFrame(
        [
            {
                "fight_url": "1",
                "event_date": "2020-01-01",
                "event_name": "T",
                "org": "UFC",
                "weight_class": "Lightweight",
                "fighter_a": "A",
                "fighter_b": "B",
                "winner": "A",
                "is_draw": False,
                "is_title_fight": True,
            }
        ]
    )
    assert title_quality_ledger(fights, None).empty
    assert title_quality_ledger(None, pd.DataFrame()).empty


def test_public_legacy_score_keeps_raw_skill_mass_as_auditable_component():
    current = pd.DataFrame(
        {"fighter": ["A"], "symon_career_skill_mass": [123.0]}
    )
    scored = public_legacy_score_rows(current, pd.DataFrame()).iloc[0]

    assert scored["public_legacy_skill_mass"] == pytest.approx(123.0)
    assert scored["public_legacy_title_score"] == pytest.approx(0.0)
    assert scored["public_legacy_schedule_score"] == pytest.approx(0.0)
    # Value-normalised: the only fighter is his own maximum on the one live
    # component, so the score is one unit of display scale.
    assert scored["public_legacy_score"] == pytest.approx(PUBLIC_LEGACY_DISPLAY_SCALE)


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
    # Two live components, each at its own maximum for a single-fighter frame.
    assert scored["public_legacy_score"] == pytest.approx(
        2 * PUBLIC_LEGACY_DISPLAY_SCALE
    )


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
    # This ledger now carries COUNTS only; the score comes from
    # title_quality_ledger, which prices each win by the opponent beaten.
    assert ledger.loc["Champion", "public_legacy_source_title_score"] == pytest.approx(0.0)


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
    # Title counts still come from the source flags; the title SCORE is zero
    # without a rating history to price the opponent with.
    assert scored["public_legacy_title_score"] == pytest.approx(0.0)
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


# ---------------------------------------------------------------------------
# Pool-priced title ledger (2026-08-28)
#
# The held-out probe measures the UFC-tested pool sitting +54 Elo [+10, +100]
# above where the ratings place it relative to never-UFC opponents. Applying
# that on the ledger path -- and ONLY there -- is what these pin.


def _pool_history() -> pd.DataFrame:
    """Two title challengers of identical rating, one UFC-tested, one not."""
    rows = []
    for fighter, mu in (
        ("Tested Champ", 1900.0),
        ("Regional Champ", 1900.0),
        ("Filler A", 1700.0),
        ("Filler B", 1650.0),
        ("Filler C", 1600.0),
        ("Beater X", 1800.0),
        ("Beater Y", 1800.0),
    ):
        for year in (2018, 2019, 2020):
            rows.append(
                {
                    "fighter": fighter,
                    "event_date": pd.Timestamp(f"{year}-06-01"),
                    "mu_whr": mu,
                }
            )
    return pd.DataFrame(rows)


def _pool_fights() -> pd.DataFrame:
    def bout(url, date, a, b, winner, corpus, title=True):
        return {
            "fight_url": url,
            "event_date": pd.Timestamp(date),
            "event_name": url,
            "fighter_a": a,
            "fighter_b": b,
            "winner": winner,
            "is_draw": False,
            "is_nc": False,
            "is_excluded": False,
            "is_title_fight": title,
            "source_corpus": corpus,
        }

    return pd.DataFrame(
        [
            # The UFC-tested champion's qualifying bout, before both title wins.
            bout("u/0", "2017-01-01", "Tested Champ", "Filler A", "Tested Champ",
                 "ufc", title=False),
            bout("u/1", "2020-01-01", "Beater X", "Tested Champ", "Beater X", "ufc"),
            bout("u/2", "2020-01-01", "Beater Y", "Regional Champ", "Beater Y",
                 "majors"),
        ]
    )


def test_pool_offset_lifts_a_ufc_tested_title_opponent_and_not_a_regional_one():
    fights, history = _pool_fights(), _pool_history()
    off = title_quality_ledger(
        fights, history, pool_offset_elo=0.0
    ).set_index("fighter")["public_legacy_title_quality"]
    on = title_quality_ledger(
        fights,
        history,
        ufc_debut_dates=ufc_debut_dates_from(fights),
        pool_offset_elo=54.0,
    ).set_index("fighter")["public_legacy_title_quality"]

    # Two champions with identical ratings price identically until the pool
    # state is read: "Beater X" took the UFC-tested belt, "Beater Y" the
    # regional one.
    assert off["Beater X"] == pytest.approx(off["Beater Y"])
    assert on["Beater X"] > on["Beater Y"]
    # The contender LINE is corrected too, which is the whole point of applying
    # the offset on both sides -- so beating an uncorrected regional champion is
    # worth strictly less once the pool above him is placed correctly.
    assert on["Beater Y"] < off["Beater Y"]


def test_pool_offset_is_inert_without_debut_dates_or_at_zero():
    fights, history = _pool_fights(), _pool_history()
    base = title_quality_ledger(fights, history, pool_offset_elo=0.0)
    no_dates = title_quality_ledger(fights, history, pool_offset_elo=54.0)
    zero = title_quality_ledger(
        fights,
        history,
        ufc_debut_dates=ufc_debut_dates_from(fights),
        pool_offset_elo=0.0,
    )
    pd.testing.assert_frame_equal(base, no_dates)
    pd.testing.assert_frame_equal(base, zero)


def test_ufc_debut_dates_reads_the_whole_ufc_family_and_only_prior_bouts():
    fights = _pool_fights()
    debuts = ufc_debut_dates_from(fights)
    assert debuts["Tested Champ"] == pd.Timestamp("2017-01-01")
    assert "Regional Champ" not in debuts
    # A bout on the debut date is not "prior experience": the state is strictly
    # before, which is the rule the offset was measured under.
    same_day = _pool_offset(
        pd.Series(["Tested Champ"]),
        pd.Series([pd.Timestamp("2017-01-01")]),
        debuts,
        54.0,
    )
    assert same_day.tolist() == [0.0]
