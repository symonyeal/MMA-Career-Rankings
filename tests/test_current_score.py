"""The Current score: titles and résumé like All-time, over the 18-month window.

Three owner decisions of 2026-10-14 are held here. A fighter needs a UFC bout
inside the window; recent title wins and contender wins count the way they count
on the All-time board; and a rating above the best opponent a fighter has ever
beaten is not credited, because no win supports it.
"""
from __future__ import annotations

import pandas as pd
import pytest

from ratings.current_score import (
    CURRENT_WINDOW_MONTHS,
    best_win_ratings,
    capped_level,
    current_score_rows,
    last_ufc_dates,
)
from ratings.legacy_resume import (
    LEGACY_ACHIEVEMENT_WEIGHT,
    LEGACY_PART_POWER,
    LEGACY_QUALITY_SKILL_SHARE,
    PUBLIC_LEGACY_DISPLAY_SCALE,
)

REF = pd.Timestamp("2026-10-10")


def _bout(url, date, a, b, winner, *, title=False, org="UFC", corpus="ufc", excluded=False):
    return {
        "fight_url": url, "event_date": pd.Timestamp(date), "event_name": "Card",
        "fighter_a": a, "fighter_b": b, "winner": winner,
        "loser": (b if winner == a else a) if winner else None,
        "is_draw": False, "is_nc": winner is None, "is_excluded": excluded,
        "is_title_fight": title, "org": org, "source_corpus": corpus,
        "weight_class": "Lightweight", "is_model_bout": not excluded and winner is not None,
    }


# --- the cap -----------------------------------------------------------------

def test_a_rating_above_the_best_win_is_capped_at_it():
    """Wins bound a rating from below only; losses bound it from above. The part
    of an unbeaten record's rating that sits above everyone it beat is carried
    by the absence of losses, not by any win, so it is not credited."""
    level = pd.Series([2100.0, 1950.0, 1900.0], index=["Prospect", "Champ", "Winless"])
    best = pd.Series({"Prospect": 1950.0, "Champ": 2050.0})
    got = capped_level(level, best)
    assert got["Prospect"] == 1950.0
    assert got["Champ"] == 1950.0
    assert pd.isna(got["Winless"])


def test_the_best_win_is_priced_going_in():
    fights = pd.DataFrame([
        _bout("1", "2025-01-01", "A", "B", "A"),
        _bout("2", "2025-06-01", "A", "C", "A"),
        _bout("3", "2025-07-01", "C", "A", "C"),
    ])
    history = pd.DataFrame([
        {"fighter": "B", "event_date": pd.Timestamp("2024-01-01"), "mu_whr": 1800.0},
        {"fighter": "B", "event_date": pd.Timestamp("2025-01-01"), "mu_whr": 1600.0},
        {"fighter": "C", "event_date": pd.Timestamp("2024-06-01"), "mu_whr": 1900.0},
    ])
    best = best_win_ratings(fights, history)
    # B is read at 1800, before the bout that lowered him; a loss is not a win.
    assert best["A"] == 1900.0
    assert "B" not in best.index
    # C's only win is over A, who has no rating to price it with.
    assert "C" not in best.index


# --- the UFC-bout requirement -------------------------------------------------

def test_a_ufc_bout_of_any_outcome_and_either_source_counts():
    fights = pd.DataFrame([
        _bout("1", "2024-07-27", "Tom", "Curtis", "Tom"),
        _bout("2", "2025-10-25", "Tom", "Ciryl", None, org="Ultimate Fighting Championship (UFC)",
              corpus="majors", excluded=True),
        _bout("3", "2026-05-16", "Francis", "Philipe", "Francis", org=None, corpus="majors"),
        _bout("4", "2022-01-22", "Francis", "Ciryl", "Francis"),
    ])
    last = last_ufc_dates(fights)
    assert last["Tom"] == pd.Timestamp("2025-10-25")
    assert last["Francis"] == pd.Timestamp("2022-01-22")


# --- the score ----------------------------------------------------------------

def _population():
    current = pd.DataFrame({
        "fighter": ["Champ", "Prospect", "Contender"],
        "mu_whr_age_activity_adjusted": [1980.0, 2100.0, 1950.0],
        "public_legacy_exposure_factor": [1.0, 1.0, 1.0],
        "rating_periods": [20, 20, 20],
    })
    rows = []
    # Each opponent gets eight UFC bouts so they are tested.
    for opp in ("Elite", "Good", "Soft"):
        rows += [_bout(f"{opp}{i}", "2015-01-01", opp, f"F{opp}{i}", opp) for i in range(8)]
    rows += [
        _bout("t1", "2026-05-09", "Champ", "Elite", "Champ", title=True),
        _bout("c1", "2026-03-21", "Contender", "Good", "Contender"),
        _bout("p1", "2026-02-01", "Prospect", "Soft", "Prospect"),
    ]
    history = pd.DataFrame([
        {"fighter": "Elite", "event_date": pd.Timestamp("2025-01-01"), "mu_whr": 2000.0},
        {"fighter": "Good", "event_date": pd.Timestamp("2025-01-01"), "mu_whr": 1900.0},
        {"fighter": "Soft", "event_date": pd.Timestamp("2025-01-01"), "mu_whr": 1700.0},
    ])
    fights = pd.DataFrame(rows)
    return current, fights, history


def test_the_score_is_the_all_time_formula_over_the_window():
    current, fights, history = _population()
    got = current_score_rows(
        current, rated_fights=fights, recorded_fights=fights, history=history,
        reference_date=REF,
    ).set_index("fighter")
    s = got[["current_title_score", "current_skill_score", "current_resume_score"]]
    scaled = (s / s[s > 0].mean().where(lambda m: m > 0, 1.0)) ** LEGACY_PART_POWER
    expected = PUBLIC_LEGACY_DISPLAY_SCALE * (
        LEGACY_ACHIEVEMENT_WEIGHT * scaled["current_title_score"]
        + (1 - LEGACY_ACHIEVEMENT_WEIGHT) * (
            LEGACY_QUALITY_SKILL_SHARE * scaled["current_skill_score"]
            + (1 - LEGACY_QUALITY_SKILL_SHARE) * scaled["current_resume_score"]
        )
    )
    assert got["current_score"].to_numpy() == pytest.approx(expected.to_numpy())


def test_a_champion_outranks_a_prospect_rated_above_everyone_it_beat():
    current, fights, history = _population()
    got = current_score_rows(
        current, rated_fights=fights, recorded_fights=fights, history=history,
        reference_date=REF,
    ).set_index("fighter")
    # The prospect's 2100 is capped at the 1700 opponent it beat: no skill above
    # the line, no contender win, no title.
    assert got.loc["Prospect", "current_best_win_mu"] == 1700.0
    assert got.loc["Prospect", "current_skill_score"] == 0.0
    assert got.loc["Prospect", "current_score"] == 0.0
    assert got.loc["Champ", "current_title_wins"] == 1
    assert got.loc["Champ", "current_score"] > got.loc["Contender", "current_score"] > 0


def test_wins_before_the_window_do_not_count():
    current, fights, history = _population()
    later = REF + pd.DateOffset(months=int(CURRENT_WINDOW_MONTHS))
    got = current_score_rows(
        current, rated_fights=fights, recorded_fights=fights, history=history,
        reference_date=later,
    ).set_index("fighter")
    assert (got["current_title_score"] == 0).all()
    assert (got["current_resume_score"] == 0).all()
    assert got.loc["Champ", "months_since_ufc"] > CURRENT_WINDOW_MONTHS


def test_no_published_skill_level_exceeds_the_best_win():
    from check_release import PUBLISHED_SNAPSHOT

    path = PUBLISHED_SNAPSHOT / "ratings_current.parquet"
    if not path.exists():
        pytest.skip("release snapshot not present")
    c = pd.read_parquet(path)
    assert "current_score" in c.columns
    level = pd.to_numeric(c["current_skill_level"], errors="coerce")
    best = pd.to_numeric(c["current_best_win_mu"], errors="coerce")
    # The exposure shrink pulls a level below 1750 up toward it, so a fighter
    # whose best win sits under the line can land a little above that win; the
    # skill part credits nothing there. Wherever skill scores, it is capped.
    scores = pd.to_numeric(c["current_skill_score"], errors="coerce") > 0
    assert not (scores & (level > best + 1e-9)).any()
    # A fighter who never beat a rated opponent is credited no skill at all.
    assert (c.loc[best.isna(), "current_skill_score"] == 0).all()
