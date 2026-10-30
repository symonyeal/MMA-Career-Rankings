"""The published WHR fit must be ONE model everywhere it is run.

The snapshot fit, the prequential acceptance gate and the bootstrap refits are
three separate call sites of :func:`ratings.whr.run_whr`. If they disagree about
the winner-score column, the gate certifies a model the board does not use and
the intervals describe a board nobody published. That has a shape in this repo
already -- an optional argument silently changing a published number -- and it
is what :mod:`tests.test_title_division_bar` guards for the division bar.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ratings import bootstrap
from ratings import prequential as PQ
from ratings.constants import WHR_WINNER_SCORE_COL
from ratings.whr import production_score_kwargs, run_whr


def _fights(n: int = 24) -> pd.DataFrame:
    dates = pd.date_range("2015-01-01", periods=n, freq="90D")
    return pd.DataFrame(
        {
            "fight_url": [f"u/{i}" for i in range(n)],
            "event_date": dates,
            "event_name": [f"E{i}" for i in range(n)],
            "fighter_a": ["A" if i % 2 else "B" for i in range(n)],
            "fighter_b": ["C" if i % 2 else "D" for i in range(n)],
            "winner": ["A" if i % 2 else "B" for i in range(n)],
            "is_draw": [False] * n,
            "method_score_winner": [1.0 if i % 3 else 0.9 for i in range(n)],
        }
    )


def test_production_score_kwargs_names_the_constant():
    kwargs = production_score_kwargs(_fights())
    assert kwargs == {"winner_score_col": WHR_WINNER_SCORE_COL}


def test_production_score_kwargs_refuses_to_fall_back_silently():
    without = _fights().drop(columns="method_score_winner")
    with pytest.raises(ValueError, match="winner-score column"):
        production_score_kwargs(without)


def test_production_score_kwargs_is_empty_when_the_model_is_binary(monkeypatch):
    monkeypatch.setattr("ratings.whr.WHR_WINNER_SCORE_COL", None)
    assert production_score_kwargs(_fights().drop(columns="method_score_winner")) == {}


def test_run_whr_still_defaults_to_binary_scoring():
    """A staged audit column must not change the model just by being present."""
    fights = _fights()
    graded = run_whr(fights, **production_score_kwargs(fights))
    binary = run_whr(fights)
    merged = graded.merge(
        binary, on=["fighter", "event_date"], suffixes=("_graded", "_binary")
    )
    assert not merged.empty
    assert not np.allclose(merged["mu_whr_graded"], merged["mu_whr_binary"])


def test_a_finish_moves_the_winner_further_than_a_split_decision():
    """The direction the ledger claims: a cleaner win is stronger evidence."""
    base = _fights()
    finishes = base.assign(method_score_winner=1.0)
    decisions = base.assign(method_score_winner=0.9)
    col = {"winner_score_col": "method_score_winner"}
    top = lambda frame: (
        run_whr(frame, **col)
        .sort_values("event_date")
        .groupby("fighter")
        .tail(1)
        .set_index("fighter")["mu_whr"]
    )
    assert top(finishes)["A"] > top(decisions)["A"]


def test_published_prequential_whr_variants_use_the_method_score():
    whr_variants = [v for v in PQ.default_variants() if v.engine == "whr"]
    assert whr_variants, "the acceptance gate has no WHR variant to run"
    assert all(v.use_method_score for v in whr_variants)
    assert all(not v.use_quality_score for v in whr_variants)


def test_one_winner_score_column_per_fit():
    variant = PQ.Variant(
        "clash", engine="whr", use_quality_score=True, use_method_score=True
    )
    inputs = PQ.Inputs(
        snapshot_dir=None,
        fights=_fights(),
        history=pd.DataFrame(),
        weights={},
        dominance_level=pd.DataFrame(),
        odds=None,
        quality_score=pd.DataFrame(columns=["fight_url", "quality_score_winner"]),
        birth_dates={},
    )
    with pytest.raises(ValueError, match="mutually exclusive"):
        PQ.whr_predictions(inputs, variant, pd.DataFrame())


def test_bootstrap_refits_the_published_functional_in_one_component(tmp_path, monkeypatch):
    """A women's interval must exclude men's bouts and keep the score's bar and grading."""
    from ratings.symon_score import DEFAULT_DIVISION_REFERENCE, DEFAULT_HINGE_SPREAD_FRACTION

    population = pd.DataFrame({
        "fighter": ["A", "B", "C", "D"], "gender": ["F", "F", "M", "M"],
        "career_division": ["Flyweight"] * 4, "rating_periods": [20, 2, 20, 20],
    })
    population.to_parquet(tmp_path / "ratings_current.parquet", index=False)
    fights = _fights().iloc[:2].copy()
    fights["fighter_a"], fights["fighter_b"] = ["A", "C"], ["B", "D"]
    monkeypatch.setattr(bootstrap, "load_fight_table", lambda *a, **kw: fights)
    monkeypatch.setattr(bootstrap, "load_birth_dates", lambda *a: {"A": pd.Timestamp("1990-01-01")})

    def refit(selected, **kwargs):
        assert selected["fighter_a"].tolist() == ["A"]
        assert kwargs["eligible_fighters"] == {"A"}
        assert kwargs["whr_kwargs"]["winner_score_col"] == WHR_WINNER_SCORE_COL
        assert kwargs["whr_kwargs"]["age_drift"] is True
        mass = kwargs["mass_kwargs"]
        assert mass["reference"] == "contender:9"
        assert mass["divisions"].to_dict() == {"A": "Women's Flyweight", "B": "Women's Flyweight"}
        assert mass["division_reference"] == DEFAULT_DIVISION_REFERENCE
        assert mass["hinge_spread_fraction"] == DEFAULT_HINGE_SPREAD_FRACTION
        assert kwargs["replicates"] == 3 and kwargs["seed"] == 8 and kwargs["return_draws"]
        return "board", "draws"

    monkeypatch.setattr(bootstrap, "career_mass_bootstrap", refit)
    assert bootstrap.bootstrap_snapshot(
        tmp_path, gender="F", reference="contender:9", replicates=3, seed=8,
    ) == ("board", "draws")
