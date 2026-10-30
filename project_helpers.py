"""Small shared helpers used across loaders, database, and analysis."""
from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent


def project_path(path: Path) -> str:
    """Repository-relative POSIX path, or an absolute path for an external input."""
    path = Path(path).resolve()
    return (path.relative_to(PROJECT_ROOT) if path.is_relative_to(PROJECT_ROOT) else path).as_posix()

# P_ID_ALIAS : project-owned source-id/name override table
# RE_SID     : terminal Sherdog-id display suffix

_ALIAS_CACHE_PATH = PROJECT_ROOT / "data" / "external" / "aliases" / "fighter_aliases.csv"
P_ID_ALIAS = (
    PROJECT_ROOT / "data" / "external" / "crossorg" / "identity_overrides.csv"
)
RE_SID = re.compile(r"\s*\(sherdog:\d+\)\s*$", flags=re.IGNORECASE)


@lru_cache(maxsize=1)
def _load_alias_map() -> dict[str, str]:
    """Load safe global aliases without weakening source-id disambiguation.

    Mapping is ``normalized_alias -> normalized_canonical``. Returns an
    empty mapping if the CSV is missing so the rest of the codebase keeps
    working before the aliases are staged. The Tiger Millionaire aliases are
    name-level by design. Project-owned cross-source overrides join globally
    only when their Sherdog id is blank; id-specific rows stay id-specific so
    a namesake cannot inherit another fighter's career.
    """
    if not _ALIAS_CACHE_PATH.exists():
        return {}
    try:
        df = pd.read_csv(_ALIAS_CACHE_PATH, usecols=["fighter", "alias"])
    except (FileNotFoundError, ValueError, KeyError):
        return {}
    mapping: dict[str, str] = {}
    for _, row in df.iterrows():
        canonical = row.get("fighter")
        alias = row.get("alias")
        if not isinstance(canonical, str) or not isinstance(alias, str):
            continue
        canonical_key = _basic_name_key(canonical)
        alias_key = _basic_name_key(alias)
        if not canonical_key or not alias_key or canonical_key == alias_key:
            continue
        mapping[alias_key] = canonical_key

    if P_ID_ALIAS.exists():
        try:
            df = pd.read_csv(
                P_ID_ALIAS,
                dtype={"sherdog_id": "string"},
                keep_default_na=False,
            )
        except (FileNotFoundError, ValueError, KeyError):
            df = pd.DataFrame()
        if {"sherdog_id", "sherdog_name", "canonical_name"} <= set(df.columns):
            sid = df["sherdog_id"].astype("string").fillna("").str.strip()
            for _, row in df[sid.eq("")].iterrows():
                canonical = row.get("canonical_name")
                alias = row.get("sherdog_name")
                if not isinstance(canonical, str) or not isinstance(alias, str):
                    continue
                canonical_key = _basic_name_key(canonical)
                alias_key = _basic_name_key(alias)
                if canonical_key and alias_key and canonical_key != alias_key:
                    mapping[alias_key] = canonical_key
    return mapping


def _basic_name_key(name: str | None, *, compact: bool = False) -> str:
    if not isinstance(name, str):
        return ""
    text = unicodedata.normalize("NFKD", RE_SID.sub("", name))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.strip().lower()
    if compact:
        text = "".join(ch for ch in text if ch.isalnum())
    return text


def _alias_key(name: str, aliases: dict[str, str], compact: bool) -> str:
    key = _basic_name_key(name, compact=False)
    if key:
        key = aliases.get(key, key)
    if compact:
        key = "".join(ch for ch in key if ch.isalnum())
    return key


# M_NK : name -> alias-applied key, one dict per ``compact`` flag, valid for the alias map object held in M_MAP.
# A name occurs in millions of rows but is only a few tens of thousands of distinct strings; the key is a pure
# function of (name, compact, alias map), and str is immutable, so sharing the stored result is safe.
M_NK: tuple[dict[str, str], dict[str, str]] = ({}, {})
M_MAP: list[dict[str, str] | None] = [None]
M_CAP = 1 << 21


def normalize_name_key(name: str | None, *, compact: bool = False, apply_aliases: bool = True) -> str:
    """Lowercase, strip, and ASCII-fold names for fuzzy joins.

    ``compact=True`` additionally removes non-alphanumeric characters, which
    is useful for cross-source joins where punctuation spacing varies.

    When ``apply_aliases`` is true the staged fighter-alias map is applied
    so e.g. ``"Francisco Figueredo"`` collapses to the same key as
    ``"Francisco Figueiredo"``. The map is loaded once and cached.
    """
    if not isinstance(name, str):
        return ""
    if not apply_aliases:
        key = _basic_name_key(name, compact=False)
        return "".join(ch for ch in key if ch.isalnum()) if compact else key
    aliases = _load_alias_map()
    if aliases is not M_MAP[0]:  # alias map reloaded or replaced: every stored key is stale
        M_NK[0].clear()
        M_NK[1].clear()
        M_MAP[0] = aliases
    memo = M_NK[bool(compact)]
    key = memo.get(name)
    if key is None:
        if len(memo) >= M_CAP:
            memo.clear()
        key = memo[name] = _alias_key(name, aliases, bool(compact))
    return key


def compact_name_keys(names: pd.Series) -> list[str]:
    """``normalize_name_key(n, compact=True)`` per element, computed once per distinct name.

    Factorizing first matters: iterating an Arrow-backed string column costs more than the key itself.
    Missing values get code -1, which indexes the trailing ``""``, as ``normalize_name_key(NaN)`` does.
    """
    codes, uniq = pd.factorize(names)
    k = np.array([normalize_name_key(n, compact=True) for n in uniq] + [""], dtype=object)
    return k[codes].tolist()


def bout_fingerprint(frame: pd.DataFrame) -> pd.Series:
    """``YYYYMMDD::<name>::<name>`` per bout, order-independent.

    The one identity a bout has across sources: UFCStats, Sherdog and
    FightMatrix agree on who fought whom on what day and on nothing else --
    not the URL, not the event name, not the spelling of the method. Two rows
    sharing a fingerprint are the same bout and must not both update a rating.
    """
    dates = pd.to_datetime(frame["event_date"], errors="coerce")
    codes, uniq = pd.factorize(dates)  # a card's bouts share one date: format each distinct date once
    if len(uniq):
        s = np.array(list(pd.Series(uniq).dt.strftime("%Y%m%d")) + [np.nan], dtype=object)
        dates = pd.Series(s[codes].tolist(), index=frame.index).fillna("")
    else:  # all-NaT or empty: the list route would infer object, not str, dtype
        dates = dates.dt.strftime("%Y%m%d").fillna("")
    pairs = [
        f"{x}::{y}" if x <= y else f"{y}::{x}"
        for x, y in zip(compact_name_keys(frame["fighter_a"]), compact_name_keys(frame["fighter_b"]))
    ]
    return dates + "::" + pd.Series(pairs, index=frame.index)


def date_range(df: pd.DataFrame) -> tuple[str | None, str | None]:
    """Return the first usable min/max date range from a snapshot table."""
    for col in ("event_date", "last_event_date", "last_event_date_method", "dob"):
        if col not in df.columns:
            continue
        dates = pd.to_datetime(df[col], errors="coerce").dropna()
        if not dates.empty:
            return str(dates.min().date()), str(dates.max().date())
    return None, None


def group_bounds(*keys: pd.Series) -> tuple[np.ndarray, np.ndarray]:
    """Half-open row ranges of each run of equal key tuples in an already-sorted frame.

    The equivalent of ``groupby(sort=False)`` over a frame that is already
    ordered by those keys, without materializing a group object per event.
    """
    n = len(keys[0])
    if n == 0:
        return np.empty(0, dtype=np.int64), np.empty(0, dtype=np.int64)
    changed = np.zeros(n - 1, dtype=bool)
    for key in keys:
        values = key.to_numpy()
        changed |= values[1:] != values[:-1]
    boundary = np.flatnonzero(changed) + 1
    starts = np.concatenate(([0], boundary))
    stops = np.concatenate((boundary, [n]))
    return starts, stops


def map_distinct(values: pd.Series, f) -> pd.Series:
    """``values.map(f)`` calling ``f`` once per distinct value (NaN included), same dtype inference as ``map``.

    The distinct values are the first occurrences themselves, not ``factorize``'s uniques, which turn every NA into
    NaN. The difference is visible: a string-dtype column turns the ``None`` that ``_winner_key`` returns into NaN,
    which the ``if value`` test in ``_result_key`` then reads as a winner, while an object column keeps ``None``.
    """
    codes, _ = pd.factorize(values, use_na_sentinel=False)
    first = np.unique(codes, return_index=True)[1]
    return values.iloc[first].map(f).take(codes).set_axis(values.index)
