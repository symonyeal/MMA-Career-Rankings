"""The scope registry: named corpora, no silent merges, no silent no-ops."""
from __future__ import annotations

import pandas as pd
import pytest

from ratings.scope import (
    SCOPE_ARTIFACT,
    SCOPE_MERGE_ORDER,
    UFC_ONLY,
    merge_scope,
    scope_guard,
    scope_sources,
)


_DEFAULT_WINNER = object()


def _bout(url: str, a: str, b: str, date: str, *, org: str = "PRIDE",
          winner=_DEFAULT_WINNER, excluded: bool = False, nc: bool = False,
          source: str = "sherdog") -> dict:
    return {
        "fight_url": url,
        "event_date": pd.Timestamp(date),
        "event_name": f"Card {url}",
        "fighter_a": a,
        "fighter_b": b,
        "winner": a if winner is _DEFAULT_WINNER else winner,
        "is_draw": False,
        "is_nc": nc,
        "is_excluded": excluded,
        "org": org,
        "source": source,
    }


def _stage(tmp_path, source, rows):
    pd.DataFrame(rows).to_parquet(tmp_path / SCOPE_ARTIFACT[source], index=False)


def test_scope_spec_parses_and_refuses_nonsense():
    assert scope_sources(UFC_ONLY) == ()
    assert scope_sources("majors") == ("majors",)
    # Order is source authority, never the order the caller wrote, so a scope
    # spec cannot decide whose parse of a shared bout survives the dedupe guard.
    assert scope_sources("majors,pre_unified") == ("pre_unified", "majors")
    assert scope_sources("pre_unified,majors") == ("pre_unified", "majors")
    assert scope_sources("all") == SCOPE_MERGE_ORDER
    # ufc contributes no corpus, so naming it alongside another is harmless.
    assert scope_sources("ufc,majors") == ("majors",)

    with pytest.raises(ValueError, match="unknown scope"):
        scope_sources("crossorg")
    with pytest.raises(ValueError, match="combines"):
        scope_sources("all,majors")
    with pytest.raises(ValueError, match="twice"):
        scope_sources("majors,majors")


def test_missing_artifact_raises_and_names_the_fix(tmp_path):
    """A scope that cannot be satisfied must not fall back to UFC-only.

    That fallback is how "cross-org makes no difference" became a believed
    result: the flag merged zero bouts and the board came out identical.
    """
    ufc = pd.DataFrame([_bout("ufc/1", "Alice Ace", "Bob Bee", "2024-01-01", org="UFC")])

    with pytest.raises(FileNotFoundError, match="stage_majors_scope"):
        merge_scope(ufc, tmp_path, scope="majors")
    with pytest.raises(FileNotFoundError, match="stage_pre_unified_scope"):
        merge_scope(ufc, tmp_path, scope="pre_unified")
    with pytest.raises(FileNotFoundError, match="no cross-org artifact at all"):
        merge_scope(ufc, tmp_path, scope="fightmatrix")


def test_ufc_scope_says_what_it_declined(tmp_path, capsys):
    ufc = pd.DataFrame([_bout("ufc/1", "Alice Ace", "Bob Bee", "2024-01-01", org="UFC")])
    _stage(tmp_path, "majors", [_bout("s/1", "Carl Cee", "Dan Dee", "2005-01-01")])

    merged = merge_scope(ufc, tmp_path, scope=UFC_ONLY)

    assert merged is ufc
    assert "not admitted" in capsys.readouterr().out


def test_combined_scope_merges_each_named_corpus(tmp_path):
    ufc = pd.DataFrame([_bout("ufc/1", "Alice Ace", "Bob Bee", "2024-01-01", org="UFC")])
    _stage(tmp_path, "majors", [_bout("s/1", "Carl Cee", "Dan Dee", "2005-01-01")])
    _stage(tmp_path, "pre_unified",
           [_bout("u/0", "Eve Eff", "Fay Gee", "1996-02-02", org="UFC (pre-unified)")])

    merged = merge_scope(ufc, tmp_path, scope="majors,pre_unified")

    assert set(merged["fight_url"]) == {"ufc/1", "s/1", "u/0"}


def test_pre_unified_rows_survive_the_ufc_org_check(tmp_path):
    """They are UFC bouts by definition, separated by date, not promotion."""
    ufc = pd.DataFrame([_bout("ufc/1", "Alice Ace", "Bob Bee", "2024-01-01", org="UFC")])
    pre = pd.DataFrame([_bout("u/0", "Eve Eff", "Fay Gee", "1996-02-02", org="UFC")])

    kept, dropped = scope_guard(pre, ufc, source="pre_unified")
    assert kept["fight_url"].tolist() == ["u/0"]
    assert "org_is_ufc" not in dropped

    # The same row in a corpus that claims to be non-UFC is still dropped.
    with pytest.raises(ValueError, match="failed the scope guard"):
        scope_guard(pre, ufc, source="majors")


def test_guard_accepts_an_empty_prior_table():
    prior = pd.DataFrame(columns=["event_date", "fighter_a", "fighter_b"])
    rows = pd.DataFrame([_bout("s/1", "Carl Cee", "Dan Dee", "2005-01-01")])

    kept, dropped = scope_guard(rows, prior, source="majors")

    assert kept["fight_url"].tolist() == ["s/1"]
    assert dropped == {}


def test_guard_collapses_a_canonical_ufc_copy_with_one_day_source_drift():
    """The same international UFC card must update the rating only once."""
    ufc = pd.DataFrame([
        _bout(
            "ufc/275",
            "Jiri Prochazka",
            "Glover Teixeira",
            "2022-06-11",
            org="UFC",
            winner="Jiri Prochazka",
            source="ufc",
        )
    ])
    rows = pd.DataFrame([
        _bout(
            "sherdog/275",
            "Glover Teixeira",
            "Jiri Prochazka",
            "2022-06-12",
            org=None,
            winner="Jiri Prochazka",
            source="sherdog_majors",
        ),
        _bout("s/other", "Carl Cee", "Dan Dee", "2005-01-01"),
    ])

    kept, dropped = scope_guard(rows, ufc, source="majors")

    assert kept["fight_url"].tolist() == ["s/other"]
    assert dropped == {"canonical_date_drift": 1}


def test_guard_collapses_a_one_day_draw_copy():
    ufc_row = _bout(
        "ufc/draw",
        "Mark Hunt",
        "Antonio Silva",
        "2013-12-06",
        org="UFC",
        winner=None,
        source="ufc",
    )
    ufc_row["is_draw"] = True
    copied = _bout(
        "sherdog/draw",
        "Antonio Silva",
        "Mark Hunt",
        "2013-12-07",
        winner=None,
        source="sherdog_majors",
    )
    copied["is_draw"] = True
    rows = pd.DataFrame([
        copied,
        _bout("s/other", "Carl Cee", "Dan Dee", "2005-01-01"),
    ])

    kept, dropped = scope_guard(
        rows,
        pd.DataFrame([ufc_row]),
        source="majors",
    )

    assert kept["fight_url"].tolist() == ["s/other"]
    assert dropped == {"canonical_date_drift": 1}


def test_guard_does_not_expand_the_observed_drift_to_two_days():
    ufc = pd.DataFrame([
        _bout(
            "ufc/1",
            "Alice Ace",
            "Bob Bee",
            "2024-01-01",
            org="UFC",
            source="ufc",
        )
    ])
    rows = pd.DataFrame([
        _bout(
            "s/1",
            "Bob Bee",
            "Alice Ace",
            "2024-01-03",
            source="sherdog_majors",
        )
    ])

    kept, dropped = scope_guard(rows, ufc, source="majors")

    assert kept["fight_url"].tolist() == ["s/1"]
    assert dropped == {}


def test_guard_preserves_an_ambiguous_one_day_match():
    """Proximity alone cannot choose between two same-result canonical bouts."""
    ufc = pd.DataFrame([
        _bout(
            "ufc/first",
            "Alice Ace",
            "Bob Bee",
            "2024-01-01",
            org="UFC",
            source="ufc",
        ),
        _bout(
            "ufc/second",
            "Bob Bee",
            "Alice Ace",
            "2024-01-03",
            org="UFC",
            winner="Alice Ace",
            source="ufc",
        ),
    ])
    rows = pd.DataFrame([
        _bout(
            "s/ambiguous",
            "Alice Ace",
            "Bob Bee",
            "2024-01-02",
            org=None,
            source="sherdog_majors",
        )
    ])

    kept, dropped = scope_guard(rows, ufc, source="majors")

    assert kept["fight_url"].tolist() == ["s/ambiguous"]
    assert dropped == {}


def test_guard_preserves_distinct_consecutive_day_tournament_rematches():
    """Pair/date proximity cannot erase two sourced tournament sessions."""
    prior = pd.DataFrame(columns=["event_date", "fighter_a", "fighter_b", "source"])
    rows = pd.DataFrame([
        _bout(
            "sherdog-majors::827::4397::1061",
            "Mike Whitehead",
            "Tim Sylvia",
            "2002-04-26",
            winner="Tim Sylvia",
            source="sherdog_majors",
        ),
        _bout(
            "sherdog-majors::831::4397::1061",
            "Mike Whitehead",
            "Tim Sylvia",
            "2002-04-27",
            winner="Tim Sylvia",
            source="sherdog_majors",
        ),
    ])

    kept, dropped = scope_guard(rows, prior, source="majors")

    assert kept["fight_url"].tolist() == [
        "sherdog-majors::827::4397::1061",
        "sherdog-majors::831::4397::1061",
    ]
    assert dropped == {}


def test_canonical_ufc_ids_preserve_a_no_contest_and_same_night_rematch():
    """Sakuraba beat Silveira at UFC Japan 1997 in a same-night rematch.

    Their first bout that night was overturned. The pair and date are the same,
    but UFC's canonical fight URLs are distinct primary keys, so both real bouts
    survive while an actual repeated row still does not.
    """
    ufc = pd.DataFrame([_bout("ufc/1", "Alice Ace", "Bob Bee", "2024-01-01", org="UFC")])
    rows = pd.DataFrame([
        _bout("http://ufcstats.com/fight-details/2750ac5854e8b28b",
              "Kazushi Sakuraba", "Marcus Silveira", "1997-12-21",
              org="UFC", winner=None, excluded=True, nc=True, source="ufc"),
        _bout("http://ufcstats.com/fight-details/ec1bda9a4c2aab42",
              "Kazushi Sakuraba", "Marcus Silveira", "1997-12-21",
              org="UFC", winner="Kazushi Sakuraba", source="ufc"),
        _bout("http://ufcstats.com/fight-details/ec1bda9a4c2aab42",
              "Marcus Silveira", "Kazushi Sakuraba", "1997-12-21",
              org="UFC", winner="Kazushi Sakuraba", source="ufc"),
    ])

    kept, dropped = scope_guard(rows, ufc, source="pre_unified")

    assert kept["fight_url"].tolist() == [
        "http://ufcstats.com/fight-details/2750ac5854e8b28b",
        "http://ufcstats.com/fight-details/ec1bda9a4c2aab42",
    ]
    assert pd.isna(kept.iloc[0]["winner"])
    assert dropped == {"repeated_in_source_table": 1}


@pytest.mark.parametrize(
    ("canonical", "variant"),
    [
        ("Jose Aldo", "José Aldo"),
        ("Francisco Figueiredo", "Francisco Figueredo"),
    ],
    ids=["accent", "alias"],
)
def test_agreeing_winners_use_the_bout_fingerprint_identity(canonical, variant):
    ufc = pd.DataFrame([_bout("ufc/1", "Alice Ace", "Bob Bee", "2024-01-01", org="UFC")])
    rows = pd.DataFrame([
        _bout("s/1", canonical, "Opponent One", "2019-08-24", winner=canonical),
        _bout("s/2", "Opponent One", variant, "2019-08-24", winner=variant),
    ])

    kept, dropped = scope_guard(rows, ufc, source="majors")

    assert kept["fight_url"].tolist() == ["s/1"]
    assert dropped == {"repeated_in_source_table": 1}


def test_opposite_winners_drop_the_whole_bout():
    ufc = pd.DataFrame([_bout("ufc/1", "Alice Ace", "Bob Bee", "2024-01-01", org="UFC")])
    rows = pd.DataFrame([
        _bout("s/1", "Ricardo Pandora", "Ronaldo Cavalheiro", "2026-03-01",
              winner="Ricardo Pandora"),
        _bout("s/2", "Ronaldo Cavalheiro", "Ricardo Pandora", "2026-03-01",
              winner="Ronaldo Cavalheiro"),
        _bout("s/3", "Carl Cee", "Dan Dee", "2005-01-01"),
    ])

    kept, dropped = scope_guard(rows, ufc, source="majors")

    assert kept["fight_url"].tolist() == ["s/3"]
    assert dropped == {"contradictory_duplicate": 2}
