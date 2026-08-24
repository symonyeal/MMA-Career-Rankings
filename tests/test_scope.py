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


def _bout(url: str, a: str, b: str, date: str, *, org: str = "PRIDE",
          winner: str | None = None, excluded: bool = False) -> dict:
    return {
        "fight_url": url,
        "event_date": pd.Timestamp(date),
        "event_name": f"Card {url}",
        "fighter_a": a,
        "fighter_b": b,
        "winner": winner if winner is not None else a,
        "is_draw": False,
        "is_excluded": excluded,
        "org": org,
        "source": "sherdog",
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


def test_a_no_contest_does_not_contradict_a_decided_rematch():
    """Sakuraba beat Silveira at UFC Japan 1997 in a same-night rematch.

    Their first bout that night was overturned. Same pair, same date, and the
    overturned row names no winner -- so it is redundant at this key, not
    contradictory, and the decided result is the one that must survive.
    """
    ufc = pd.DataFrame([_bout("ufc/1", "Alice Ace", "Bob Bee", "2024-01-01", org="UFC")])
    rows = pd.DataFrame([
        _bout("u/nc", "Kazushi Sakuraba", "Marcus Silveira", "1997-12-21",
              org="UFC", winner=None, excluded=True),
        _bout("u/win", "Kazushi Sakuraba", "Marcus Silveira", "1997-12-21",
              org="UFC", winner="Kazushi Sakuraba"),
    ])

    kept, dropped = scope_guard(rows, ufc, source="pre_unified")

    assert kept["fight_url"].tolist() == ["u/win"]
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
