from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from loaders.combined_fights import (
    build_combined_fights,
    write_combined_fights,
)
from loaders.scope import SCOPE_ARTIFACT


def _bout(
    url: str,
    a: str,
    b: str,
    date: str,
    *,
    org: str = "UFC",
    source: str = "ufc",
    winner: str | None = None,
) -> dict:
    return {
        "fight_url": url,
        "event_date": pd.Timestamp(date),
        "event_name": f"Event {url}",
        "fighter_a": a,
        "fighter_b": b,
        "winner": winner if winner is not None else a,
        "is_draw": False,
        "is_nc": False,
        "is_excluded": False,
        "method_class": "Decision",
        "method_score_winner": 1.0,
        "org": org,
        "source": source,
    }


def test_combined_fights_preserves_union_columns_and_writes_summary(tmp_path: Path):
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    canonical = pd.DataFrame(
        [_bout("u/1", "Alice", "Bob", "2024-01-01")]
    )
    canonical.to_parquet(snapshot / "canonical_fights.parquet", index=False)

    majors = pd.DataFrame(
        [
            {
                **_bout(
                    "s/1",
                    "Carl",
                    "Dana",
                    "2010-01-01",
                    org="PRIDE",
                    source="sherdog_majors",
                ),
                "sherdog_event_id": "123",
            }
        ]
    )
    majors.to_parquet(snapshot / SCOPE_ARTIFACT["majors"], index=False)

    summary = write_combined_fights(snapshot, scope="majors")
    combined = pd.read_parquet(snapshot / "combined_fights.parquet")
    stored_summary = json.loads((snapshot / "combined_fights_summary.json").read_text(encoding="utf-8"))

    assert summary == stored_summary
    assert set(combined["fight_url"]) == {"u/1", "s/1"}
    assert "sherdog_event_id" in combined.columns
    assert combined["bout_fingerprint"].is_unique
    assert combined.set_index("fight_url").loc["u/1", "source_corpus"] == "ufc"
    assert combined.set_index("fight_url").loc["s/1", "source_corpus"] == "majors"
    assert combined.set_index("fight_url").loc["u/1", "available_in_corpora"] == "ufc"
    assert combined.set_index("fight_url").loc["s/1", "available_in_corpora"] == "majors"
    assert summary["scope"] == "majors"
    assert summary["rows"] == 2
    assert summary["model_bouts"] == 2
    assert summary["duplicate_fingerprints"] == 0


def test_combined_fights_refuses_duplicate_canonical_bouts(tmp_path: Path):
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    duplicated = pd.DataFrame(
        [
            _bout("u/1", "Alice", "Bob", "2024-01-01"),
            _bout("u/1", "Bob", "Alice", "2024-01-01"),
        ]
    )
    duplicated.to_parquet(snapshot / "canonical_fights.parquet", index=False)

    with pytest.raises(ValueError, match="duplicate bout identities"):
        build_combined_fights(snapshot, scope="ufc")


def test_combined_fights_preserves_distinct_canonical_same_day_rematches(tmp_path: Path):
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    pd.DataFrame(
        [
            _bout("u/first", "Alice", "Bob", "2024-01-01"),
            _bout("u/rematch", "Bob", "Alice", "2024-01-01"),
        ]
    ).to_parquet(snapshot / "canonical_fights.parquet", index=False)

    combined, summary = build_combined_fights(snapshot, scope="ufc")

    assert set(combined["fight_url"]) == {"u/first", "u/rematch"}
    assert combined["bout_fingerprint"].duplicated().sum() == 1
    assert summary["duplicate_fingerprints"] == 1
    assert summary["duplicate_bout_keys"] == 0


def test_combined_fights_collapses_date_drift_and_keeps_corpus_membership(tmp_path: Path):
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    pd.DataFrame([
        _bout(
            "u/275",
            "Jiri Prochazka",
            "Glover Teixeira",
            "2022-06-11",
            winner="Jiri Prochazka",
        )
    ]).to_parquet(snapshot / "canonical_fights.parquet", index=False)
    pd.DataFrame(
        [
            _bout(
                "s/275",
                "Glover Teixeira",
                "Jiri Prochazka",
                "2022-06-12",
                org=None,
                source="sherdog_majors",
                winner="Jiri Prochazka",
            ),
            _bout(
                "s/other",
                "Carl Cee",
                "Dan Dee",
                "2005-01-01",
                org="PRIDE",
                source="sherdog_majors",
            ),
        ]
    ).to_parquet(snapshot / SCOPE_ARTIFACT["majors"], index=False)

    combined, summary = build_combined_fights(snapshot, scope="majors")

    assert combined["fight_url"].tolist() == ["s/other", "u/275"]
    assert combined.set_index("fight_url").loc["u/275", "available_in_corpora"] == "majors,ufc"
    assert summary["rows"] == 2
    assert summary["model_bouts"] == 2


def _three_corpus_snapshot(snapshot: Path) -> None:
    """UFC base, a majors extension, and a FightMatrix row duplicating a majors bout."""
    pd.DataFrame([_bout("u/1", "Alice", "Bob", "2024-01-01")]).to_parquet(
        snapshot / "canonical_fights.parquet", index=False
    )
    pd.DataFrame([
        _bout("s/1", "Carl", "Dana", "2010-01-01", org="PRIDE", source="sherdog_majors"),
        _bout("s/2", "Erin", "Fay", "2011-01-01", org="Bellator", source="sherdog_majors"),
    ]).to_parquet(snapshot / SCOPE_ARTIFACT["majors"], index=False)
    # The pre-unified rows are UFC bouts separated by date, not by promotion,
    # and _tag_combined reads that off the org label -- so the label matters.
    pd.DataFrame([
        _bout("p/1", "Gil", "Hana", "1999-01-01", org="UFC (pre-unified)", source="ufc"),
    ]).to_parquet(snapshot / SCOPE_ARTIFACT["pre_unified"], index=False)
    pd.DataFrame([
        # the same bout the majors corpus already carries, sides swapped
        _bout("f/1", "Dana", "Carl", "2010-01-01", org="PRIDE",
              source="fightmatrix_public", winner="Carl"),
        _bout("f/2", "Ivan", "Jo", "2015-01-01", org="ACB", source="fightmatrix_public"),
    ]).to_parquet(snapshot / SCOPE_ARTIFACT["fightmatrix"], index=False)


def test_narrowing_is_possible_when_it_is_the_intent(tmp_path: Path):
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    _three_corpus_snapshot(snapshot)
    write_combined_fights(snapshot)
    narrowed = write_combined_fights(snapshot, scope="majors", allow_narrowing=True)
    assert set(narrowed["source_corpora"]) == {"ufc", "majors"}
