"""Small shared helpers used across loaders, database, and analysis."""
from __future__ import annotations

import unicodedata
from functools import lru_cache
from pathlib import Path

import pandas as pd


_ALIAS_CACHE_PATH = Path(__file__).resolve().parent / "data" / "external" / "aliases" / "fighter_aliases.csv"


@lru_cache(maxsize=1)
def _load_alias_map() -> dict[str, str]:
    """Load fighter alias map from the staged tiger-millionaire export.

    Mapping is ``normalized_alias -> normalized_canonical``. Returns an
    empty mapping if the CSV is missing so the rest of the codebase keeps
    working before the aliases are staged.
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
    return mapping


def _basic_name_key(name: str | None, *, compact: bool = False) -> str:
    if not isinstance(name, str):
        return ""
    text = unicodedata.normalize("NFKD", name)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.strip().lower()
    if compact:
        text = "".join(ch for ch in text if ch.isalnum())
    return text


def normalize_name_key(name: str | None, *, compact: bool = False, apply_aliases: bool = True) -> str:
    """Lowercase, strip, and ASCII-fold names for fuzzy joins.

    ``compact=True`` additionally removes non-alphanumeric characters, which
    is useful for cross-source joins where punctuation spacing varies.

    When ``apply_aliases`` is true the staged fighter-alias map is applied
    so e.g. ``"Francisco Figueredo"`` collapses to the same key as
    ``"Francisco Figueiredo"``. The map is loaded once and cached.
    """
    key = _basic_name_key(name, compact=False)
    if apply_aliases and key:
        aliases = _load_alias_map()
        key = aliases.get(key, key)
    if compact:
        key = "".join(ch for ch in key if ch.isalnum())
    return key


def date_range(df: pd.DataFrame) -> tuple[str | None, str | None]:
    """Return the first usable min/max date range from a snapshot table."""
    for col in ("event_date", "last_event_date", "last_event_date_method", "dob"):
        if col not in df.columns:
            continue
        dates = pd.to_datetime(df[col], errors="coerce").dropna()
        if not dates.empty:
            return str(dates.min().date()), str(dates.max().date())
    return None, None
