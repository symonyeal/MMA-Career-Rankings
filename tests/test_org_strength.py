from __future__ import annotations

import pandas as pd
import pytest

from ratings.org_strength import OrgWeightSpec, apply_org_weight_model, organization_bridge_table


def _bout(url: str, a: str, b: str, org: str, corpus: str) -> dict:
    return {
        "fight_url": url,
        "event_date": pd.Timestamp("2024-01-01"),
        "event_name": url,
        "fighter_a": a,
        "fighter_b": b,
        "winner": a,
        "is_draw": False,
        "org": org,
        "source_corpus": corpus,
    }


def test_bridge_reliability_weights_only_non_ufc_rows_by_bridge_support():
    fights = pd.DataFrame(
        [
            _bout("u/1", "Alice", "Bob", "UFC", "ufc"),
            _bout("p/1", "Alice", "Carl", "PRIDE", "majors"),
            _bout("p/2", "Dana", "Eve", "PRIDE", "majors"),
            _bout("r/1", "Fay", "Gail", "Regional", "fightmatrix"),
        ]
    )

    bridge = organization_bridge_table(fights, floor=0.5, prior=1.0).set_index("org")
    assert bridge.loc["PRIDE", "crossover_fighters"] == 1
    assert bridge.loc["PRIDE", "crossover_bouts"] == 1
    assert bridge.loc["PRIDE", "evidence_weight"] == pytest.approx(0.75)
    assert bridge.loc["Regional", "evidence_weight"] == pytest.approx(0.5)

    weighted = apply_org_weight_model(
        fights,
        OrgWeightSpec("bridge", model="bridge_reliability", floor=0.5, prior=1.0),
    ).set_index("fight_url")
    assert weighted.loc["u/1", "org_weight"] == pytest.approx(1.0)
    assert weighted.loc["p/1", "org_weight"] == pytest.approx(0.75)
    assert weighted.loc["r/1", "org_weight"] == pytest.approx(0.5)


def test_constant_non_ufc_weight_is_a_sensitivity_model():
    fights = pd.DataFrame(
        [
            _bout("u/1", "Alice", "Bob", "UFC", "ufc"),
            _bout("p/1", "Alice", "Carl", "PRIDE", "majors"),
        ]
    )
    weighted = apply_org_weight_model(
        fights,
        OrgWeightSpec("constant", model="constant_non_ufc", non_ufc_weight=0.7),
    ).set_index("fight_url")

    assert weighted.loc["u/1", "org_weight"] == pytest.approx(1.0)
    assert weighted.loc["p/1", "org_weight"] == pytest.approx(0.7)
