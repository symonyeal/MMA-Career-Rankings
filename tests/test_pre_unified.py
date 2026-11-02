"""The UFC pre-unified era staged as its own corpus."""
from __future__ import annotations

import pandas as pd
import pytest

from loaders.pre_unified import load_pre_unified_fights, stage_pre_unified_scope


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

    assert pre["fight_url"].head(2).tolist() == ["u/1", "u/2"]
    assert len(pre[pre["event_name"].eq("UFC 1: The Beginning")]) == 8
    assert pre.set_index("fight_url").loc[["u/1", "u/2"], "is_excluded"].to_dict() == {
        "u/1": False,
        "u/2": True,
    }
    assert (pre["rules_era"] == "ufc_pre_unified").all()
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
