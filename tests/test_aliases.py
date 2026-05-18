"""Fighter alias resolution via the staged tiger-millionaire export."""
from __future__ import annotations

from project_helpers import normalize_name_key


def test_alias_collapses_known_pair():
    # "Francisco Figueredo" is the alias of "Francisco Figueiredo" in
    # the staged tiger-millionaire fighter_aliases.csv.
    alias_key = normalize_name_key("Francisco Figueredo")
    canonical_key = normalize_name_key("Francisco Figueiredo")
    assert alias_key == canonical_key


def test_alias_disabled_when_requested():
    alias_key = normalize_name_key("Francisco Figueredo", apply_aliases=False)
    canonical_key = normalize_name_key("Francisco Figueiredo", apply_aliases=False)
    assert alias_key != canonical_key


def test_unknown_name_passes_through():
    assert normalize_name_key("Israel Adesanya") == "israel adesanya"
    assert normalize_name_key("  Israel Adesanya  ") == "israel adesanya"
