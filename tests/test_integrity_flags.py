"""Integrity flag detection: PED + DQ + missed-weight."""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from loaders.integrity_flags import (
    _CURATED_PED_COLUMNS,
    _load_curated_ped_bouts,
    annotate_dq_wins,
    annotate_missed_weight,
    build_integrity_flags,
    confirmed_counts,
)


def _row(**overrides) -> dict:
    base = {
        "fight_url": "u/1",
        "event_date": "2024-01-01",
        "event_name": "E1",
        "fighter_a": "Alice",
        "fighter_b": "Bob",
        "winner": "Alice",
        "loser": "Bob",
        "is_draw": False,
        "method_class": "Decision - Unanimous",
        "details_text": "",
        "weight_class": "Lightweight",
    }
    base.update(overrides)
    return base


def test_dq_winner_flag_set_only_when_method_is_dq():
    df = pd.DataFrame([
        _row(),
        _row(fight_url="u/2", method_class="DQ"),
    ])
    out = annotate_dq_wins(df)
    assert bool(out.iloc[0]["is_dq"]) is False
    assert bool(out.iloc[1]["is_dq"]) is True
    assert out.iloc[1]["dq_winner"] == "Alice"


def test_missed_weight_greco_phrase_detection():
    text = "Alice missed weight by 2.5 pounds at the official weigh-in. Won by KO."
    df = pd.DataFrame([_row(details_text=text)])
    out = annotate_missed_weight(df)
    row = out.iloc[0]
    assert bool(row["missed_weight"]) is True
    assert row["missed_weight_fighter"] == "Alice"
    assert row["missed_weight_source"] == "greco"


def test_missed_weight_when_phrase_does_not_name_winner():
    text = "Bob missed weight; the bout proceeded as a catchweight."
    df = pd.DataFrame([_row(details_text=text)])
    out = annotate_missed_weight(df)
    row = out.iloc[0]
    # Winner Alice not named in text -> not flagged on her behalf.
    assert not bool(row["missed_weight"])


def test_build_integrity_flags_unions_three_sources():
    df = pd.DataFrame([
        _row(),
        _row(fight_url="u/2", method_class="DQ"),
        _row(fight_url="u/3", details_text="Alice missed weight by 1 lb"),
    ])
    flags = build_integrity_flags(df, mdabbert_csv=None)
    assert set(flags.columns).issuperset(
        {"fight_url", "ped_confirmed", "is_dq", "dq_winner",
         "missed_weight", "missed_weight_fighter", "missed_weight_source"}
    )
    assert bool(flags.iloc[1]["is_dq"]) is True
    assert flags.iloc[1]["dq_winner"] == "Alice"
    assert bool(flags.iloc[2]["missed_weight"]) is True
    assert flags.iloc[2]["missed_weight_fighter"] == "Alice"


def test_missed_weight_when_phrase_does_not_name_winner_safe_no_attribution():
    # Just exercise the negative branch to avoid relying on noisy heuristics.
    df = pd.DataFrame([_row(details_text="no relevant phrase here")])
    out = annotate_missed_weight(df)
    assert bool(out.iloc[0]["missed_weight"]) is False


def _write_curated(tmp_path: Path, rows: list[dict]) -> Path:
    path = tmp_path / "ped_bouts.csv"
    if not rows:
        df = pd.DataFrame(columns=list(_CURATED_PED_COLUMNS))
    else:
        df = pd.DataFrame(rows, columns=list(_CURATED_PED_COLUMNS))
    df.to_csv(path, index=False)
    return path


def test_load_curated_ped_bouts_missing_file_returns_empty(tmp_path):
    out = _load_curated_ped_bouts(tmp_path / "does_not_exist.csv")
    assert out.empty
    assert list(out.columns) == list(_CURATED_PED_COLUMNS)


def test_curated_ped_row_flags_named_fighter(tmp_path):
    curated = _write_curated(tmp_path, [{
        "event_date": "2024-01-01",
        "event_name": "E1",
        "fighter": "Alice",
        "opponent": "Bob",
        "sanctioning_body": "USADA",
        "substance": "turinabol",
        "finding_type": "in_competition_positive_no_overturn",
        "source_url": "https://example.test/usada/alice",
        "notes": "test row",
    }])
    df = pd.DataFrame([_row()])  # event_date 2024-01-01, event_name E1, Alice wins
    flags = build_integrity_flags(df, mdabbert_csv=None, curated_ped_csv=curated)
    row = flags.iloc[0]
    assert bool(row["ped_confirmed"]) is True
    assert row["ped_flagged_fighter"] == "Alice"
    assert row["ped_confirmation_source"] == "curated:USADA"
    assert "turinabol" in row["ped_confirmation_detail"]
    assert "https://example.test/usada/alice" in row["ped_confirmation_detail"]


def test_curated_ped_row_unresolved_event_warns_and_skips(tmp_path, caplog):
    curated = _write_curated(tmp_path, [{
        "event_date": "2024-01-01",
        "event_name": "Nonexistent Event",
        "fighter": "Alice",
        "opponent": "Bob",
        "sanctioning_body": "USADA",
        "substance": "turinabol",
        "finding_type": "in_competition_positive_no_overturn",
        "source_url": "https://example.test/x",
        "notes": "",
    }])
    df = pd.DataFrame([_row()])
    with caplog.at_level(logging.WARNING, logger="loaders.integrity_flags"):
        flags = build_integrity_flags(df, mdabbert_csv=None, curated_ped_csv=curated)
    assert bool(flags.iloc[0]["ped_confirmed"]) is False
    assert any("does not resolve" in rec.message for rec in caplog.records)


def test_curated_ped_row_unknown_fighter_warns_and_skips(tmp_path, caplog):
    curated = _write_curated(tmp_path, [{
        "event_date": "2024-01-01",
        "event_name": "E1",
        "fighter": "Charlie",  # neither fighter_a nor fighter_b
        "opponent": "Dana",
        "sanctioning_body": "USADA",
        "substance": "turinabol",
        "finding_type": "in_competition_positive_no_overturn",
        "source_url": "https://example.test/x",
        "notes": "",
    }])
    df = pd.DataFrame([_row()])
    with caplog.at_level(logging.WARNING, logger="loaders.integrity_flags"):
        flags = build_integrity_flags(df, mdabbert_csv=None, curated_ped_csv=curated)
    assert bool(flags.iloc[0]["ped_confirmed"]) is False
    assert any("not in the bout" in rec.message for rec in caplog.records)


def test_curated_ped_row_takes_precedence_over_regex(tmp_path):
    text = "Won by Submission. Overturned - Failed Drug Test by Alice"
    curated = _write_curated(tmp_path, [{
        "event_date": "2024-01-01",
        "event_name": "E1",
        "fighter": "Alice",
        "opponent": "Bob",
        "sanctioning_body": "NSAC",
        "substance": "drostanolone",
        "finding_type": "overturned_result",
        "source_url": "https://example.test/nsac/alice",
        "notes": "",
    }])
    df = pd.DataFrame([_row(details_text=text)])
    flags = build_integrity_flags(df, mdabbert_csv=None, curated_ped_csv=curated)
    row = flags.iloc[0]
    assert bool(row["ped_confirmed"]) is True
    assert row["ped_flagged_fighter"] == "Alice"
    # Curated source string replaces the Greco one.
    assert row["ped_confirmation_source"] == "curated:NSAC"
    assert "drostanolone" in row["ped_confirmation_detail"]


def test_confirmed_counts_aggregates_per_fighter():
    flags = pd.DataFrame([
        {"fight_url": "u/1", "ped_confirmed": True,  "ped_flagged_fighter": "Alice",
         "is_dq": False, "dq_winner": None,
         "missed_weight": False, "missed_weight_fighter": None},
        {"fight_url": "u/2", "ped_confirmed": False, "ped_flagged_fighter": None,
         "is_dq": True, "dq_winner": "Alice",
         "missed_weight": False, "missed_weight_fighter": None},
        {"fight_url": "u/3", "ped_confirmed": False, "ped_flagged_fighter": None,
         "is_dq": False, "dq_winner": None,
         "missed_weight": True, "missed_weight_fighter": "Alice"},
    ])
    counts = confirmed_counts(flags).set_index("fighter")
    assert int(counts.loc["Alice", "ped_confirmed_fights"]) == 1
    assert int(counts.loc["Alice", "dq_wins"]) == 1
    assert int(counts.loc["Alice", "missed_weight_wins"]) == 1
