"""Gender is a property of the bout graph, not of one bout's billing.

Every test here fails against the rule that shipped before 2026-08-26, which
read ``weight_class.startswith("Women's")`` on a fighter's most recent bout. On
the 2026-08-13 snapshot that rule found 247 of 1,752 women and left 663 bouts in
which the corpus believed a man had fought a woman.
"""
from __future__ import annotations

import pandas as pd
import pytest

from ratings.legacy_resume import _division_labels
from ratings.performance_adjustment import womens_division_label
from ratings.rate_snapshot import (
    _attach_recent_division_gender,
    _female_by_bout_graph,
    _gender_isolated_prime_score,
)


def _bout(date: str, a: str, b: str, weight_class: object) -> dict:
    return {
        "event_date": date,
        "event_name": f"{a} vs {b}",
        "fighter_a": a,
        "fighter_b": b,
        "weight_class": weight_class,
    }


@pytest.fixture
def corpus() -> pd.DataFrame:
    """One women's component billed three ways, one men's component.

    "Rin" never fights a bout billed "Women's ...", and her LAST bout is billed
    with a bare men's-sounding label -- the exact shape the old rule got wrong.
    """
    return pd.DataFrame([
        # women's component: only the first bout carries the prefix
        _bout("2014-01-01", "Ayaka", "Seika", "Women's Strawweight Bout"),
        _bout("2015-01-01", "Seika", "Rin", None),
        _bout("2016-01-01", "Rin", "Mei", "Flyweight"),
        _bout("2017-01-01", "Mei", "Ayaka", "108lb Catchweight"),
        _bout("2018-01-01", "Rin", "Ayaka", "Featherweight"),
        # men's component, disjoint from the above
        _bout("2015-06-01", "Jon", "Daniel", "Light Heavyweight Bout"),
        _bout("2016-06-01", "Daniel", "Stipe", "Heavyweight Bout"),
        _bout("2017-06-01", "Stipe", "Jon", "Heavyweight Bout"),
    ])


def _prepared(corpus: pd.DataFrame) -> pd.DataFrame:
    from ratings.performance_adjustment import normalize_division_label

    f = corpus.copy()
    f["event_date"] = pd.to_datetime(f["event_date"])
    f["recent_division"] = f["weight_class"].map(normalize_division_label)
    return f


def test_a_woman_is_found_even_when_no_bout_of_hers_is_billed_womens(corpus):
    """Rin's own bouts are billed None / Flyweight / Featherweight.

    The last-bout rule calls her a man. The graph does not: she is two edges
    from a bout the corpus does label.
    """
    female = _female_by_bout_graph(_prepared(corpus))
    assert "Rin" in female
    assert {"Ayaka", "Seika", "Mei"} <= female


def test_the_mens_component_is_untouched(corpus):
    female = _female_by_bout_graph(_prepared(corpus))
    assert female.isdisjoint({"Jon", "Daniel", "Stipe"})


def test_no_bout_is_left_between_a_man_and_a_woman(corpus):
    """The defect the old rule produced, stated as its own assertion."""
    female = _female_by_bout_graph(_prepared(corpus))
    a = corpus["fighter_a"].isin(female)
    b = corpus["fighter_b"].isin(female)
    assert int((a ^ b).sum()) == 0


def test_a_mens_billing_majority_keeps_a_component_male(corpus):
    """One stray women's billing inside the men's component must not flip it.

    Guards the case a genuine intergender bout would create in a later snapshot.
    """
    stray = pd.concat([
        corpus,
        pd.DataFrame([_bout("2019-06-01", "Jon", "Daniel", "Women's Bantamweight Bout")]),
    ], ignore_index=True)
    female = _female_by_bout_graph(_prepared(stray))
    assert female.isdisjoint({"Jon", "Daniel", "Stipe"})


def test_attach_writes_F_for_the_unbilled_woman(corpus):
    current = pd.DataFrame({"fighter": ["Rin", "Mei", "Jon", "Stipe"]})
    out = _attach_recent_division_gender(current, corpus)
    got = out.set_index("fighter")["gender"].to_dict()
    assert got == {"Rin": "F", "Mei": "F", "Jon": "M", "Stipe": "M"}
    # and the display column still reports what she was actually billed at
    assert out.set_index("fighter").loc["Rin", "recent_division"] == "Featherweight"


@pytest.mark.parametrize("billed,expected", [
    ("Flyweight", "Women's Flyweight"),
    ("Women's Flyweight", "Women's Flyweight"),
    ("Strawweight", "Women's Strawweight"),
    ("108lb Catchweight", "Women's Strawweight"),
    ("Atomweight", "Women's Atomweight"),
    ("127lb Catchweight", "Women's Bantamweight"),
    ("Heavyweight", "Women's Openweight"),
    (None, None),
    ("", None),
])
def test_womens_division_label_folds_every_spelling(billed, expected):
    assert womens_division_label(billed) == expected


def test_one_womens_division_is_one_pool():
    """A bare "Flyweight" and a "Women's Flyweight" must not be two bars.

    Before the fold these produced "W Flyweight" and "W Women's Flyweight",
    whose contender lines sat 91 rating points apart on the 2026-08-13 snapshot.
    """
    current = pd.DataFrame({
        "fighter": ["Juliana", "Valentina", "Demetrious"],
        "career_division": ["Flyweight", "Women's Flyweight", "Flyweight"],
        "gender": ["F", "F", "M"],
    })
    labels = _division_labels(current)
    assert labels["Juliana"] == labels["Valentina"] == "Women's Flyweight"
    assert labels["Demetrious"] == "Flyweight"
    assert labels["Juliana"] != labels["Demetrious"]


def test_an_unplaceable_label_still_never_pools_a_woman_with_the_men():
    current = pd.DataFrame({
        "fighter": ["Someone", "Aman"],
        "career_division": ["Super Welterweight", "Super Welterweight"],
        "gender": ["F", "M"],
    })
    labels = _division_labels(current)
    assert labels["Someone"] == "W Super Welterweight"
    assert labels["Aman"] == "Super Welterweight"


def test_womens_history_cannot_change_mens_prime_shrinkage():
    dates = pd.date_range("2010-01-01", periods=13, freq="180D")

    def history(fighter: str, values: list[float]) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "fighter": fighter,
                "event_date": dates,
                "event_name": [f"Event {number}" for number in range(13)],
                "mu_whr": values,
            }
        )

    men = pd.concat(
        [
            history("Man A", [1700.0 + number for number in range(13)]),
            history("Man B", [1900.0 - 2 * number for number in range(13)]),
        ],
        ignore_index=True,
    )
    women_low = history("Woman", [1200.0 + number for number in range(13)])
    women_high = history("Woman", [2400.0 + number for number in range(13)])
    current = pd.DataFrame(
        {"fighter": ["Man A", "Man B", "Woman"], "gender": ["M", "M", "F"]}
    )

    low = _gender_isolated_prime_score(pd.concat([men, women_low]), current)
    high = _gender_isolated_prime_score(pd.concat([men, women_high]), current)

    columns = ["fighter", "score", "shrinkage"]
    pd.testing.assert_frame_equal(
        low[low["fighter"].str.startswith("Man")][columns].reset_index(drop=True),
        high[high["fighter"].str.startswith("Man")][columns].reset_index(drop=True),
    )
