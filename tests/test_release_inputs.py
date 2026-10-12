"""A release requires its evidence, not only aggregate manifests."""
import json

import pandas as pd

from check_release import check


def test_manifest_and_combined_table_do_not_prove_rebuildability(tmp_path):
    (tmp_path / "rating_run.json").write_text(json.dumps({"birth_dates": 0}))
    (tmp_path / "combined_fights.parquet").touch()

    report = check(tmp_path, inputs_only=True)

    assert not report["ready"]
    assert "canonical_rounds.parquet" in report["missing"]
    assert "career_coverage.parquet" in report["missing"]
    assert "pre_unified_fights.parquet" in report["missing"]
    assert "ratings_current.parquet" not in report["missing"]


def test_ufc_inputs_do_not_require_other_scopes(tmp_path):
    for name in ["canonical_fights", "canonical_rounds", "canonical_fighters"]:
        pd.DataFrame({"fighter": ["A"], "dob": ["2000-01-01"]}).to_parquet(tmp_path / f"{name}.parquet")

    assert check(tmp_path, scope="ufc", inputs_only=True)["ready"]
    assert not check(tmp_path, scope="ufc")["ready"]


def test_recorded_birth_dates_cannot_silently_disappear(tmp_path):
    for name in ["canonical_fights", "canonical_rounds", "canonical_fighters"]:
        pd.DataFrame({"fighter": ["A"], "dob": ["2000-01-01"]}).to_parquet(tmp_path / f"{name}.parquet")
    (tmp_path / "rating_run.json").write_text(json.dumps({"birth_dates": 2}))

    report = check(tmp_path, scope="ufc", inputs_only=True)

    assert not report["ready"]
    assert "birth dates" in report["issues"][0]
