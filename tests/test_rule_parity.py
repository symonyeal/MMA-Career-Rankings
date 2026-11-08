"""Name keys, organisation rules and PED text rules exist in Python (staging) and Rust (the model).

`fixtures/rule_parity.json` is the contract: this test holds the Python side to it, and the Rust unit tests in
`src/names.rs`, `src/orgs.rs` and `src/bouts.rs` hold the Rust side to the same file.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

import project_helpers as ph
from loaders.fightmatrix_organizations import normalize_organization
from loaders.ped_flags import PED_DETAIL_RE, _infer_flagged_fighter

CASES = json.loads((Path(__file__).parent / "fixtures" / "rule_parity.json").read_text(encoding="utf8"))


@pytest.mark.parametrize("name,key,compact", CASES["name_keys"])
def test_name_key(name, key, compact):
    assert ph.normalize_name_key(name, apply_aliases=False) == key
    assert ph.normalize_name_key(name, compact=True, apply_aliases=False) == compact


@pytest.mark.parametrize("label,day,verified,canonical,tier", CASES["orgs"])
def test_organization(label, day, verified, canonical, tier):
    r = normalize_organization(label, pd.Timestamp(day) if day else None, verified_label=verified)
    assert (r["canonical_organization"], r["organization_tier"]) == (canonical, tier)


@pytest.mark.parametrize("text,a,b,ped,fighter", CASES["ped"])
def test_ped_text(text, a, b, ped, fighter):
    row = pd.Series({"details_text": text, "fighter_a": a, "fighter_b": b})
    assert bool(PED_DETAIL_RE.search(text)) is ped
    assert (_infer_flagged_fighter(row) or "") == fighter
