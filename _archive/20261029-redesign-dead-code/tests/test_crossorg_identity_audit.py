"""The identity audit proposes; it never decides."""
from __future__ import annotations

from loaders.crossorg_identity_audit import audit

CORE = [
    "Jacare Souza", "Rogerio Nogueira", "Mauricio Rua", "Patricio Freire",
    "Ovince Saint Preux", "Mike Brown",
]


def test_an_exact_key_match_is_not_reported():
    """Already-joined fighters are not candidates."""
    out = audit(["Mauricio Rua"], CORE)
    assert out.empty or "Mauricio Rua" not in set(out["crossorg_name"])


def test_a_shared_given_name_ranks_above_a_bare_surname():
    out = audit(["Ovince St. Preux", "Ronaldo Souza"], CORE,
                crossorg_weight={"Ovince St. Preux": 7, "Ronaldo Souza": 8})
    reasons = dict(zip(out["crossorg_name"], out["reason"]))
    assert reasons["Ovince St. Preux"] == "surname + given name"
    assert reasons["Ronaldo Souza"] == "surname only"
    # The stronger tier sorts first regardless of bout count.
    assert out.iloc[0]["crossorg_name"] == "Ovince St. Preux"


def test_siblings_are_surfaced_but_never_merged():
    """Murilo Rua and Patricky Freire are brothers of rated fighters, not them.

    Both land in the weak tier with the collision visible, which is the whole
    reason this module returns candidates instead of applying them.
    """
    out = audit(["Murilo Rua", "Patricky Freire"], CORE,
                crossorg_weight={"Murilo Rua": 14, "Patricky Freire": 11})
    assert set(out["crossorg_name"]) == {"Murilo Rua", "Patricky Freire"}
    assert set(out["reason"]) == {"surname + shared initial"}
    assert "core_candidate" in out.columns


def test_bout_count_orders_within_a_tier():
    out = audit(["Ronaldo Souza", "Bruno Souza"], CORE,
                crossorg_weight={"Ronaldo Souza": 8, "Bruno Souza": 1})
    assert out.iloc[0]["crossorg_name"] == "Ronaldo Souza"


def test_nicknames_and_accents_do_not_block_the_surname():
    out = audit(['Antonio "Minotouro" Nogueira'], CORE)
    assert not out.empty
    assert out.iloc[0]["core_candidate"] == "Rogerio Nogueira"
