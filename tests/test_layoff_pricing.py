"""Pricing a win over a fighter who had been away.

The rating charges elapsed time at an age rate and nothing else, so ageing while
competing and ageing while idle cost the same: the published trajectory
separates the Stipe Miocic that Daniel Cormier fought (35, active) from the one
Jon Jones fought (42, 44 months out) by 34 rating points.

This corrects the price of the win, never the opponent's rating. Putting the
charge in the WHR transition prior was measured and refused -- see
``docs/DECISIONS.md`` and the module docstring.
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ratings.layoff import (
    MAX_EXCESS_TURNAROUNDS,
    OPPONENT_LAYOFF_ELO_PER_TURNAROUND,
    appearance_layoff_excess,
    attach_opponent_layoff,
    discount_opponent_mu,
    era_normal_turnaround,
)


def _schedule(fighter: str, start: str, cadence_days: int, n: int, then_gap: int | None = None):
    day = pd.Timestamp(start)
    rows = []
    for _ in range(n):
        rows.append({"fighter": fighter, "event_date": day})
        day = day + pd.Timedelta(days=cadence_days)
    if then_gap is not None:
        rows.append({"fighter": fighter, "event_date": rows[-1]["event_date"]
                     + pd.Timedelta(days=then_gap)})
    return rows


def _field(year: int, cadence_days: int, n_fighters: int = 40, bouts: int = 10):
    rows = []
    for f in range(n_fighters):
        rows.extend(_schedule(f"bg{f}", f"{year}-01-01", cadence_days, bouts))
    return pd.DataFrame(rows)


# --- the era normal ---------------------------------------------------------

def test_the_era_normal_is_read_off_the_schedule():
    field = _field(2015, 180)
    normal = era_normal_turnaround(field)
    assert normal.notna().all()
    assert normal.iloc[0] == pytest.approx(180.0, abs=1.0)


def test_a_thin_year_borrows_the_corpus_normal_rather_than_inventing_one():
    """One transition in a year must not define that year's normal."""
    rows = _field(2015, 180).to_dict("records")
    rows.extend(_schedule("loner", "1990-01-01", 30, 2))
    normal = era_normal_turnaround(pd.DataFrame(rows))
    assert normal.get(1990, 180.0) > 30.0


# --- the excess -------------------------------------------------------------

def test_a_fighter_on_the_era_cadence_is_charged_nothing():
    field = _field(2015, 180)
    excess = appearance_layoff_excess(field)
    assert excess["layoff_excess"].max() == pytest.approx(0.0, abs=1e-9)


def test_a_first_bout_is_not_an_absence():
    field = _field(2015, 180)
    excess = appearance_layoff_excess(field)
    first = excess.sort_values("event_date").groupby("fighter").head(1)
    assert (first["layoff_excess"] == 0).all()


def test_a_long_absence_is_charged_in_era_normal_turnarounds():
    rows = _field(2015, 180).to_dict("records")
    rows.extend(_schedule("returner", "2015-01-01", 180, 4, then_gap=180 * 4))
    excess = appearance_layoff_excess(pd.DataFrame(rows))
    got = excess[excess["fighter"].eq("returner")]["layoff_excess"].max()
    assert got == pytest.approx(3.0, abs=0.15)


def test_the_same_absence_costs_the_same_in_any_era():
    """A fixed grace in days is an era penalty; a turnaround multiple is not.

    The 75th-percentile gap ran 112 days in 1995 and 392 in 2020, so a fixed
    270-day grace charged a 2020-era transition 4.8x what it charged a 1995-era
    one.
    """
    busy = _field(1996, 70).to_dict("records")
    busy.extend(_schedule("busy_era", "1996-01-01", 70, 4, then_gap=70 * 4))
    sparse = _field(2018, 240).to_dict("records")
    sparse.extend(_schedule("sparse_era", "2018-01-01", 240, 4, then_gap=240 * 4))
    a = appearance_layoff_excess(pd.DataFrame(busy))
    b = appearance_layoff_excess(pd.DataFrame(sparse))
    fast = a[a["fighter"].eq("busy_era")]["layoff_excess"].max()
    slow = b[b["fighter"].eq("sparse_era")]["layoff_excess"].max()
    assert fast == pytest.approx(slow, abs=0.2)


def test_the_excess_is_capped():
    rows = _field(2015, 180).to_dict("records")
    rows.extend(_schedule("gone", "2015-01-01", 180, 3, then_gap=180 * 40))
    excess = appearance_layoff_excess(pd.DataFrame(rows))
    assert excess["layoff_excess"].max() <= MAX_EXCESS_TURNAROUNDS


# --- the discount -----------------------------------------------------------

def test_no_absence_leaves_the_price_untouched():
    got = discount_opponent_mu(pd.Series([1993.0]), pd.Series([0.0]))
    assert float(got.iloc[0]) == pytest.approx(1993.0)


def test_the_discount_is_additive_on_the_rating_scale():
    got = discount_opponent_mu(pd.Series([1936.0]), pd.Series([2.52]))
    assert float(got.iloc[0]) == pytest.approx(
        1936.0 + 2.52 * OPPONENT_LAYOFF_ELO_PER_TURNAROUND
    )


def test_a_missing_excess_is_read_as_no_absence():
    got = discount_opponent_mu(pd.Series([1900.0]), pd.Series([np.nan]))
    assert float(got.iloc[0]) == pytest.approx(1900.0)


def test_attaching_the_discount_does_not_duplicate_rows():
    rows = _field(2015, 180).to_dict("records")
    rows.extend(_schedule("returner", "2015-01-01", 180, 4, then_gap=180 * 4))
    appearances = pd.DataFrame(rows)
    priced = pd.DataFrame({
        "fighter": ["winner"] * 3,
        "opponent": ["returner", "bg0", "bg1"],
        "event_date": [
            appearances[appearances["fighter"].eq("returner")]["event_date"].max(),
            pd.Timestamp("2015-07-01"),
            pd.Timestamp("2016-01-01"),
        ],
        "opponent_mu": [1936.0, 1800.0, 1800.0],
    })
    out = attach_opponent_layoff(priced, appearances)
    assert len(out) == len(priced)
    assert out.loc[0, "opponent_mu"] < 1936.0
    assert out.loc[1, "opponent_mu"] == pytest.approx(1800.0)


def test_the_rate_is_a_discount_not_a_bonus():
    assert OPPONENT_LAYOFF_ELO_PER_TURNAROUND < 0


def test_the_charge_is_not_written_back_to_the_opponents_rating():
    """The whole point of pricing here rather than in the model.

    A rating-layer charge inflated pre-layoff peaks -- Sean Sherk 1927 -> 2124
    -- because a symmetric transition prior reads "declined" as "used to be
    better". Nothing here may touch a rating.
    """
    rows = _field(2015, 180).to_dict("records")
    rows.extend(_schedule("returner", "2015-01-01", 180, 4, then_gap=180 * 4))
    appearances = pd.DataFrame(rows)
    before = appearances.copy()
    priced = pd.DataFrame({
        "fighter": ["w"], "opponent": ["returner"],
        "event_date": [appearances[appearances["fighter"].eq("returner")]["event_date"].max()],
        "opponent_mu": [1936.0],
    })
    attach_opponent_layoff(priced, appearances)
    pd.testing.assert_frame_equal(appearances, before)


# --- the quoted Stipe figures, held to the snapshot ------------------------

SNAPSHOT = Path(__file__).resolve().parents[1] / "data" / "snapshots" / "2026-08-13"
DECISIONS = Path(__file__).resolve().parents[1] / "docs" / "DECISIONS.md"

CORMIER_WIN = pd.Timestamp("2018-07-07")
JONES_WIN = pd.Timestamp("2024-11-16")


def _whr_history():
    path = SNAPSHOT / "ratings_history_whr.parquet"
    if not path.exists():
        pytest.skip("snapshot artifact not present: ratings_history_whr.parquet")
    return pd.read_parquet(path)


def _priced_at(mu: pd.Series, when: pd.Timestamp) -> float:
    """The rating the ledger prices a bout at: the last one strictly before it."""
    before = mu[mu.index < when]
    return float(before.iloc[-1])


def test_the_quoted_stipe_figures_match_the_snapshot():
    """The decision register quotes both halves of the Stipe example.

    This is the one canonical explanation of the policy. Both figures went stale
    once already, so a refit must fail here rather than in the prose.
    """
    if not DECISIONS.exists():
        pytest.skip("docs/DECISIONS.md not present")
    text = DECISIONS.read_text(encoding="utf-8")

    quoted_discount = re.search(r"priced (\d+) points below", text)
    quoted_gap = re.search(r"beat\s+from\s+the one Jones beat by (\d+)", text)
    assert quoted_discount, "DECISIONS.md no longer quotes the layoff discount"
    assert quoted_gap, "DECISIONS.md no longer quotes the rating gap"

    history = _whr_history()
    excess = appearance_layoff_excess(history[["fighter", "event_date"]])
    excess = excess[excess["fighter"].eq("Stipe Miocic")].set_index("event_date")
    charged = float(excess.loc[JONES_WIN, "layoff_excess"])
    discount = charged * -OPPONENT_LAYOFF_ELO_PER_TURNAROUND

    mu = (
        history[history["fighter"].eq("Stipe Miocic")]
        .sort_values("event_date")
        .set_index("event_date")["mu_whr"]
    )
    gap = _priced_at(mu, CORMIER_WIN) - _priced_at(mu, JONES_WIN)

    assert round(discount) == int(quoted_discount.group(1))
    assert round(gap) == int(quoted_gap.group(1))
    assert discount > gap, (
        "the example only makes its point if the layoff charge exceeds what the "
        "rating trajectory charged on its own"
    )
