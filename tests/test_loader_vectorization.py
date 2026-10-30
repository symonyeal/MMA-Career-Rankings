"""Parity for vectorized source loader hot paths."""
from __future__ import annotations

import re

import pandas as pd
from pandas.testing import assert_frame_equal

from loaders.ufcstats_loader import (
    _pair_col_names,
    _PAIR_COLS,
    build_canonical_rounds,
    parse_mmss_to_seconds,
)
from loaders.crossorg_identity import (
    _overlap,
    _overlap_index,
    _overlap_scores,
    resolve_by_bout_evidence,
)


def parse_x_of_y(s):
    """'5 of 11' -> (5, 11). '--'/empty/None -> (None, None)."""
    if not isinstance(s, str):
        return (None, None)
    m = re.match(r"^\s*(\d+)\s*of\s*(\d+)\s*$", s)
    if not m:
        return (None, None)
    return int(m.group(1)), int(m.group(2))


def parse_pct(s):
    if not isinstance(s, str):
        return None
    m = re.match(r"^\s*(\d+)\s*%\s*$", s)
    if not m:
        return None
    return int(m.group(1))


def _old_build_canonical_rounds(stats: pd.DataFrame, fights: pd.DataFrame) -> pd.DataFrame:
    """Pre-vectorization implementation retained as an executable oracle."""
    s = stats.copy()
    s["event_name"] = s["EVENT"]
    s["bout_string"] = s["BOUT"]
    s = s.merge(
        fights[["event_name", "bout_string", "fight_url", "event_date"]],
        on=["event_name", "bout_string"], how="left",
    )
    s["round_num"] = s["ROUND"].astype("string").str.extract(r"Round\s*(\d+)").astype("Int64")
    for col in _PAIR_COLS:
        values = s[col].apply(lambda v, c=col: pd.Series(parse_x_of_y(v), index=_pair_col_names(c)))
        s = pd.concat([s, values], axis=1)
    s["kd"] = pd.to_numeric(s["KD"], errors="coerce").astype("Int64")
    s["sub_att"] = pd.to_numeric(s["SUB.ATT"], errors="coerce").astype("Int64")
    s["rev"] = pd.to_numeric(s["REV."], errors="coerce").astype("Int64")
    s["sig_str_pct"] = s["SIG.STR. %"].apply(parse_pct)
    s["td_pct"] = s["TD %"].apply(parse_pct)
    s["ctrl_seconds"] = s["CTRL"].apply(parse_mmss_to_seconds)
    s["fighter"] = s["FIGHTER"]
    keep = [
        "fight_url", "event_name", "event_date", "bout_string", "round_num", "fighter", "kd",
        "sig_str_landed", "sig_str_attempted", "sig_str_pct", "total_str_landed",
        "total_str_attempted", "td_landed", "td_attempted", "td_pct", "sub_att", "rev",
        "ctrl_seconds", "head_landed", "head_attempted", "body_landed", "body_attempted",
        "leg_landed", "leg_attempted", "distance_landed", "distance_attempted",
        "clinch_landed", "clinch_attempted", "ground_landed", "ground_attempted",
    ]
    return s[keep].copy()


def test_canonical_rounds_matches_old_function_on_malformed_and_missing_values():
    stats = pd.DataFrame({
        "EVENT": ["E", "E", "missing", "E"],
        "BOUT": ["A vs. B", "A vs. B", "C vs. D", "A vs. B"],
        "ROUND": ["Round 1", "Round 2", "Round x", None],
        "FIGHTER": ["A", "B", "C", "A"],
        "KD": ["0", "--", None, "2"], "SUB.ATT": ["1", "2", "bad", "3"],
        "REV.": ["0", "0", "--", "1"], "SIG.STR. %": ["10%", "--", " 4 %", "3.5%"],
        "TD %": ["0%", "bad", None, "100 %"], "CTRL": ["1:02", "--", "x:2", "10:90"],
    })
    for col in _PAIR_COLS:
        stats[col] = ["5 of 11", "--", None, "1of2"]
    fights = pd.DataFrame({
        "event_name": ["E"], "bout_string": ["A vs. B"], "fight_url": ["url"],
        "event_date": [pd.Timestamp("2020-01-01")],
    })
    assert_frame_equal(
        build_canonical_rounds(stats, fights), _old_build_canonical_rounds(stats, fights),
        check_dtype=True, check_exact=True,
    )


def test_canonical_rounds_matches_old_function_for_all_valid_and_all_missing():
    fights = pd.DataFrame({
        "event_name": ["E"], "bout_string": ["A vs. B"], "fight_url": ["url"],
        "event_date": [pd.Timestamp("2020-01-01")],
    })
    for values in (["1 of 2", "3 of 4"], [None, "--"]):
        stats = pd.DataFrame({
            "EVENT": ["E", "E"], "BOUT": ["A vs. B", "A vs. B"],
            "ROUND": ["Round 1", "Round 2"], "FIGHTER": ["A", "B"],
            "KD": ["0", "1"], "SUB.ATT": ["0", "1"], "REV.": ["0", "0"],
            "SIG.STR. %": ["10%", "20%"], "TD %": ["0%", "50%"],
            "CTRL": ["0:00", "1:02"],
        })
        for col in _PAIR_COLS:
            stats[col] = values
        assert_frame_equal(
            build_canonical_rounds(stats, fights), _old_build_canonical_rounds(stats, fights),
            check_dtype=True, check_exact=True,
        )


def test_indexed_identity_overlap_matches_pairwise_rule():
    day = pd.Timestamp("2020-01-01")
    canonical = {
        "A": {(day, "x"), (day + pd.Timedelta(days=2), "y")},
        "B": {(day + pd.Timedelta(days=1), "x"), (day, "z")},
        "C": {(day + pd.Timedelta(days=4), "x")},
    }
    mine = {(day, "x"), (day + pd.Timedelta(days=2), "y"), (day, "z")}
    assert _overlap_scores(mine, _overlap_index(canonical)) == {
        name: _overlap(mine, records) for name, records in canonical.items()
        if _overlap(mine, records)
    }


def test_identity_minimum_overlap_zero_preserves_zero_score_candidates():
    identity = pd.DataFrame({
        "sherdog_id": ["1"], "sherdog_name": ["Unjoined"],
        "canonical_name": ["Unjoined"], "join_method": ["unjoined"],
        "claimed_canonical_name": ["Unjoined"],
    })
    bouts = pd.DataFrame({
        "fighter_a_id": ["1"], "fighter_b_id": ["2"],
        "fighter_a": ["Unjoined"], "fighter_b": ["Opponent"],
        "event_date": [pd.Timestamp("2020-01-01")],
    })
    fights = pd.DataFrame({
        "fighter_a": ["Only candidate"], "fighter_b": ["Only candidate"],
        "event_date": [pd.Timestamp("2021-01-01")],
    })
    result = resolve_by_bout_evidence(identity, bouts, fights, min_overlap=0)
    assert result.loc[0, "canonical_name"] == "Only candidate"
    assert result.loc[0, "join_method"] == "bout_evidence"
