"""Joining Sherdog ids to canonical fighters: conservative, then evidence-led."""
from __future__ import annotations

import pandas as pd

from loaders.crossorg_identity import (
    apply_identity_map,
    build_identity_map,
    resolve_by_bout_evidence,
    resolve_collisions,
    sherdog_names,
    summary,
)

CORE = ["Jacare Souza", "Fedor Emelianenko", "Anderson Silva", "Mauricio Rua"]


def _bouts(rows: list[tuple[str, str, str, str, str]]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["fighter_a_id", "fighter_a",
                                       "fighter_b_id", "fighter_b", "event_date"])


def test_exact_key_joins_and_an_unknown_keeps_its_own_identity():
    bouts = _bouts([
        ("1500", "Fedor Emelianenko", "999", "Martin Lazarov", "2000-05-21"),
    ])
    identity = build_identity_map(bouts, CORE, overrides={})
    by_id = identity.set_index("sherdog_id")
    assert by_id.loc["1500", "canonical_name"] == "Fedor Emelianenko"
    assert by_id.loc["1500", "join_method"] == "name_key"
    # Not in the UFC set: still rated, just not asserted to be someone else.
    assert by_id.loc["999", "canonical_name"] == "Martin Lazarov"
    assert by_id.loc["999", "join_method"] == "unjoined"


def test_a_ring_name_joins_only_through_a_verified_override():
    bouts = _bouts([("7448", "Ronaldo Souza", "1500", "Fedor Emelianenko", "2006-12-17")])

    without = build_identity_map(bouts, CORE, overrides={})
    assert without.set_index("sherdog_id").loc["7448", "join_method"] == "unjoined"

    with_override = build_identity_map(
        bouts, CORE, overrides={"ronaldosouza": "Jacare Souza"}
    )
    row = with_override.set_index("sherdog_id").loc["7448"]
    assert row["canonical_name"] == "Jacare Souza"
    assert row["join_method"] == "override"


def test_two_ids_claiming_one_name_are_both_refused():
    """Sherdog carries two Anderson Silvas; a name cannot tell them apart."""
    bouts = _bouts([
        ("1356", "Anderson Silva", "1500", "Fedor Emelianenko", "2006-10-21"),
        ("133403", "Anderson Silva", "1500", "Fedor Emelianenko", "2011-01-01"),
    ])
    identity = build_identity_map(bouts, CORE, overrides={})
    both = identity[identity["sherdog_id"].isin(["1356", "133403"])]
    assert set(both["join_method"]) == {"collision"}
    assert "Anderson Silva" not in set(
        identity.loc[identity["join_method"].eq("name_key"), "canonical_name"]
    )


def test_the_contested_name_goes_to_the_id_whose_dates_match_the_ufc_record():
    bouts = _bouts([
        ("1356", "Anderson Silva", "500", "Rich Franklin", "2006-10-14"),
        ("1356", "Anderson Silva", "501", "Dan Henderson", "2008-03-01"),
        ("133403", "Anderson Silva", "502", "Regional Guy", "2015-06-06"),
    ])
    canonical = pd.DataFrame([
        {"fighter_a": "Anderson Silva", "fighter_b": "Rich Franklin",
         "event_date": "2006-10-14"},
        {"fighter_a": "Dan Henderson", "fighter_b": "Anderson Silva",
         "event_date": "2008-03-01"},
    ])
    identity = build_identity_map(bouts, CORE, overrides={})
    resolved = resolve_collisions(identity, bouts, canonical).set_index("sherdog_id")

    assert resolved.loc["1356", "canonical_name"] == "Anderson Silva"
    assert resolved.loc["1356", "join_method"] == "collision_resolved"
    # The namesake is left alone rather than merged in.
    assert resolved.loc["133403", "canonical_name"] != "Anderson Silva"


def test_one_matching_date_is_not_enough_to_award_a_name():
    bouts = _bouts([
        ("1356", "Anderson Silva", "500", "Rich Franklin", "2006-10-14"),
        ("133403", "Anderson Silva", "502", "Regional Guy", "2015-06-06"),
    ])
    canonical = pd.DataFrame([
        {"fighter_a": "Anderson Silva", "fighter_b": "Rich Franklin",
         "event_date": "2006-10-14"},
    ])
    identity = build_identity_map(bouts, CORE, overrides={})
    resolved = resolve_collisions(identity, bouts, canonical)
    assert "collision_resolved" not in set(resolved["join_method"])


def test_names_and_summary_survive_spelling_variants():
    bouts = _bouts([
        ("1500", "Fedor Emelianenko", "999", "Martin Lazarov", "2000-05-21"),
        ("1500", "Fedor  Emelianenko", "998", "Kerry Schall", "2001-04-20"),
    ])
    assert sherdog_names(bouts).loc["1500"] in {"Fedor Emelianenko", "Fedor  Emelianenko"}
    identity = build_identity_map(bouts, CORE, overrides={})
    joined = apply_identity_map(bouts, identity)
    assert len(joined) == 2
    assert summary(identity)["fighters"] == 3


def test_unjoined_namesakes_do_not_collapse_into_one_fighter():
    """Two regional fighters sharing a name are two fighters, not one."""
    bouts = _bouts([
        ("111", "Joao Silva", "999", "Someone", "2010-01-01"),
        ("222", "Joao Silva", "998", "Someone Else", "2014-01-01"),
        ("333", "Unique Person", "997", "Third", "2012-01-01"),
    ])
    identity = build_identity_map(bouts, CORE, overrides={}).set_index("sherdog_id")
    assert identity.loc["111", "canonical_name"] != identity.loc["222", "canonical_name"]
    assert "sherdog:111" in identity.loc["111", "canonical_name"]
    # A name nobody else claims is left readable.
    assert identity.loc["333", "canonical_name"] == "Unique Person"


def test_bout_evidence_joins_a_ring_name_no_name_rule_could_reach():
    """Patchy Mix: 'Patrick Mix' on Sherdog, 'Patchy Mix' in the canonical set."""
    bouts = _bouts([
        ("161007", "Patrick Mix", "700", "Kyoji Horiguchi", "2022-04-23"),
        ("161007", "Patrick Mix", "701", "Sergio Pettis", "2023-11-17"),
        # His fighter page carries his UFC bouts too -- that is the evidence.
        ("161007", "Patrick Mix", "702", "Mario Bautista", "2025-06-07"),
        ("161007", "Patrick Mix", "703", "Jakub Wiklacz", "2025-10-04"),
    ])
    canonical = pd.DataFrame([
        {"fighter_a": "Patchy Mix", "fighter_b": "Mario Bautista",
         "event_date": "2025-06-07"},
        {"fighter_a": "Jakub Wiklacz", "fighter_b": "Patchy Mix",
         "event_date": "2025-10-04"},
    ])
    identity = build_identity_map(bouts, CORE + ["Patchy Mix"], overrides={})
    assert identity.set_index("sherdog_id").loc["161007", "join_method"] == "unjoined"

    resolved = resolve_by_bout_evidence(identity, bouts, canonical).set_index("sherdog_id")
    assert resolved.loc["161007", "canonical_name"] == "Patchy Mix"
    assert resolved.loc["161007", "join_method"] == "bout_evidence"


def test_bout_evidence_does_not_merge_brothers():
    """Murilo Rua shares no bout with Mauricio Rua, so nothing joins."""
    bouts = _bouts([
        ("5707", "Murilo Rua", "800", "Some Opponent", "2005-01-01"),
        ("5707", "Murilo Rua", "801", "Another Opponent", "2006-01-01"),
    ])
    canonical = pd.DataFrame([
        {"fighter_a": "Mauricio Rua", "fighter_b": "Forrest Griffin",
         "event_date": "2007-09-22"},
        {"fighter_a": "Mauricio Rua", "fighter_b": "Chuck Liddell",
         "event_date": "2009-04-18"},
    ])
    identity = build_identity_map(bouts, CORE, overrides={})
    resolved = resolve_by_bout_evidence(identity, bouts, canonical)
    assert "bout_evidence" not in set(resolved["join_method"])


def test_one_shared_bout_is_not_enough_and_a_tie_abstains():
    bouts = _bouts([("900", "Ambiguous Guy", "901", "Shared Opponent", "2020-01-01")])
    canonical = pd.DataFrame([
        {"fighter_a": "Fighter One", "fighter_b": "Shared Opponent",
         "event_date": "2020-01-01"},
        {"fighter_a": "Fighter Two", "fighter_b": "Shared Opponent",
         "event_date": "2020-01-01"},
    ])
    identity = build_identity_map(bouts, ["Fighter One", "Fighter Two"], overrides={})
    resolved = resolve_by_bout_evidence(identity, bouts, canonical)
    assert "bout_evidence" not in set(resolved["join_method"])


def test_bout_evidence_tolerates_the_one_day_date_drift():
    bouts = _bouts([
        ("161007", "Patrick Mix", "702", "Mario Bautista", "2025-06-08"),
        ("161007", "Patrick Mix", "703", "Jakub Wiklacz", "2025-10-05"),
    ])
    canonical = pd.DataFrame([
        {"fighter_a": "Patchy Mix", "fighter_b": "Mario Bautista",
         "event_date": "2025-06-07"},
        {"fighter_a": "Patchy Mix", "fighter_b": "Jakub Wiklacz",
         "event_date": "2025-10-04"},
    ])
    identity = build_identity_map(bouts, ["Patchy Mix"], overrides={})
    resolved = resolve_by_bout_evidence(identity, bouts, canonical).set_index("sherdog_id")
    assert resolved.loc["161007", "canonical_name"] == "Patchy Mix"
