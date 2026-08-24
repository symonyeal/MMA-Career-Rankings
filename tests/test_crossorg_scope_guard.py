"""The cross-org merge must not admit bouts the UFC table already rated."""
from __future__ import annotations

import pandas as pd
import pytest

from ratings.rate_snapshot import merge_crossorg_fights
from ratings.scope import SCOPE_ARTIFACT


def _bout(url: str, a: str, b: str, date: str, *, org: str = "PRIDE", winner: str | None = None) -> dict:
    return {
        "fight_url": url,
        "event_date": pd.Timestamp(date),
        "event_name": f"Card {url}",
        "fighter_a": a,
        "fighter_b": b,
        "winner": winner if winner is not None else a,
        "is_draw": False,
        "org": org,
        "source": "sherdog",
    }


def _write(tmp_path, rows):
    pd.DataFrame(rows).to_parquet(tmp_path / SCOPE_ARTIFACT["fightmatrix"], index=False)
    return tmp_path


def test_guard_drops_a_bout_already_in_the_ufc_table(tmp_path, capsys):
    """19 real bouts sat in both tables and updated their ratings twice.

    An older depth-one artifact carried UFC bouts -- including bouts already in
    ``canonical_fights`` under a different source URL. The merge guard remains
    the backstop for snapshots built before the producer filter existed.
    """
    ufc = pd.DataFrame([_bout("ufc/1", "Alice Ace", "Bob Bee", "2014-05-31", org="UFC")])
    # Same pair, same day, different URL and spelling of the source.
    _write(tmp_path, [
        _bout("sherdog/1", "Bob Bee", "Alice Ace", "2014-05-31", org="Bellator"),
        _bout("sherdog/2", "Carl Cee", "Dan Dee", "2005-01-01"),
    ])

    merged = merge_crossorg_fights(ufc, tmp_path, enabled=True)

    assert merged["fight_url"].tolist() == ["ufc/1", "sherdog/2"]
    assert "already_in_ufc_table" in capsys.readouterr().out


def test_guard_drops_rows_the_source_itself_calls_ufc(tmp_path):
    ufc = pd.DataFrame([_bout("ufc/1", "Alice Ace", "Bob Bee", "2014-05-31", org="UFC")])
    _write(tmp_path, [
        _bout("sherdog/1", "Eve Eff", "Fay Gee", "2019-02-02", org="UFC"),
        _bout("sherdog/2", "Carl Cee", "Dan Dee", "2005-01-01"),
    ])

    merged = merge_crossorg_fights(ufc, tmp_path, enabled=True)

    assert merged["fight_url"].tolist() == ["ufc/1", "sherdog/2"]


def test_guard_keeps_one_agreeing_duplicate_and_drops_a_contradictory_pair(tmp_path, capsys):
    """One bout per profile perspective, and the perspectives can disagree.

    Two rows naming opposite winners cannot both be true. Keeping either
    asserts a result the sources contradict; keeping both hands each fighter a
    win and a loss for one fight. The bout is dropped.
    """
    ufc = pd.DataFrame([_bout("ufc/1", "Alice Ace", "Bob Bee", "2024-01-01", org="UFC")])
    _write(tmp_path, [
        # Agreeing perspectives on one bout.
        _bout("sherdog/1", "Carl Cee", "Dan Dee", "2019-08-24", winner="Carl Cee"),
        _bout("sherdog/2", "Dan Dee", "Carl Cee", "2019-08-24", winner="Carl Cee"),
        # Contradicting perspectives on another.
        _bout("sherdog/3", "Eve Eff", "Fay Gee", "2026-03-01", winner="Eve Eff"),
        _bout("sherdog/4", "Fay Gee", "Eve Eff", "2026-03-01", winner="Fay Gee"),
    ])

    merged = merge_crossorg_fights(ufc, tmp_path, enabled=True)

    assert merged["fight_url"].tolist() == ["ufc/1", "sherdog/1"]
    report = capsys.readouterr().out
    assert "contradictory_duplicate" in report
    assert "repeated_in_source_table" in report


def test_guard_raises_when_nothing_survives(tmp_path):
    ufc = pd.DataFrame([_bout("ufc/1", "Alice Ace", "Bob Bee", "2014-05-31", org="UFC")])
    _write(tmp_path, [_bout("sherdog/1", "Bob Bee", "Alice Ace", "2014-05-31", org="UFC")])

    with pytest.raises(ValueError, match="failed the scope guard"):
        merge_crossorg_fights(ufc, tmp_path, enabled=True)


def test_disabled_merge_is_untouched(tmp_path):
    ufc = pd.DataFrame([_bout("ufc/1", "Alice Ace", "Bob Bee", "2014-05-31", org="UFC")])
    _write(tmp_path, [_bout("sherdog/1", "Carl Cee", "Dan Dee", "2005-01-01")])

    merged = merge_crossorg_fights(ufc, tmp_path, enabled=False)

    assert merged is ufc
