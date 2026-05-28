from __future__ import annotations

import pandas as pd

from ratings.division_resume import division_resume_rows, primary_division_rows


def _rows(fighter: str, division: str, n: int, mu: float, *, title_n: int = 0) -> tuple[list[dict], list[dict]]:
    hist = []
    apps = []
    for i in range(n):
        date = pd.Timestamp("2020-01-01") + pd.Timedelta(days=90 * i)
        event = f"{division}-{i}"
        hist.append({"fighter": fighter, "event_date": date, "event_name": event, "mu_whr": mu})
        is_title = i < title_n
        apps.append({
            "fighter": fighter,
            "event_date": date,
            "event_name": event,
            "division": division,
            "opp_weight": 1.5 if is_title else 0.8,
            "opponent_quality_level": 0.8 if is_title else 0.5,
            "actual_score": 1.0,
            "opponent_prefight_division_rank": 1 if is_title else 8,
            "opponent_prefight_p4p_rank": 5 if is_title else pd.NA,
            "opponent_entered_as_champion": bool(is_title),
            "opponent_entered_as_interim_champion": False,
            "fighter_entered_as_champion": bool(is_title and i > 0),
            "fighter_entered_as_interim_champion": False,
            "is_championship_bout": bool(is_title),
            "is_interim_title_bout": False,
        })
    return hist, apps


def _bout(
    fighter: str,
    date: str,
    division: str,
    mu: float = 1800.0,
    *,
    score: float = 1.0,
    title: bool = False,
    entered_champ: bool = False,
) -> tuple[dict, dict]:
    """One chronological bout for hand-built career scenarios."""
    ts = pd.Timestamp(date)
    event = f"{fighter}-{date}"
    hist = {"fighter": fighter, "event_date": ts, "event_name": event, "mu_whr": mu}
    app = {
        "fighter": fighter,
        "event_date": ts,
        "event_name": event,
        "division": division,
        "opp_weight": 1.5 if title else 0.8,
        "opponent_quality_level": 0.8 if title else 0.5,
        "actual_score": score,
        "opponent_prefight_division_rank": 1 if title else 8,
        "opponent_prefight_p4p_rank": 5 if title else pd.NA,
        "opponent_entered_as_champion": bool(title and not entered_champ),
        "opponent_entered_as_interim_champion": False,
        "fighter_entered_as_champion": bool(entered_champ),
        "fighter_entered_as_interim_champion": False,
        "is_championship_bout": bool(title),
        "is_interim_title_bout": False,
    }
    return hist, app


def _labels(bouts: list[tuple[dict, dict]], fighter: str) -> tuple[str, str]:
    """Return (career_division, current_division) for ``fighter``."""
    hist = pd.DataFrame([h for h, _ in bouts])
    apps = pd.DataFrame([a for _, a in bouts])
    resume = division_resume_rows(hist, apps)
    primary = primary_division_rows(resume)
    row = primary[primary["fighter"].eq(fighter)].iloc[0]
    return row["career_division"], row["current_division"]


def test_title_win_in_new_division_moves_current_but_not_career():
    # Topuria-like: long featherweight reign, then vacates and wins lightweight.
    # Career stays FW (5 FW vs 1 LW); current jumps to LW on the title win.
    bouts = [
        _bout("Mover", "2021-01-01", "Featherweight"),
        _bout("Mover", "2021-07-01", "Featherweight"),
        _bout("Mover", "2022-01-01", "Featherweight"),
        _bout("Mover", "2023-02-01", "Featherweight", title=True),
        _bout("Mover", "2024-02-01", "Featherweight", title=True, entered_champ=True),
        _bout("Mover", "2025-06-01", "Lightweight", title=True),
    ]
    career, current = _labels(bouts, "Mover")
    assert career == "Featherweight"
    assert current == "Lightweight"


def test_title_loss_up_a_class_relocates_neither_label():
    # Volkanovski-like: featherweight champion who lost two lightweight title shots.
    # Both career and current stay FW — losing a belt fight is not a permanent move.
    fw_dates = ["2018-01-01", "2018-07-01", "2019-01-01", "2019-07-01",
                "2020-01-01", "2021-01-01", "2022-01-01", "2023-07-01"]
    bouts = [
        _bout("Champ", d, "Featherweight", title=(i >= 4), entered_champ=(i >= 5))
        for i, d in enumerate(fw_dates)
    ]
    bouts += [
        _bout("Champ", "2023-02-11", "Lightweight", score=0.0, title=True),
        _bout("Champ", "2023-10-21", "Lightweight", score=0.0, title=True),
    ]
    career, current = _labels(bouts, "Champ")
    assert career == "Featherweight"
    assert current == "Featherweight"


def test_dual_division_champ_current_is_most_recent_belt():
    # McGregor-like: 7 featherweight (2 title wins), 4 lightweight (1 title
    # win), 3 welterweight non-title cameos. Career is FW (majority); current
    # is LW (most recent belt won). Welterweight cameos never become a label.
    bouts = [
        _bout("Dual", "2013-04-06", "Featherweight"),
        _bout("Dual", "2013-08-17", "Featherweight"),
        _bout("Dual", "2014-07-19", "Featherweight"),
        _bout("Dual", "2014-09-27", "Featherweight"),
        _bout("Dual", "2015-01-18", "Featherweight"),
        _bout("Dual", "2015-07-11", "Featherweight", title=True),
        _bout("Dual", "2015-12-12", "Featherweight", title=True),
        _bout("Dual", "2016-03-05", "Welterweight", score=0.0),
        _bout("Dual", "2016-08-20", "Welterweight"),
        _bout("Dual", "2016-11-12", "Lightweight", title=True),
        _bout("Dual", "2018-10-06", "Lightweight", score=0.0, title=True),
        _bout("Dual", "2020-01-18", "Welterweight"),
        _bout("Dual", "2021-01-23", "Lightweight", score=0.0),
        _bout("Dual", "2021-07-10", "Lightweight", score=0.0),
    ]
    career, current = _labels(bouts, "Dual")
    assert career == "Featherweight"
    assert current == "Lightweight"


def test_one_fight_in_other_division_does_not_move_career():
    # GSP-like: long welterweight career, single middleweight title win cameo.
    # Career stays WW; current jumps to MW on that title win.
    bouts = [_bout("GSP", f"201{i}-01-01", "Welterweight", title=(i >= 6))
             for i in range(0, 7)]
    bouts += [_bout("GSP", "2017-11-04", "Middleweight", title=True)]
    career, current = _labels(bouts, "GSP")
    assert career == "Welterweight"
    assert current == "Middleweight"


def test_catch_weight_is_never_a_label():
    bouts = [
        _bout("Catcher", "2021-01-01", "Catch Weight", score=1.0),
        _bout("Catcher", "2021-07-01", "Lightweight"),
        _bout("Catcher", "2022-01-01", "Lightweight"),
    ]
    career, current = _labels(bouts, "Catcher")
    assert career == "Lightweight"
    assert current == "Lightweight"


def test_non_champion_no_belt_no_relocation():
    # Long lightweight tenure, then two recent welterweight bouts, no titles.
    # No belt change so neither label moves.
    bouts = [_bout("Journeyman", f"2018-0{1 + i}-01", "Lightweight", score=1.0) for i in range(6)]
    bouts += [
        _bout("Journeyman", "2024-06-01", "Welterweight"),
        _bout("Journeyman", "2025-01-01", "Welterweight"),
    ]
    career, current = _labels(bouts, "Journeyman")
    assert career == "Lightweight"
    assert current == "Lightweight"


def test_division_resume_does_not_loan_legacy_across_weight_classes():
    hist_a_lhw, app_a_lhw = _rows("Two Division Star", "Light Heavyweight", 10, 1900.0, title_n=8)
    hist_a_hw, app_a_hw = _rows("Two Division Star", "Heavyweight", 2, 1900.0, title_n=2)
    hist_hw, app_hw = _rows("Heavyweight Reign", "Heavyweight", 12, 1840.0, title_n=8)

    resume = division_resume_rows(
        pd.DataFrame(hist_a_lhw + hist_a_hw + hist_hw),
        pd.DataFrame(app_a_lhw + app_a_hw + app_hw),
    )

    heavyweight = resume[resume["division"].eq("Heavyweight")].sort_values(
        "division_score_whr",
        ascending=False,
    )
    assert heavyweight.iloc[0]["fighter"] == "Heavyweight Reign"
    assert int(heavyweight[heavyweight["fighter"].eq("Two Division Star")].iloc[0]["division_fights"]) == 2

    primary = primary_division_rows(resume)
    star = primary[primary["fighter"].eq("Two Division Star")].iloc[0]
    # Career is the long LHW tenure (no legacy loan to the HW cameo).
    assert star["career_division"] == "Light Heavyweight"
