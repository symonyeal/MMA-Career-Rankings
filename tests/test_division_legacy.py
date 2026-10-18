"""The All-time score by weight class: class mapping, the capped-year rule, and sum_d S_d = S."""
import numpy as np
import pandas as pd
import pytest

from ratings.division_legacy import class_board, class_scores, pro_rata, weight_class
from ratings.legacy_resume import RESUME_QUALITY_SCALE, TITLE_QUALITY_SCALE, legacy_points


@pytest.mark.parametrize("division, gender, expected", [
    ("Lightweight", "M", "Lightweight"),
    ("UFC Welterweight Title Bout", "M", "Welterweight"),
    ("165lb Catchweight", "M", "Welterweight"),
    ("265lb Catchweight", "M", "Heavyweight"),
    ("Open Weight", "M", None),
    (None, "M", None),
    ("Flyweight", "F", "Women's Flyweight"),
    ("125lb Catchweight", "F", "Women's Flyweight"),
    ("Open Weight", "F", None),
])
def test_weight_class(division, gender, expected):
    assert weight_class(division, gender) == expected


def test_pro_rata_allocates_each_capped_year_exactly():
    rows = pd.DataFrame({"fighter": ["A"] * 3 + ["B"], "_year": [2010, 2010, 2011, 2010],
                         "weight": [0.6, 0.9, 0.4, 0.3]})
    got = rows.assign(w=pro_rata(rows, cap=1.0)).groupby(["fighter", "_year"])["w"].sum()
    assert got.to_dict() == pytest.approx({("A", 2010): 1.0, ("A", 2011): 0.4, ("B", 2010): 0.3})
    assert pro_rata(rows, 1.0)[0] / pro_rata(rows, 1.0)[1] == pytest.approx(0.6 / 0.9)  # proportions kept


def _current(rng, n=120):
    t, m, r = (rng.gamma(2.0, 1.0, n) for _ in range(3))
    cur = pd.DataFrame({"fighter": [f"f{i}" for i in range(n)], "gender": "M",
                        "public_legacy_exposure_factor": 0.6 + 0.4 * rng.random(n),
                        "_t": t, "_m": m, "_r": r})
    cur["public_legacy_title_score"] = TITLE_QUALITY_SCALE * t
    cur["public_legacy_skill_score"] = m * cur["public_legacy_exposure_factor"]
    cur["public_legacy_resume_score"] = RESUME_QUALITY_SCALE * r * cur["public_legacy_exposure_factor"]
    cur["public_legacy_score"] = sum(legacy_points(*(cur[f"public_legacy_{c}_score"]
                                                     for c in ("title", "skill", "resume"))))
    return cur


def test_class_scores_sum_to_the_all_time_score():
    rng = np.random.default_rng(0)
    cur = _current(rng)
    split = rng.dirichlet(np.ones(3), len(cur))  # each fighter's totals split over two classes and None
    ledger = pd.concat([
        pd.DataFrame({"fighter": cur["fighter"], "division": d, "title": cur["_t"] * split[:, j],
                      "skill": cur["_m"] * split[:, j], "resume": cur["_r"] * split[:, j]})
        for j, d in enumerate(["Lightweight", "Welterweight", None])
    ])
    S = class_scores(cur, ledger)
    total = S.groupby("fighter")["score"].sum().reindex(cur["fighter"])
    assert np.allclose(total.to_numpy(), cur["public_legacy_score"].to_numpy())


def test_class_board_ranks_within_class_and_skips_the_unclassed():
    scores = pd.DataFrame({"fighter": ["A", "B", "A", "C"],
                           "division": ["Lightweight", "Lightweight", None, "Lightweight"],
                           "title": 0.0, "skill": 0.0, "resume": 0.0, "score": [5.0, 9.0, 1.0, 3.0]})
    cur = pd.DataFrame({"fighter": ["A", "B", "C"], "gender": "M", "public_legacy_score": [6.0, 9.0, 3.0]})
    b = class_board(scores, cur, eligible=pd.Series(["A", "B"]))
    assert b[["fighter", "rank"]].values.tolist() == [["B", 1], ["A", 2]]
    assert b.set_index("fighter")["share"]["A"] == pytest.approx(5 / 6)
