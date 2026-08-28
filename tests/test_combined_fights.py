from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from loaders.combined_fights import (
    max_coverage_scope,
    build_combined_fights,
    load_combined_fights,
    select_scope,
    write_combined_fights,
)
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


def test_selecting_a_scope_from_max_coverage_matches_merging_that_scope(tmp_path: Path):
    """A named scope must be a filter on the one table, not a second build.

    Verified on the real snapshot as well: selecting ``majors,pre_unified`` out
    of the ``all`` table returned the same 67,920 model bouts as merging that
    scope directly, with zero rows on either side of the difference. That check
    ran on the pre-career-coverage-repair corpus; the equality is structural, so
    the count is only there to say the check was run against real data.
    """
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    _three_corpus_snapshot(snapshot)

    narrow, _ = build_combined_fights(snapshot, scope="majors,pre_unified")
    wide, _ = build_combined_fights(snapshot, scope="all")
    selected = select_scope(wide, "majors,pre_unified")

    assert set(narrow.loc[narrow["is_model_bout"], "bout_fingerprint"]) == set(
        selected.loc[selected["is_model_bout"], "bout_fingerprint"]
    )
    assert set(selected["source_corpus"]) == {"ufc", "majors", "pre_unified"}
    assert (selected["rated_scope"] == "majors,pre_unified").all()


def test_max_coverage_resolves_a_shared_bout_to_the_higher_priority_source(tmp_path: Path):
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    _three_corpus_snapshot(snapshot)

    wide, _ = build_combined_fights(snapshot, scope="all")
    assert wide["bout_fingerprint"].is_unique
    # Carl/Dana arrives from both corpora; the Sherdog parse outranks FightMatrix.
    shared = wide[wide["fighter_a"].isin({"Carl", "Dana"}) & wide["fighter_b"].isin({"Carl", "Dana"})]
    assert len(shared) == 1
    assert shared.iloc[0]["source_corpus"] == "majors"
    # ... so selecting the fightmatrix scope returns that one row, not a copy.
    fm = select_scope(wide, "fightmatrix")
    assert set(fm["fight_url"]) == {"u/1", "f/2"}


def test_written_artifact_defaults_to_maximum_coverage(tmp_path: Path):
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    _three_corpus_snapshot(snapshot)

    summary = write_combined_fights(snapshot)
    assert summary["scope"] == max_coverage_scope(snapshot)
    assert set(summary["source_corpora"]) == {"ufc", "majors", "pre_unified", "fightmatrix"}

    loaded, loaded_summary = load_combined_fights(snapshot, scope="majors,pre_unified")
    assert set(loaded["source_corpus"]) == {"ufc", "majors", "pre_unified"}
    assert loaded_summary["scope"] == "majors,pre_unified"


def test_loading_a_scope_the_artifact_cannot_cover_rebuilds_rather_than_truncating(tmp_path: Path):
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    _three_corpus_snapshot(snapshot)

    # An artifact written before a corpus was staged must not cap a later run.
    write_combined_fights(snapshot, scope="majors")
    loaded, summary = load_combined_fights(snapshot, scope="majors,pre_unified")
    assert set(loaded["source_corpus"]) == {"ufc", "majors", "pre_unified"}
    assert summary["scope"] == "majors,pre_unified"


def test_writing_never_silently_drops_a_corpus_the_artifact_already_holds(tmp_path: Path):
    """Archiving the staged inputs must not shrink the authoritative table."""
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    _three_corpus_snapshot(snapshot)
    wide = write_combined_fights(snapshot)
    assert set(wide["source_corpora"]) == {"ufc", "majors", "pre_unified", "fightmatrix"}

    # The staged parquets are build inputs; archive them and rebuild.
    for source in ("majors", "pre_unified", "fightmatrix"):
        (snapshot / SCOPE_ARTIFACT[source]).unlink()

    kept = write_combined_fights(snapshot)
    assert set(kept["source_corpora"]) == {"ufc", "majors", "pre_unified", "fightmatrix"}
    still_wide = pd.read_parquet(snapshot / "combined_fights.parquet")
    assert set(still_wide["source_corpus"]) == {"ufc", "majors", "pre_unified", "fightmatrix"}
    # ... and the published scope still selects out of it.
    loaded, _ = load_combined_fights(snapshot, scope="majors,pre_unified")
    assert set(loaded["source_corpus"]) == {"ufc", "majors", "pre_unified"}


def test_narrowing_is_possible_when_it_is_the_intent(tmp_path: Path):
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    _three_corpus_snapshot(snapshot)
    write_combined_fights(snapshot)
    narrowed = write_combined_fights(snapshot, scope="majors", allow_narrowing=True)
    assert set(narrowed["source_corpora"]) == {"ufc", "majors"}
