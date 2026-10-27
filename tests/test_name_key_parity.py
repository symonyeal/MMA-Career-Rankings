"""The memoized name keys and the vectorized fingerprint must equal the original row-by-row code bit for bit."""
from __future__ import annotations

import unicodedata

import numpy as np
import pandas as pd
import pytest

import project_helpers as ph

# ref_* : the pre-memo implementations, kept verbatim as the reference the fast paths are held to

NAMES = [
    "Jon Jones", "  JON   JONES ", "José Aldo", "JOSÉ ALDO", "Jose Aldo", "Sean O’Malley", "O'Malley",
    "T.J. Dillashaw", "TJ Dillashaw", "Francisco Figueredo", "Francisco Figueiredo", "Patricio Pitbull",
    "Bruno Silva (sherdog:118601)", "Bruno Silva (SHERDOG:5) ", "(sherdog:1)", "x (sherdog:12", "ﬁ ligature",
    "ｆｕｌｌｗｉｄｔｈ", "İstanbul", "ß straße", "٣٤", "²³", "名前 テスト", "___", "...", "\u200b", "e\u0301",
    "A\u0301lvarez", "tab\tname", "\xa0nbsp\xa0", "", " ", None, float("nan"), pd.NA, 0, 1.5, [], np.str_("Jon Jones"),
]


def ref_basic(name, *, compact=False):
    if not isinstance(name, str):
        return ""
    text = unicodedata.normalize("NFKD", ph.RE_SID.sub("", name))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.strip().lower()
    if compact:
        text = "".join(ch for ch in text if ch.isalnum())
    return text


def ref_key(name, *, compact=False, apply_aliases=True):
    key = ref_basic(name, compact=False)
    if apply_aliases and key:
        key = ph._load_alias_map().get(key, key)
    if compact:
        key = "".join(ch for ch in key if ch.isalnum())
    return key


def ref_fingerprint(frame):
    dates = pd.to_datetime(frame["event_date"], errors="coerce").dt.strftime("%Y%m%d").fillna("")
    pairs = [
        "::".join(sorted([ref_key(a, compact=True), ref_key(b, compact=True)]))
        for a, b in zip(frame["fighter_a"], frame["fighter_b"])
    ]
    return dates + "::" + pd.Series(pairs, index=frame.index)


@pytest.mark.parametrize("compact", [False, True])
@pytest.mark.parametrize("aliases", [False, True])
def test_key_equals_reference_cold_and_warm(compact, aliases):
    for d in ph.M_NK:
        d.clear()
    for _ in range(2):  # second pass is served from the memo
        for n in NAMES:
            got, want = ph.normalize_name_key(n, compact=compact, apply_aliases=aliases), ref_key(
                n, compact=compact, apply_aliases=aliases)
            assert got == want and type(got) is type(want) is str, (n, got, want)


def test_memo_follows_a_replaced_alias_map(monkeypatch):
    assert ph.normalize_name_key("Zed Alpha") == "zed alpha"
    monkeypatch.setattr(ph, "_load_alias_map", lambda: {"zed alpha": "zed beta"})
    assert ph.normalize_name_key("Zed Alpha") == "zed beta"
    assert ph.normalize_name_key("Zed Alpha", compact=True) == "zedbeta"
    monkeypatch.undo()
    assert ph.normalize_name_key("Zed Alpha") == "zed alpha"


def test_compact_name_keys_maps_missing_to_empty():
    s = pd.Series(["José  Aldo", None, "o'malley", np.nan, "José  Aldo", ""])
    assert ph.compact_name_keys(s) == [ref_key(v, compact=True) for v in s]
    assert ph.compact_name_keys(s.astype(object)) == ph.compact_name_keys(s)
    assert ph.compact_name_keys(pd.Series([], dtype=object)) == []


def frames():
    d = pd.to_datetime(["2020-01-02", "2020-01-02", "1999-12-31", None, "2020-01-03"])
    yield pd.DataFrame({"event_date": d, "fighter_a": ["B b", "a.b", None, "x", "Zed"],
                        "fighter_b": ["a b", "A-B", "y", np.nan, "Zed"]})
    yield pd.DataFrame({"event_date": ["2020-01-02", "bad", None], "fighter_a": ["a", None, "é"],
                        "fighter_b": ["b", "c", "e"]}, index=[7, 7, 3])
    yield pd.DataFrame({"event_date": [pd.NaT, pd.NaT], "fighter_a": ["a", "b"], "fighter_b": ["c", None]})
    yield pd.DataFrame({"event_date": pd.to_datetime(["0900-01-02", "2262-01-01"]), "fighter_a": ["a", "b"],
                        "fighter_b": ["c", "d"]})
    yield pd.DataFrame({"event_date": pd.to_datetime(["2020-01-02 23:00", None]).tz_localize("UTC"),
                        "fighter_a": ["a", "b"], "fighter_b": ["c", "d"]})
    yield pd.DataFrame({"event_date": pd.Series([], dtype="datetime64[us]"), "fighter_a": pd.Series([], dtype=str),
                        "fighter_b": pd.Series([], dtype=str)})


@pytest.mark.parametrize("k", range(6))
def test_fingerprint_equals_reference(k):
    f = list(frames())[k]
    if f.empty:  # pandas < 3.1 raises TypeError on str + empty object column; 3.1 returns an empty str Series
        try:
            ref_fingerprint(f)
        except TypeError:
            with pytest.raises(TypeError):
                ph.bout_fingerprint(f)
            return
    got, want = ph.bout_fingerprint(f), ref_fingerprint(f)
    assert got.dtype == want.dtype and got.name == want.name
    assert got.index.equals(want.index) and got.tolist() == want.tolist()
    assert got.equals(want)
