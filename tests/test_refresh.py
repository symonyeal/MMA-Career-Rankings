from __future__ import annotations

import sys
from pathlib import Path

import refresh


def test_refresh_writes_board_artifacts_immediately_after_ratings(
    tmp_path: Path,
    monkeypatch,
):
    project_root = tmp_path / "project"
    greco_dir = tmp_path / "greco"
    project_root.mkdir()
    greco_dir.mkdir()
    order: list[str] = []

    monkeypatch.setattr(refresh, "copy_raw_inputs", lambda *_: None)
    monkeypatch.setattr(refresh, "previous_snapshot_dir", lambda *_: None)
    monkeypatch.setattr(refresh, "build_snapshot", lambda *_: ({"events_kept": 1}, None))

    def fake_ratings(*_args, **_kwargs):
        order.append("ratings")
        return {"current_fighters": 2, "history_rows": 3, "events_processed": 1}

    def fake_boards(snapshot_dir, *, min_rating_periods, scope):
        order.append("boards")
        assert snapshot_dir == project_root / "data" / "snapshots" / "2026-08-20"
        assert min_rating_periods == 4
        assert scope == "majors,pre_unified"
        return {
            "core_rating_col": "public_legacy_score",
            "integrity_rating_col": "mu_whr",
            "ledger_rows": 1,
            "ranked_fighters": 2,
            "withheld_fighters": 0,
        }

    def fake_changelog(*_args, **_kwargs):
        order.append("changelog")

    monkeypatch.setattr(refresh, "run_ratings", fake_ratings)
    monkeypatch.setattr(refresh, "write_board_artifacts", fake_boards)
    monkeypatch.setattr(refresh, "append_changelog", fake_changelog)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "refresh.py",
            "--project-root",
            str(project_root),
            "--greco-dir",
            str(greco_dir),
            "--snapshot-date",
            "2026-08-20",
            "--min-fights",
            "4",
            "--no-include-external",
        ],
    )

    refresh.main()

    assert order == ["ratings", "boards", "changelog"]


def test_no_flags_means_the_published_configuration():
    """A plain refresh on any machine stages what the published fit read."""
    args = refresh.parse_args([])
    assert args.include_external
    assert args.include_fightmatrix_profiles
    assert args.scope == "majors,pre_unified"

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
