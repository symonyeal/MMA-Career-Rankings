"""Lean Symon period and career-mass scores."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ratings.symon_score import (
    DEFAULT_CAREER_REFERENCE,
    MASS_COLUMNS,
    PERIOD_COLUMNS,
    career_mass_family,
    career_skill_mass,
    year_reference,
    symon_period_score,
    symon_prime_score,
)


def _history(fighter: str, dates: list[str], mu: list[float], **extra: object) -> pd.DataFrame:
    rows = pd.DataFrame({
        "fighter": fighter,
        "event_date": pd.to_datetime(dates),
        "event_name": [f"E{i:02d}" for i in range(len(dates))],
        "mu_whr": mu,
    })
    for name, value in extra.items():
        rows[name] = value
    return rows


def _row(frame: pd.DataFrame, fighter: str) -> pd.Series:
    return frame.loc[frame["fighter"].eq(fighter)].iloc[0]


def test_period_empty_and_parameter_guards_are_safe():
    empty = symon_period_score(pd.DataFrame(), window_days=30, min_fights=2)
    assert list(empty.columns) == PERIOD_COLUMNS
    assert empty.empty

    missing_mu = symon_period_score(
        pd.DataFrame({"fighter": ["A"]}), window_days=30, min_fights=2
    )
    assert list(missing_mu.columns) == PERIOD_COLUMNS
    assert missing_mu.empty

    with pytest.raises(ValueError):
        symon_period_score(pd.DataFrame(), window_days=-1, min_fights=2)
    with pytest.raises(ValueError):
        symon_period_score(pd.DataFrame(), window_days=30, min_fights=0)


def test_period_selects_the_highest_arithmetic_mean_and_audits_it():
    h = _history(
        "A",
        ["2020-01-01", "2020-01-02", "2020-02-01", "2020-02-02"],
        [1.0, 3.0, 8.0, 12.0],
    )
    out = symon_period_score(h, window_days=2, min_fights=2)
    row = _row(out, "A")

    assert list(out.columns) == PERIOD_COLUMNS
    assert row["raw_mean"] == pytest.approx(10.0)
    assert row["score"] == pytest.approx(10.0)
    assert row["shrinkage"] == pytest.approx(1.0)
    assert row["window_fights"] == 2
    assert row["window_start"] == pd.Timestamp("2020-02-01")
    assert row["window_end"] == pd.Timestamp("2020-02-02")
    assert row["within_var"] == pytest.approx(8.0)
    assert row["sampling_var"] == pytest.approx(4.0)


def test_only_latent_rating_is_evidence_no_hidden_bonus():
    dates = pd.date_range("2020-01-01", periods=8, freq="60D").strftime("%Y-%m-%d").tolist()
    plain = _history("A", dates, [1700.0] * 8)
    decorated = _history(
        "A",
        dates,
        [1700.0] * 8,
        opponent="Champion",
        result="WIN",
        is_title_fight=True,
        title_defense=True,
        activity_bonus=1_000_000.0,
    )

    a = symon_period_score(plain, window_days=1826, min_fights=8)
    b = symon_period_score(decorated, window_days=1826, min_fights=8)
    pd.testing.assert_frame_equal(a, b)
    assert a.iloc[0]["score"] == pytest.approx(1700.0)


def test_prime_gate_counts_actual_appearances_only():
    dates12 = pd.date_range("2015-01-01", periods=12, freq="240D").strftime("%Y-%m-%d").tolist()
    h12 = _history(
        "Title Fighter",
        dates12,
        [1900.0] * 12,
        is_title_fight=True,
        title_win=True,
        title_defense=True,
    )
    assert symon_prime_score(h12).empty

    h13 = _history(
        "Title Fighter",
        dates12 + ["2022-11-20"],
        [1900.0] * 13,
        is_title_fight=True,
        title_win=True,
        title_defense=True,
    )
    out = symon_prime_score(h13)
    assert _row(out, "Title Fighter")["window_fights"] == 13


def test_empirical_bayes_shrinkage_uses_mom_and_window_sampling_variance():
    dates = ["2020-01-01", "2020-01-02"]
    h = pd.concat([
        _history("A", dates, [0.0, 0.0]),
        _history("B", dates, [10.0, 10.0]),
        _history("C", dates, [10.0, 30.0]),
    ], ignore_index=True)
    out = symon_period_score(h, window_days=2, min_fights=2)

    # Var(raw means)=100, mean sampling variance=100/3, so tau^2=200/3.
    c = _row(out, "C")
    assert c["within_var"] == pytest.approx(200.0)
    assert c["sampling_var"] == pytest.approx(100.0)
    assert c["shrinkage"] == pytest.approx(0.4)
    assert c["score"] == pytest.approx(14.0)
    assert _row(out, "A")["score"] == pytest.approx(0.0)


def test_small_and_zero_variance_cohorts_are_finite():
    one = _history("A", ["2020-01-01", "2020-01-02"], [0.0, 20.0])
    one_out = symon_period_score(one, window_days=2, min_fights=2)
    assert _row(one_out, "A")["score"] == pytest.approx(10.0)
    assert _row(one_out, "A")["shrinkage"] == pytest.approx(1.0)

    equal = pd.concat([
        _history("A", ["2020-01-01", "2020-01-02"], [0.0, 20.0]),
        _history("B", ["2020-01-01", "2020-01-02"], [0.0, 20.0]),
    ], ignore_index=True)
    equal_out = symon_period_score(equal, window_days=2, min_fights=2)
    assert np.isfinite(equal_out[["score", "shrinkage"]].to_numpy()).all()
    assert equal_out["score"].tolist() == pytest.approx([10.0, 10.0])


def test_window_ties_prefer_more_fights_then_earlier_start_deterministically():
    more = _history(
        "More",
        ["2020-01-01", "2020-01-02", "2020-02-01", "2020-02-02", "2020-02-03"],
        [10.0] * 5,
    )
    earlier = _history(
        "Earlier",
        ["2020-01-01", "2020-01-02", "2020-02-01", "2020-02-02"],
        [20.0] * 4,
    )
    h = pd.concat([more, earlier], ignore_index=True)
    expected = symon_period_score(h, window_days=2, min_fights=2)
    shuffled = symon_period_score(
        h.sample(frac=1.0, random_state=19), window_days=2, min_fights=2
    )

    pd.testing.assert_frame_equal(expected, shuffled)
    assert _row(expected, "More")["window_fights"] == 3
    assert _row(expected, "More")["window_start"] == pd.Timestamp("2020-02-01")
    assert _row(expected, "Earlier")["window_fights"] == 2
    assert _row(expected, "Earlier")["window_start"] == pd.Timestamp("2020-01-01")


def test_configurable_input_names_and_fixed_prime_wrapper_window():
    dates = pd.date_range("2010-01-01", periods=13, freq="260D")
    h = pd.DataFrame({
        "name": "A",
        "date": dates,
        "card": [f"C{i}" for i in range(13)],
        "latent": 1800.0,
    })
    prime = symon_prime_score(
        h, mu_col="latent", fighter_col="name", date_col="date", event_col="card"
    )
    generic_period = symon_period_score(
        h,
        window_days=1826,
        min_fights=8,
        mu_col="latent",
        fighter_col="name",
        date_col="date",
        event_col="card",
    )
    assert _row(prime, "A")["window_fights"] == 13
    assert _row(generic_period, "A")["window_fights"] == 8


def test_career_skill_mass_is_one_field_relative_contribution_per_year():
    h = pd.concat([
        _history("A", ["2020-01-01", "2020-06-01", "2021-01-01"], [20.0, 30.0, 15.0]),
        _history("B", ["2020-01-01", "2021-01-01"], [10.0, 25.0]),
    ], ignore_index=True)
    # Pinned to the mean bar: this test is about the shape of the functional
    # (one contribution per active year), not about the production default.
    out = career_skill_mass(h, field_min_population=2, reference="mean")

    assert list(out.columns) == MASS_COLUMNS
    a = _row(out, "A")
    b = _row(out, "B")
    assert a["score"] == pytest.approx(7.5)
    assert a["active_years"] == 2
    assert a["contributing_years"] == 1
    assert a["peak_year_excess"] == pytest.approx(7.5)
    assert (a["first_year"], a["last_year"]) == (2020, 2021)
    assert b["score"] == pytest.approx(5.0)


def test_career_mass_year_gate_and_sparse_field_fallback():
    h = pd.concat([
        _history("A", ["2020-01-01", "2020-06-01", "2021-01-01"], [30.0, 30.0, 100.0]),
        _history("B", ["2020-01-01", "2020-06-01"], [10.0, 10.0]),
        _history("C", ["2021-01-01", "2021-06-01"], [20.0, 20.0]),
    ], ignore_index=True)
    out = career_skill_mass(
        h,
        min_appearances_per_year=2,
        field_min_population=3,
        reference="mean",
    )

    # A-2021 has only one appearance and is excluded. The remaining annual
    # means are 30, 10 and 20, so every sparse-year baseline falls back to 20.
    a = _row(out, "A")
    assert a["score"] == pytest.approx(10.0)
    assert a["active_years"] == 1
    assert (a["first_year"], a["last_year"]) == (2020, 2020)
    assert _row(out, "C")["score"] == pytest.approx(0.0)


def test_career_mass_empty_and_zero_excess_are_safe():
    empty = career_skill_mass(pd.DataFrame())
    assert list(empty.columns) == MASS_COLUMNS
    assert empty.empty

    h = pd.concat([
        _history("A", ["2020-01-01"], [10.0]),
        _history("B", ["2020-01-01"], [10.0]),
    ], ignore_index=True)
    out = career_skill_mass(h, field_min_population=2)
    assert out["score"].tolist() == pytest.approx([0.0, 0.0])
    assert out["peak_year_excess"].tolist() == pytest.approx([0.0, 0.0])


def test_hybrid_reference_spans_relative_to_absolute():
    """lam=1 must reproduce the contemporaneous bar; lam=0 must be a real move.

    The blend can only act through the positive-part clip, so the fixture needs
    a fighter whose years straddle the two bars -- and enough fighters per year
    to clear ``field_min_population``, or every year falls back to one global
    bar and the blend is trivially a no-op.
    """
    levels = {"A": [1700.0, 1750.0], "B": [1500.0, 1900.0], "C": [1400.0, 1450.0],
              "D": [1620.0, 1610.0], "E": [1560.0, 1580.0], "F": [1480.0, 1520.0]}
    history = pd.concat(
        [_history(name, ["2010-01-01", "2011-01-01"], mu) for name, mu in levels.items()],
        ignore_index=True,
    )

    relative = career_skill_mass(history, reference="mean")
    pd.testing.assert_frame_equal(relative, career_skill_mass(history, reference="hybrid:1.0"))

    absolute = career_skill_mass(history, reference="hybrid:0.0").set_index("fighter")["score"]
    assert not np.allclose(
        absolute.reindex(relative["fighter"]).to_numpy(), relative["score"].to_numpy()
    )

    with pytest.raises(ValueError):
        career_skill_mass(history, reference="hybrid:1.5")
    with pytest.raises(ValueError):
        career_skill_mass(history, reference="nonsense")


def test_the_production_bar_is_the_contender_line_not_the_field_mean():
    """The default decides what the all-time board measures, so pin it.

    At the field mean the positive part never binds for elite careers and the
    board silently ranks duration; at the contender line the clip does real work.
    """
    assert DEFAULT_CAREER_REFERENCE == "contender:60"

    levels = {"A": [1900.0, 1880.0], "B": [1700.0, 1690.0], "C": [1500.0, 1510.0],
              "D": [1480.0, 1470.0], "E": [1460.0, 1450.0], "F": [1440.0, 1430.0]}
    history = pd.concat(
        [_history(name, ["2020-01-01", "2021-01-01"], mu) for name, mu in levels.items()],
        ignore_index=True,
    )
    at_mean = career_skill_mass(history, reference="mean").set_index("fighter")
    at_bar = career_skill_mass(history, reference=0.9).set_index("fighter")

    # Mid-tier careers clear the mean but not the contender line.
    assert at_mean.loc["B", "contributing_years"] == 2
    assert at_bar.loc["B", "contributing_years"] == 0
    # The genuinely elite career still clears both.
    assert at_bar.loc["A", "contributing_years"] == 2


def test_career_mass_rank_is_a_shared_place_across_the_zero_tie():
    """Row order is a determinism tie-break, not a ranking.

    Everyone who never cleared the bar scores exactly zero, so they are tied.
    Printing them at consecutive ranks presented the ``repr(name)`` tie-break as
    a measurement -- the defect that put Forrest Griffin, Randy Couture and
    Wanderlei Silva at three different "ranks" on the same score of zero.
    """
    h = pd.concat([
        _history("A", ["2020-01-01", "2021-01-01"], [90.0, 90.0]),
        _history("B", ["2020-01-01", "2021-01-01"], [50.0, 50.0]),
        # Three fighters at the same low level: all below the bar, all tied.
        _history("Zeta", ["2020-01-01", "2021-01-01"], [10.0, 10.0]),
        _history("Alpha", ["2020-01-01", "2021-01-01"], [10.0, 10.0]),
        _history("Mid", ["2020-01-01", "2021-01-01"], [10.0, 10.0]),
    ], ignore_index=True)
    out = career_skill_mass(h, field_min_population=2, reference="mean")

    assert list(out.columns) == MASS_COLUMNS
    zero = out[out["score"] == 0.0]
    assert len(zero) == 3
    assert zero["rank"].nunique() == 1, "tied fighters must share one printed place"
    assert out["rank"].min() == 1
    # A "min" rank leaves the gap after the tie, and never exceeds the row count.
    assert out["rank"].max() == int(zero["rank"].iloc[0])
    assert out.loc[out["fighter"].eq("A"), "rank"].iloc[0] == 1


def test_career_mass_family_keeps_one_rank_per_reference():
    h = pd.concat([
        _history("A", ["2020-01-01", "2021-01-01"], [90.0, 90.0]),
        _history("B", ["2020-01-01", "2021-01-01"], [50.0, 50.0]),
        _history("C", ["2020-01-01", "2021-01-01"], [10.0, 10.0]),
    ], ignore_index=True)
    fam = career_mass_family(h, references=("mean", 0.5), field_min_population=2)

    assert list(fam.columns) == [*MASS_COLUMNS, "reference"]
    assert set(fam["reference"]) == {"mean", "0.5"}
    for reference, block in fam.groupby("reference"):
        assert block["rank"].min() == 1, reference
        # Rank is a function of score within the block, and only of score.
        by_score = block.sort_values("score", ascending=False)["rank"]
        assert by_score.is_monotonic_increasing, reference


def test_count_reference_names_a_count_not_a_fraction():
    """A quantile bar is population-relative; a count bar is not.

    0.9 was chosen because it was ~60 fighter-years out of ~578 in a modern
    UFC-only year. Admit a second corpus and the same quantile admits 245-419.
    ``count:n`` states the intent directly and survives the scope change.
    """
    h = pd.concat([
        _history(f"F{i}", ["2020-01-01"], [float(100 - i)]) for i in range(10)
    ], ignore_index=True)
    annual = pd.DataFrame({
        "fighter": [f"F{i}" for i in range(10)],
        "year": [2020] * 10,
        "annual_mean": [float(100 - i) for i in range(10)],
    })

    # The 3rd best of ten fighter-years scored 98.
    assert year_reference(annual, "count:3").loc[2020] == pytest.approx(98.0)
    assert year_reference(annual, "count:1").loc[2020] == pytest.approx(100.0)
    # A year thinner than the count has no local bar; career_skill_mass replaces
    # it with the whole-sample contender level rather than handing out a free
    # floor at that thin year's weakest fighter.
    assert np.isnan(year_reference(annual, "count:50").loc[2020])

    with pytest.raises(ValueError, match="at least one"):
        year_reference(annual, "count:0")

    board = career_skill_mass(h, field_min_population=2, reference="count:3")
    assert list(board.columns) == MASS_COLUMNS
    # Exactly three fighter-years sit at or above the third-best level.
    assert int((board["score"] > 0).sum()) == 2


def test_count_reference_sparse_year_uses_the_global_contender_level():
    dense_levels = [100.0, 98.0, 97.0, 96.0, 95.0, 94.0, 93.0, 92.0, 91.0, 90.0]
    dense = pd.concat([
        _history(f"Dense{i}", ["2020-01-01"], [level])
        for i, level in enumerate(dense_levels)
    ], ignore_index=True)
    thin = pd.concat([
        _history("Thin elite", ["1993-01-01"], [99.0]),
        _history("Thin low", ["1993-01-01"], [20.0]),
    ], ignore_index=True)

    board = career_skill_mass(
        pd.concat([dense, thin], ignore_index=True),
        field_min_population=1,
        reference="count:3",
    ).set_index("fighter")

    # Global third-best is 98: the elite pioneer contributes one point and the
    # weak pioneer contributes zero. Falling back to the thin-year minimum
    # would have handed the elite pioneer 79 cheap points.
    assert board.loc["Thin elite", "score"] == pytest.approx(1.0)
    assert board.loc["Thin low", "score"] == pytest.approx(0.0)


def test_contender_reference_is_a_decile_then_a_count_cap():
    small = pd.DataFrame({
        "fighter": [f"S{i}" for i in range(65)],
        "year": 1994,
        "annual_mean": np.arange(65, dtype=float),
    })
    mature = pd.DataFrame({
        "fighter": [f"M{i}" for i in range(1000)],
        "year": 2024,
        "annual_mean": np.arange(1000, dtype=float),
    })
    bars = year_reference(pd.concat([small, mature], ignore_index=True), "contender:60")

    # ceil(10% of 65) = seventh-best, not the 60th-best cheap floor.
    assert bars.loc[1994] == pytest.approx(58.0)
    # A mature field is capped at the 60th-best, not its 100th-best decile.
    assert bars.loc[2024] == pytest.approx(940.0)
