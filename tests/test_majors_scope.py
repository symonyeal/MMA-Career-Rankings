"""The six-promotion corpus, reshaped into rateable canonical rows."""
from __future__ import annotations

import pandas as pd
import pytest

from loaders.majors_scope import (
    CANONICAL_COLUMNS,
    build_majors_fights,
    load_majors_bouts,
    resolve_identities,
    sherdog_birth_dates,
    to_canonical_fights,
    unmatched_names,
)
from loaders.page_cache import open_cache


def _card(fid_a, name_a, fid_b, name_b, *, date, org="PRIDE", event_id="1",
          a_outcome="win", b_outcome="loss", method="Submission (Armbar)") -> dict:
    return {
        "event_id": event_id,
        "event_name": f"{org} 1",
        "event_date": pd.Timestamp(date),
        "event_location": "Saitama",
        "org": org,
        "fighter_a_id": fid_a,
        "fighter_a": name_a,
        "fighter_b_id": fid_b,
        "fighter_b": name_b,
        "fighter_a_outcome": a_outcome,
        "fighter_b_outcome": b_outcome,
        "weight_class": None,
        "method_raw": method,
        "referee": "Yuji Shimada",
        "end_round": 1.0,
        "end_time_seconds": 397.0,
        "is_title_fight": False,
    }


def _canonical() -> pd.DataFrame:
    return pd.DataFrame([
        {"fight_url": "ufc/1", "event_date": pd.Timestamp("2007-01-01"),
         "event_name": "UFC 1", "fighter_a": "Wanderlei Silva",
         "fighter_b": "Chuck Liddell", "winner": "Chuck Liddell", "is_draw": False},
    ])


def test_card_rows_become_canonical_rows_keyed_to_ufc_identities():
    bouts = pd.DataFrame([
        _card("1", "Wanderlei Silva", "2", "Kazushi Sakuraba", date="2001-03-25"),
        _card("3", "Some Regional", "4", "Other Regional", date="2002-01-01",
              event_id="2", a_outcome="loss", b_outcome="win", method="Decision (Split)"),
    ])
    identity = resolve_identities(bouts, _canonical())
    fights = to_canonical_fights(bouts, identity)

    assert list(fights.columns) == CANONICAL_COLUMNS
    silva = fights[fights["fighter_a"].eq("Wanderlei Silva")].iloc[0]
    assert silva["winner"] == "Wanderlei Silva"
    assert silva["method_class"] == "Submission"
    assert silva["source"] == "sherdog_majors"
    assert silva["org_evidence"] == "sherdog_event"
    # No organisation weight, ever. Promotion strength is an output.
    assert (fights["org_weight"] == 1.0).all()

    # A loss row is oriented so winner/loser are the same fields as everywhere.
    other = fights[fights["event_name"].str.endswith("PRIDE 1")].iloc[-1]
    assert other["winner"] == other["loser"] or other["winner"] != other["fighter_a"]


def test_an_unrateable_result_is_marked_excluded_not_dropped():
    bouts = pd.DataFrame([
        _card("1", "Wanderlei Silva", "2", "Kazushi Sakuraba", date="2001-03-25",
              a_outcome="nc", b_outcome="nc", method="No Contest"),
        _card("1", "Wanderlei Silva", "5", "Ricardo Arona", date="2002-03-25",
              event_id="9", method="KO (Punches)"),
    ])
    fights = to_canonical_fights(bouts, resolve_identities(bouts, _canonical()))

    by_date = fights.set_index(fights["event_date"].dt.year)
    assert bool(by_date.loc[2001, "is_excluded"])
    assert not bool(by_date.loc[2002, "is_excluded"])
    assert "result_not_rateable" in str(by_date.loc[2001, "exclusion_reason"])


def test_fighter_page_event_name_recovers_a_known_organization():
    row = _card(
        "1", "Wanderlei Silva", "2", "Kazushi Sakuraba", date="2012-06-23"
    )
    row["org"] = None
    row["event_name"] = "UFC 147 - Silva vs. Franklin 2"
    bouts = pd.DataFrame([row])

    fights = to_canonical_fights(bouts, resolve_identities(bouts, _canonical()))

    assert fights.iloc[0]["org"] == "UFC"
    assert fights.iloc[0]["org_evidence"] == "event_name_rule"
    assert fights.iloc[0]["event_name"] == "UFC 147 - Silva vs. Franklin 2"


def test_a_fighter_who_matches_nothing_keeps_their_own_identity():
    """Not asserted to be someone in the UFC set, and still rated.

    The alternative -- dropping them -- would silently remove the opponent a
    known fighter's result was earned against, which is evidence about the
    known fighter.
    """
    bouts = pd.DataFrame([
        _card("1", "Wanderlei Silva", "9", "Nobody In The DB", date="2001-03-25"),
    ])
    identity = resolve_identities(bouts, _canonical())
    fights = to_canonical_fights(bouts, identity)

    assert len(fights) == 1
    assert set(fights.iloc[0][["fighter_a", "fighter_b"]]) == {
        "Wanderlei Silva", "Nobody In The DB"}
    audit = unmatched_names(bouts, identity)
    assert "Nobody In The DB" in set(audit["sherdog_name"])


def test_build_reports_the_bridge_population(tmp_path):
    """How many fighters the two corpora share is the whole joint fit's leverage."""
    pd.DataFrame([
        _card("1", "Wanderlei Silva", "2", "Kazushi Sakuraba", date="2001-03-25"),
        _card("2", "Kazushi Sakuraba", "9", "Nobody In The DB", date="2002-03-25",
              event_id="7"),
    ]).to_parquet(tmp_path / "majors_bouts.parquet", index=False)

    fights, report = build_majors_fights(_canonical(), majors_dir=tmp_path)

    assert report["source_bouts"] == 2
    assert report["rateable_bouts"] == 2
    assert report["fighters_shared_with_ufc"] == 1  # Wanderlei Silva
    assert report["careers_extension_present"] is False
    assert report["by_org"] == {"PRIDE": 2}
    assert len(fights) == 2


def test_missing_corpus_says_which_builder_makes_it(tmp_path):
    with pytest.raises(FileNotFoundError, match="build_sherdog_majors"):
        load_majors_bouts(tmp_path)


def test_sherdog_birth_dates_read_the_shared_store(tmp_path):
    open_cache(tmp_path).put(
        "fighters",
        "17",
        '<span itemprop="birthDate">Jan 2, 1990</span>',
    )
    identity = pd.DataFrame(
        {"sherdog_id": ["17"], "canonical_name": ["Alice Ace"]}
    )

    births = sherdog_birth_dates(identity, cache_dir=tmp_path)

    assert births.to_dict(orient="records") == [
        {
            "fighter": "Alice Ace",
            "dob": pd.Timestamp("1990-01-02"),
            "source": "sherdog_profile",
            "source_id": "17",
        }
    ]
