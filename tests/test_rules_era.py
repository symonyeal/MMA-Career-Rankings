"""The UFC pre-unified era: labelled, admitted, and priced by measurement."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ratings.rate_snapshot import attach_bout_weights
from ratings.rules_era import (
    RULES_ERA_NON_UFC,
    RULES_ERA_PRE,
    RULES_ERA_UNIFIED,
    RULES_ERA_WEIGHT,
    UFC_28_DATE,
    label_rules_era,
    load_pre_unified_fights,
    rules_era_factor,
    stage_pre_unified_scope,
)


def _fights() -> pd.DataFrame:
    return pd.DataFrame([
        # UFC 27, the last card before the unified rules.
        {"event_date": pd.Timestamp("2000-09-22"), "source": "ufc"},
        # UFC 28, the first card under them.
        {"event_date": UFC_28_DATE, "source": "ufc"},
        {"event_date": pd.Timestamp("2024-01-01"), "source": "ufc"},
        # A PRIDE bout from the same year as UFC 27. Not unified either, but
        # this project does not assert what rules a promotion used.
        {"event_date": pd.Timestamp("2000-09-22"), "source": "sherdog_majors"},
    ])


def test_the_boundary_is_the_date_and_only_for_ufc():
    era = label_rules_era(_fights())
    assert era.tolist() == [
        RULES_ERA_PRE, RULES_ERA_UNIFIED, RULES_ERA_UNIFIED, RULES_ERA_NON_UFC,
    ]


def test_the_factor_touches_only_pre_unified_ufc_bouts():
    fights = _fights()
    fights["rules_era"] = label_rules_era(fights)

    assert rules_era_factor(fights, weight=1.0).tolist() == [1.0, 1.0, 1.0, 1.0]
    assert rules_era_factor(fights, weight=0.25).tolist() == [0.25, 1.0, 1.0, 1.0]

    for bad in (0.0, -0.5, 1.5):
        with pytest.raises(ValueError, match="rules-era weight"):
            rules_era_factor(fights, weight=bad)


def test_default_is_full_admission():
    """1.0 by measurement, not by preference.

    The sweep in ``build_rules_era_sweep.py`` finds every held-out interval
    crossing zero -- only 36 held-out bouts involve a fighter who crossed the
    boundary -- so the term is not identified by prediction and must not be
    asserted at some other value.
    """
    assert RULES_ERA_WEIGHT == 1.0


def test_bout_weights_multiply_org_and_rules_era_on_both_sides():
    fights = _fights()
    fights["rules_era"] = label_rules_era(fights)
    fights["org_weight"] = [1.0, 1.0, 1.0, 0.5]

    out = attach_bout_weights(fights, rules_era_weight=0.5)

    assert out["weight_a"].tolist() == [0.5, 1.0, 1.0, 0.5]
    # WHR needs one shared bout likelihood; a side-specific weight is not one.
    assert np.allclose(out["weight_a"], out["weight_b"])


def test_pre_unified_scope_recovers_the_dropped_bouts(tmp_path):
    pd.DataFrame([
        {"fight_url": "u/1", "event_date": "1997-12-21", "event_name": "UFC Japan",
         "fighter_a": "Alice Ace", "fighter_b": "Bob Bee", "winner": "Alice Ace",
         "is_draw": False, "is_nc": False, "method_class": "Submission",
         "exclusion_reason": "pre_unified_rules"},
        # Excluded for being pre-unified AND unrateable. The era decision does
        # not re-admit a result the engine refuses to read.
        {"fight_url": "u/2", "event_date": "1997-12-21", "event_name": "UFC Japan",
         "fighter_a": "Carl Cee", "fighter_b": "Dan Dee", "winner": None,
         "is_draw": False, "is_nc": True, "method_class": "Overturned",
         "exclusion_reason": "pre_unified_rules"},
        # A modern bout excluded for a different reason stays excluded.
        {"fight_url": "u/3", "event_date": "2019-01-01", "event_name": "UFC 999",
         "fighter_a": "Eve Eff", "fighter_b": "Fay Gee", "winner": None,
         "is_draw": False, "is_nc": True, "method_class": "Overturned",
         "exclusion_reason": "method_overturned"},
    ]).to_csv(tmp_path / "_excluded_bouts.csv", index=False)

    pre = load_pre_unified_fights(tmp_path)

    assert pre["fight_url"].tolist() == ["u/1", "u/2"]
    assert pre.set_index("fight_url")["is_excluded"].to_dict() == {"u/1": False, "u/2": True}
    assert (pre["rules_era"] == RULES_ERA_PRE).all()
    assert (pre["org_weight"] == 1.0).all()


def test_pre_unified_scope_refuses_an_empty_recovery(tmp_path):
    pd.DataFrame([
        {"fight_url": "u/3", "event_date": "2019-01-01", "event_name": "UFC 999",
         "fighter_a": "Eve Eff", "fighter_b": "Fay Gee", "winner": None,
         "is_draw": False, "is_nc": True, "method_class": "Overturned",
         "exclusion_reason": "method_overturned"},
    ]).to_csv(tmp_path / "_excluded_bouts.csv", index=False)

    with pytest.raises(ValueError, match="pre_unified_rules"):
        load_pre_unified_fights(tmp_path)

    (tmp_path / "_excluded_bouts.csv").unlink()
    with pytest.raises(FileNotFoundError, match="_excluded_bouts.csv"):
        stage_pre_unified_scope(tmp_path)
