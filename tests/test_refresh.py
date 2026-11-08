from __future__ import annotations

import sys
from pathlib import Path

import pytest

import refresh


def test_refresh_stages_then_runs_the_model_then_writes_the_changelog(tmp_path: Path, monkeypatch):
    project_root = tmp_path / "project"
    greco_dir = tmp_path / "greco"
    snapshot = project_root / "data" / "snapshots" / "2026-08-20"
    snapshot.mkdir(parents=True)
    greco_dir.mkdir()
    order: list[str] = []

    monkeypatch.setattr(refresh, "copy_raw_inputs", lambda *_: None)
    monkeypatch.setattr(refresh, "previous_snapshot_dir", lambda *_: None)
    monkeypatch.setattr(refresh, "build_snapshot", lambda *_: ({"events_kept": 1}, None))
    monkeypatch.setattr(refresh, "stage_scopes", lambda *_: order.append("stage"))
    monkeypatch.setattr(refresh, "write_combined_fights", lambda *_: order.append("combined"))

    def fake_coverage(snapshot_dir, scope):
        order.append("coverage")
        assert scope == "majors,pre_unified"
        return {"eligible": 0}

    def fake_model(command, *, cwd, check):
        order.append("model")
        assert command[-1] == str(snapshot) and cwd == project_root and check
        (snapshot / "rating_run.json").write_text('{"current_fighters": 2}', encoding="utf-8")

    def fake_changelog(root, date, counts, summary, coverage, previous):
        order.append("changelog")
        assert summary == {"current_fighters": 2} and coverage == {"eligible": 0}

    monkeypatch.setattr(refresh, "require_coverage", fake_coverage)
    monkeypatch.setattr(refresh.subprocess, "run", fake_model)
    monkeypatch.setattr(refresh, "append_changelog", fake_changelog)
    monkeypatch.setattr(sys, "argv", [
        "refresh.py", "--project-root", str(project_root), "--greco-dir", str(greco_dir),
        "--snapshot-date", "2026-08-20", "--no-include-external",
    ])

    refresh.main()

    assert order == ["stage", "combined", "coverage", "model", "changelog"]


def test_no_flags_means_the_published_configuration():
    """A plain refresh on any machine stages what the published fit read."""
    args = refresh.parse_args([])
    assert args.include_external
    assert args.include_fightmatrix_profiles

    opted_out = refresh.parse_args(["--no-include-external"])
    assert not opted_out.include_fightmatrix_profiles


def test_profile_staging_into_a_new_snapshot_does_not_need_ratings(tmp_path):
    """``refresh.py --snapshot-date <new date>`` stages FightMatrix profiles
    before the ratings exist. It used to read ``ratings_current.parquet`` from
    the new folder for a bout weight the production fit discards, and crashed."""
    import pandas as pd

    from loaders.fightmatrix_profiles import crossorg_org_weights

    fights = pd.DataFrame({
        "fighter_a": ["A", "B"], "fighter_b": ["C", "D"],
        "event_date": pd.to_datetime(["2026-09-01", "2026-09-02"]),
    })
    weights = crossorg_org_weights(fights, tmp_path)
    assert weights.tolist() == [1.0, 1.0]
    assert weights.index.equals(fights.index)


def test_the_changelog_compares_against_the_previous_release_not_a_research_run(tmp_path):
    """``2026-08-13-fightmatrix-public`` sorts after ``2026-08-13``, so picking the
    greatest name before the new date compared a refresh with a research run and
    published movers such as Brendan Loughnane +923."""
    for name in ("2026-06-23", "2026-08-13", "2026-08-13-fightmatrix-public"):
        folder = tmp_path / "data" / "snapshots" / name
        folder.mkdir(parents=True)
        (folder / "ratings_current.parquet").write_bytes(b"")
    previous = refresh.previous_snapshot_dir(tmp_path, "2026-10-14")
    assert previous is not None and previous.name == "2026-08-13"


def test_a_published_scope_that_cannot_stage_stops_the_refresh(tmp_path: Path, monkeypatch):
    def missing(_snapshot):
        raise FileNotFoundError("no sherdog corpus")

    monkeypatch.setattr(refresh, "stage_pre_unified_scope", missing)
    monkeypatch.setattr(refresh, "DEFAULT_PUBLISHED_SCOPE", "pre_unified,majors")
    with pytest.raises(FileNotFoundError, match="sherdog"):
        refresh.stage_scopes(tmp_path)


def test_an_unpublished_scope_that_cannot_stage_is_reported(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(refresh, "stage_pre_unified_scope", lambda _s: {"bouts": 1})
    monkeypatch.setattr("loaders.majors_scope.stage_majors_scope", lambda _s: (_ for _ in ()).throw(ValueError("x")))
    monkeypatch.setattr(refresh, "DEFAULT_PUBLISHED_SCOPE", "pre_unified")
    staged = refresh.stage_scopes(tmp_path)
    assert staged["majors"].startswith("not staged")
