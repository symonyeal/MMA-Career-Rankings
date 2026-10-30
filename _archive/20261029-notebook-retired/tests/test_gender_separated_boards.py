"""No published ranking may mix the two bout-graph components.

Men's and women's bouts are disjoint: 0 of 80,697 rated bouts and 0 shared
opponents join them, so the offset between the two rating levels is set by the
prior and any mixed *ordering* is a reading of that prior. Separating the two
published board artifacts was not enough -- Prime, the snapshot's headline
prints, the bootstrap tiers and the notebook's top-N helper all ranked across
both. These pin every one of those surfaces.
"""
from __future__ import annotations

import inspect

import pandas as pd
import pytest

import build_boards
import build_top100_audit
import build_uncertainty
import refresh
from analysis.viz import top_n_table
from ratings.gender import (
    DEFAULT_GENDER,
    GENDER_GAUGE_NOTE,
    GENDER_SUFFIX,
    GENDERS,
    female_mask,
    partition_by_gender,
    select_component_fights,
    select_gender,
)
from ratings.rate_snapshot import _print_top


def _current() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "fighter": ["Ada", "Bea", "Cal", "Dan", "Eve"],
            "gender": ["F", "f ", "M", "m", None],
            "rating_periods": [20, 20, 20, 20, 20],
            "symon_prime_score": [2000.0, 1900.0, 1950.0, 1800.0, 1700.0],
            "public_legacy_score": [900.0, 800.0, 850.0, 700.0, 600.0],
            "mu_canonical": [1900.0, 1850.0, 1875.0, 1800.0, 1750.0],
        }
    )


# ---------------------------------------------------------------------------
# The rule itself


def test_partition_is_case_and_whitespace_insensitive():
    parts = partition_by_gender(_current())
    assert parts["F"]["fighter"].tolist() == ["Ada", "Bea"]
    assert parts["M"]["fighter"].tolist() == ["Cal", "Dan", "Eve"]


def test_unlabelled_fighters_are_not_asserted_into_the_womens_component():
    """A blank gender is an abstention by the inference, not a female label."""
    assert not female_mask(_current()).iloc[4]
    assert "Eve" in partition_by_gender(_current())["M"]["fighter"].tolist()


def test_a_frame_without_gender_is_one_population_not_a_false_split():
    parts = partition_by_gender(_current().drop(columns="gender"))
    assert set(parts) == {DEFAULT_GENDER}
    assert len(parts[DEFAULT_GENDER]) == 5


def test_select_gender_defaults_to_the_published_board_and_rejects_junk():
    assert select_gender(_current(), None)["fighter"].tolist() == ["Cal", "Dan", "Eve"]
    assert select_gender(_current(), "F")["fighter"].tolist() == ["Ada", "Bea"]
    with pytest.raises(ValueError, match="unknown gender"):
        select_gender(_current(), "both")


def test_the_two_components_partition_the_population_exactly():
    parts = partition_by_gender(_current())
    assert len(parts["M"]) + len(parts["F"]) == 5
    assert not set(parts["M"]["fighter"]) & set(parts["F"]["fighter"])


def test_the_mens_board_keeps_the_unsuffixed_name():
    """"All-time" and "Prime" without a gender mean men's."""
    assert GENDER_SUFFIX[DEFAULT_GENDER] == ""
    assert GENDER_SUFFIX["F"] == "_women"
    assert GENDERS[0] == DEFAULT_GENDER


# ---------------------------------------------------------------------------
# Every ranking surface


def test_prime_and_every_snapshot_headline_board_is_printed_per_component(capsys):
    """Prime is the one that matters most: it reads mu_whr with nothing damping it."""
    _print_top(
        _current(),
        rating_col="symon_prime_score",
        extra_cols=[],
        title="Prime",
        n=10,
        min_fights=0,
    )
    out = capsys.readouterr().out
    assert "Prime [men's]" in out
    assert "Prime [women's]" in out
    # The two tables must not be one table: Ada tops the women's board and must
    # not appear above Cal in a shared ordering.
    men_block = out.split("Prime [women's]")[0]
    assert "Ada" not in men_block and "Cal" in men_block


def test_snapshot_headline_boards_print_the_reason_beside_them(capsys):
    _print_top(
        _current(), rating_col="public_legacy_score", extra_cols=[],
        title="Legacy", n=10, min_fights=0,
    )
    assert GENDER_GAUGE_NOTE in capsys.readouterr().out


def test_a_snapshot_without_gender_prints_one_unlabelled_board(capsys):
    _print_top(
        _current().drop(columns="gender"), rating_col="symon_prime_score",
        extra_cols=[], title="Prime", n=10, min_fights=0,
    )
    out = capsys.readouterr().out
    assert "Prime [" not in out and "=== Prime ===" in out


def test_top_n_table_defaults_to_the_published_component():
    fighters = pd.DataFrame({
        "fighter": ["Ada", "Bea", "Cal", "Dan", "Eve"],
        "height_inches": [64] * 5, "weight_lb": [125] * 5,
        "reach_inches": [64] * 5, "stance": ["Orthodox"] * 5,
    })
    fights = pd.DataFrame({"event_date": [pd.Timestamp("2024-01-01")]})
    current = _current().assign(
        phi_canonical=50.0, mu_method=1800.0, mu_whr=1800.0,
        last_event_date=pd.Timestamp("2024-01-01"),
        symon_career_skill_mass=100.0,
    )
    default = top_n_table(current, fighters, fights, n=10, min_fights=0)
    assert set(default["fighter"]) == {"Cal", "Dan", "Eve"}
    womens = top_n_table(current, fighters, fights, n=10, min_fights=0, gender="F")
    assert set(womens["fighter"]) == {"Ada", "Bea"}
    mixed = top_n_table(current, fighters, fights, n=10, min_fights=0, gender=None)
    assert len(mixed) == 5


@pytest.mark.parametrize("module", [build_uncertainty, refresh])
def test_bootstrap_entry_points_scope_the_population(module):
    """A mixed interval asks whether a woman is separated from a man."""
    source = inspect.getsource(module)
    assert "select_gender" in source
    assert "select_component_fights" in source


def test_bootstrap_component_filter_excludes_unrelated_cards():
    population = pd.DataFrame({"fighter": ["Cal", "Dan"]})
    fights = pd.DataFrame(
        {
            "fight_url": ["m/1", "w/1", "mixed/1"],
            "fighter_a": ["Cal", "Ada", "Cal"],
            "fighter_b": ["Dan", "Bea", "Ada"],
        }
    )

    selected = select_component_fights(fights, population)

    assert selected["fight_url"].tolist() == ["m/1"]


def test_uncertainty_artifacts_are_named_per_component():
    source = inspect.getsource(build_uncertainty)
    assert "career_mass_uncertainty{suffix}.parquet" in source
    assert "career_mass_tiers{suffix}.parquet" in source
    assert "career_mass_uncertainty{suffix}.json" in source


def test_the_anchor_audit_scores_the_published_component():
    source = inspect.getsource(build_top100_audit)
    assert "gender_partition" in source


def test_build_boards_reuses_the_shared_rule_rather_than_its_own_copy():
    assert build_boards.gender_partition is partition_by_gender
    assert build_boards.BOARD_GENDER_SUFFIX is GENDER_SUFFIX
