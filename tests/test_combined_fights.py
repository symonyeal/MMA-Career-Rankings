from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from loaders.combined_fights import build_combined_fights, write_combined_fights
from ratings.scope import SCOPE_ARTIFACT


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
            _bout("u/2", "Bob", "Alice", "2024-01-01"),
        ]
    )
    duplicated.to_parquet(snapshot / "canonical_fights.parquet", index=False)

    with pytest.raises(ValueError, match="duplicate bout fingerprints"):
        build_combined_fights(snapshot, scope="ufc")
