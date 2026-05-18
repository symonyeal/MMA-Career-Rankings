"""Opponent-quality 5-year and 10-year period scores."""
from __future__ import annotations

import pandas as pd
import pytest

from ratings.constants import (
    FIVE_YEAR_PEAK_MIN_FIGHTS,
    HEADLINE_RESUME_BONUS_CAP,
    SUSTAINED_PEAK_MIN_FIGHTS,
)
from ratings.peaks import five_year_peak, peak_appearance_quality, sustained_peak


def _history_and_fights(
    *,
    fighter: str = "X",
    dates: list[str],
    fighter_mus: list[float],
    opponent_mus: list[float],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    fights = []
    prior_date = pd.Timestamp(dates[0]) - pd.Timedelta(days=500)
    for i, opp_mu in enumerate(opponent_mus):
        rows.append({
            "fighter": f"Opp{i+1}",
            "event_date": prior_date,
            "event_name": "PriorWarmup",
            "mu_canonical": opp_mu,
        })
    for i, (date_text, mu, _opp_mu) in enumerate(zip(dates, fighter_mus, opponent_mus)):
        date = pd.Timestamp(date_text)
        event_name = f"E{i+1}"
        opp = f"Opp{i+1}"
        rows.extend([
            {
                "fighter": fighter,
                "event_date": date,
                "event_name": event_name,
                "mu_canonical": mu,
            },
            {
                "fighter": opp,
                "event_date": date,
                "event_name": event_name,
                "mu_canonical": opponent_mus[i],
            },
        ])
        fights.append({
            "fight_url": f"u/{i+1}",
            "event_date": date,
            "event_name": event_name,
            "fighter_a": fighter,
            "fighter_b": opp,
            "winner": fighter,
            "is_draw": False,
            "method_class": "Decision - Unanimous",
            "method_score_winner": 0.85,
            "time_format": "3 Rnd (5-5-5)",
            "end_round": 3,
            "end_time_seconds": 300,
            "details_text": "30-27 30-27 30-27",
            "weight_class": "UFC Lightweight Bout",
            "is_title_fight": False,
        })
    return pd.DataFrame(rows), pd.DataFrame(fights)


def test_five_year_peak_requires_eight_ufc_fights():
    dates = pd.date_range("2020-01-01", periods=7, freq="180D").strftime("%Y-%m-%d").tolist()
    hist, fights = _history_and_fights(
        dates=dates,
        fighter_mus=[1800 + i for i in range(7)],
        opponent_mus=[1900] * 7,
    )
    fp = five_year_peak(
        hist, hist, fights,
        mu_col="mu_canonical", out_col="five_year_peak_mu_canonical",
    )
    assert pd.isna(fp[fp["fighter"] == "X"].iloc[0]["five_year_peak_mu_canonical"])
    assert FIVE_YEAR_PEAK_MIN_FIGHTS == 8

    hist8, fights8 = _history_and_fights(
        dates=pd.date_range("2020-01-01", periods=8, freq="180D").strftime("%Y-%m-%d").tolist(),
        fighter_mus=[1800 + i for i in range(8)],
        opponent_mus=[1900] * 8,
    )
    fp8 = five_year_peak(
        hist8, hist8, fights8,
        mu_col="mu_canonical", out_col="five_year_peak_mu_canonical",
    )
    assert fp8[fp8["fighter"] == "X"].iloc[0]["five_year_peak_mu_canonical"] > 1800


def test_sustained_period_qualifies_by_thirteen_ufc_fights_not_thirteen_quality_fights():
    dates = pd.date_range("2011-01-01", periods=13, freq="240D").strftime("%Y-%m-%d").tolist()
    hist, fights = _history_and_fights(
        dates=dates,
        fighter_mus=[2000] * 10 + [1600, 1600, 1600],
        opponent_mus=[1900] * 10 + [1500, 1500, 1500],
    )
    sp = sustained_peak(
        hist, hist, fights,
        mu_col="mu_canonical", out_col="sustained_peak_mu_canonical",
    )
    value = sp[sp["fighter"] == "X"].iloc[0]["sustained_peak_mu_canonical"]
    assert value > 1900.0
    assert SUSTAINED_PEAK_MIN_FIGHTS == 13


def test_title_dense_sustained_period_can_qualify_with_effective_count():
    dates = pd.date_range("2020-01-01", periods=10, freq="180D").strftime("%Y-%m-%d").tolist()
    hist, fights = _history_and_fights(
        dates=dates,
        fighter_mus=[2050] * 10,
        opponent_mus=[1900] * 10,
    )
    fights["weight_class"] = "UFC Lightweight Title Bout"
    fights["is_title_fight"] = True

    sp = sustained_peak(
        hist,
        hist,
        fights,
        mu_col="mu_canonical",
        out_col="sustained_peak_mu_canonical",
    )
    value = sp[sp["fighter"] == "X"].iloc[0]["sustained_peak_mu_canonical"]
    assert value > 1900.0


def test_sustained_period_counts_lower_quality_extra_appearances():
    """A single low-quality (1200 mu vs 1500 opp) appearance inside a window
    otherwise made of strong (2100 mu vs 1900 opp) appearances must pull the
    window score below the strong-only baseline.
    """
    dates = pd.date_range("2011-01-01", periods=14, freq="220D").strftime("%Y-%m-%d").tolist()
    mixed_hist, mixed_fights = _history_and_fights(
        dates=dates,
        fighter_mus=[2100] * 6 + [1200] + [2100] * 7,
        opponent_mus=[1900] * 6 + [1500] + [1900] * 7,
    )
    strong_only_hist, strong_only_fights = _history_and_fights(
        dates=dates,
        fighter_mus=[2100] * 14,
        opponent_mus=[1900] * 14,
    )
    mixed = float(
        sustained_peak(mixed_hist, mixed_hist, mixed_fights,
                       mu_col="mu_canonical",
                       out_col="sustained_peak_mu_canonical")
        .query("fighter == 'X'").iloc[0]["sustained_peak_mu_canonical"]
    )
    strong = float(
        sustained_peak(strong_only_hist, strong_only_hist, strong_only_fights,
                       mu_col="mu_canonical",
                       out_col="sustained_peak_mu_canonical")
        .query("fighter == 'X'").iloc[0]["sustained_peak_mu_canonical"]
    )
    assert mixed < strong


def test_loss_in_period_pulls_score_down():
    dates = pd.date_range("2015-01-01", periods=13, freq="220D").strftime("%Y-%m-%d").tolist()
    hist_win, fights_win = _history_and_fights(
        dates=dates,
        fighter_mus=[2050] * 13,
        opponent_mus=[1900] * 13,
    )
    hist_loss, fights_loss = _history_and_fights(
        dates=dates,
        fighter_mus=[2050] * 12 + [1980],
        opponent_mus=[1900] * 13,
    )
    fights_loss.loc[fights_loss.index[-1], "winner"] = fights_loss.loc[fights_loss.index[-1], "fighter_b"]

    win = sustained_peak(
        hist_win, hist_win, fights_win,
        mu_col="mu_canonical", out_col="score",
    )
    loss = sustained_peak(
        hist_loss, hist_loss, fights_loss,
        mu_col="mu_canonical", out_col="score",
    )
    assert float(loss[loss["fighter"] == "X"].iloc[0]["score"]) < float(
        win[win["fighter"] == "X"].iloc[0]["score"]
    )


def test_activity_bonus_rewards_deeper_quality_period():
    dates_thin = pd.date_range("2015-01-01", periods=13, freq="240D").strftime("%Y-%m-%d").tolist()
    hist_thin, fights_thin = _history_and_fights(
        dates=dates_thin,
        fighter_mus=[2050] * 13,
        opponent_mus=[1900] * 13,
    )
    dates_deep = pd.date_range("2015-01-01", periods=18, freq="160D").strftime("%Y-%m-%d").tolist()
    hist_deep, fights_deep = _history_and_fights(
        dates=dates_deep,
        fighter_mus=[2050] * 18,
        opponent_mus=[1900] * 18,
    )
    thin = sustained_peak(hist_thin, hist_thin, fights_thin, mu_col="mu_canonical", out_col="score")
    deep = sustained_peak(hist_deep, hist_deep, fights_deep, mu_col="mu_canonical", out_col="score")
    assert float(deep[deep["fighter"] == "X"].iloc[0]["score"]) > float(
        thin[thin["fighter"] == "X"].iloc[0]["score"]
    )


def test_headline_peak_adds_proven_resume_bonus_capped_at_envelope():
    """Headline column = raw peak + clip(rate * sum_opp_weight_in_window, 0, cap)."""
    dates = pd.date_range("2015-01-01", periods=14, freq="220D").strftime("%Y-%m-%d").tolist()
    hist, fights = _history_and_fights(
        dates=dates,
        fighter_mus=[2100] * 14,
        opponent_mus=[1900] * 14,
    )
    sp = sustained_peak(
        hist, hist, fights,
        mu_col="mu_canonical",
        out_col="sustained_peak_mu_canonical",
        headline_col="sustained_peak_headline_mu_canonical",
    )
    row = sp[sp["fighter"] == "X"].iloc[0]
    raw = float(row["sustained_peak_mu_canonical"])
    headline = float(row["sustained_peak_headline_mu_canonical"])
    assert headline >= raw
    assert headline - raw <= HEADLINE_RESUME_BONUS_CAP + 1e-6


def test_headline_peak_is_monotonic_in_resume_volume():
    """More quality fights in the window -> larger headline bonus, until cap."""
    dates_thin = pd.date_range("2015-01-01", periods=13, freq="240D").strftime("%Y-%m-%d").tolist()
    hist_thin, fights_thin = _history_and_fights(
        dates=dates_thin,
        fighter_mus=[2100] * 13,
        opponent_mus=[1900] * 13,
    )
    dates_thick = pd.date_range("2015-01-01", periods=20, freq="160D").strftime("%Y-%m-%d").tolist()
    hist_thick, fights_thick = _history_and_fights(
        dates=dates_thick,
        fighter_mus=[2100] * 20,
        opponent_mus=[2000] * 20,
    )
    sp_thin = sustained_peak(
        hist_thin, hist_thin, fights_thin,
        mu_col="mu_canonical",
        out_col="raw",
        headline_col="headline",
    )
    sp_thick = sustained_peak(
        hist_thick, hist_thick, fights_thick,
        mu_col="mu_canonical",
        out_col="raw",
        headline_col="headline",
    )
    thin = sp_thin[sp_thin["fighter"] == "X"].iloc[0]
    thick = sp_thick[sp_thick["fighter"] == "X"].iloc[0]
    thin_lift = float(thin["headline"] - thin["raw"])
    thick_lift = float(thick["headline"] - thick["raw"])
    assert thick_lift > thin_lift


def test_headline_peak_selects_best_headline_window_not_best_raw_window():
    dates = pd.date_range("2010-01-01", periods=14, freq="300D").strftime("%Y-%m-%d").tolist()
    hist, fights = _history_and_fights(
        dates=dates,
        fighter_mus=[2100] * 7 + [2050] * 7,
        opponent_mus=[1700] * 7 + [1900] * 7,
    )
    # Later appearances are slightly lower raw mu but title-rich enough that
    # the headline objective should choose the deeper title-resume window.
    fights.loc[7:, "weight_class"] = "UFC Lightweight Title Bout"
    fights.loc[7:, "is_title_fight"] = True

    raw_only = sustained_peak(
        hist,
        hist,
        fights,
        mu_col="mu_canonical",
        out_col="raw",
    )
    headline = sustained_peak(
        hist,
        hist,
        fights,
        mu_col="mu_canonical",
        out_col="raw",
        headline_col="headline",
    )
    raw_value = float(raw_only[raw_only["fighter"] == "X"].iloc[0]["raw"])
    headline_raw_value = float(headline[headline["fighter"] == "X"].iloc[0]["raw"])
    headline_value = float(headline[headline["fighter"] == "X"].iloc[0]["headline"])
    assert headline_value > raw_value
    assert headline_raw_value <= raw_value


def test_peak_opponent_quality_uses_actual_opponent_not_same_card_elite():
    prior_date = pd.Timestamp("2023-01-01")
    event_date = pd.Timestamp("2024-01-01")
    hist = pd.DataFrame([
        {"fighter": "LowOpp", "event_date": prior_date, "event_name": "Prior", "mu_canonical": 1500.0},
        {"fighter": "Elite", "event_date": prior_date, "event_name": "Prior", "mu_canonical": 2300.0},
        {"fighter": "Other", "event_date": prior_date, "event_name": "Prior", "mu_canonical": 1500.0},
        {"fighter": "X", "event_date": event_date, "event_name": "Card", "mu_canonical": 1700.0},
        {"fighter": "LowOpp", "event_date": event_date, "event_name": "Card", "mu_canonical": 1450.0},
        {"fighter": "Elite", "event_date": event_date, "event_name": "Card", "mu_canonical": 2310.0},
        {"fighter": "Other", "event_date": event_date, "event_name": "Card", "mu_canonical": 1490.0},
    ])
    fights = pd.DataFrame([
        {
            "fight_url": "u/1", "event_date": event_date, "event_name": "Card",
            "fighter_a": "X", "fighter_b": "LowOpp", "winner": "X",
            "is_draw": False, "method_class": "Decision - Unanimous",
            "method_score_winner": 0.85, "time_format": "3 Rnd (5-5-5)",
            "end_round": 3, "end_time_seconds": 300, "details_text": "30-27 30-27 30-27",
            "weight_class": "UFC Lightweight Bout", "is_title_fight": False,
        },
        {
            "fight_url": "u/2", "event_date": event_date, "event_name": "Card",
            "fighter_a": "Elite", "fighter_b": "Other", "winner": "Elite",
            "is_draw": False, "method_class": "KO/TKO",
            "method_score_winner": 1.0, "time_format": "3 Rnd (5-5-5)",
            "end_round": 1, "end_time_seconds": 60, "details_text": "",
            "weight_class": "UFC Lightweight Bout", "is_title_fight": False,
        },
    ])
    quality = peak_appearance_quality(fights, hist)
    x = quality[quality["fighter"] == "X"].iloc[0]
    assert x["opponent"] == "LowOpp"
    assert x["opponent_prefight_mu"] == pytest.approx(1500.0)
    assert x["opp_weight"] == pytest.approx(0.0)
