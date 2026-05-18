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
    assert star["primary_division"] == "Light Heavyweight"
