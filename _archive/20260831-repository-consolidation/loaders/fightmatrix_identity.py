"""Profile-ID-first identity resolution for public FightMatrix data."""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import pandas as pd

from project_helpers import normalize_name_key


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OVERRIDES_PATH = (
    PROJECT_ROOT / "data" / "external" / "fightmatrix" / "identity_overrides.csv"
)


def identity_name_key(name: str | None) -> str:
    """Normalize Unicode/punctuation/nicknames while retaining suffix identity."""
    if not isinstance(name, str):
        return ""
    value = unicodedata.normalize("NFKD", name)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = re.sub(r'\s+["“”‘’\'][^"“”‘’\']+["“”‘’\']\s+', " ", value)
    value = value.replace("’", "'").replace("‐", "-").replace("‑", "-")
    value = re.sub(r"\b(junior)\b", "jr", value, flags=re.IGNORECASE)
    value = re.sub(r"\b(senior)\b", "sr", value, flags=re.IGNORECASE)
    return normalize_name_key(value, compact=True, apply_aliases=True)


def _valid_profile_id(value) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    return text if text.isdigit() else None


def build_identity_artifacts(
    profiles: pd.DataFrame,
    bouts: pd.DataFrame,
    ufc_fighters: pd.DataFrame | None = None,
    *,
    overrides_path: Path = DEFAULT_OVERRIDES_PATH,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build a stable identity map and an explicit exception ledger.

    Exact normalized-name matches are accepted only when unique on both sides.
    Ambiguous names never merge without a committed manual override.
    """
    names_by_id: dict[str, set[str]] = {}
    for frame, id_col, name_col in (
        (profiles, "profile_id", "fighter"),
        (bouts, "fighter_profile_id", "fighter"),
        (bouts, "opponent_profile_id", "opponent"),
    ):
        if frame is None or frame.empty or id_col not in frame or name_col not in frame:
            continue
        for pid, name in zip(frame[id_col], frame[name_col]):
            pid = _valid_profile_id(pid)
            if pid and isinstance(name, str) and name.strip():
                names_by_id.setdefault(pid, set()).add(name.strip())

    profile_rows = []
    for pid, names in sorted(names_by_id.items(), key=lambda item: int(item[0])):
        canonical = sorted(names, key=lambda value: (len(value), value.casefold()))[0]
        profile_rows.append({
            "internal_fighter_id": f"fightmatrix:{pid}",
            "fightmatrix_profile_id": pid,
            "canonical_display_name": canonical,
            "normalized_name": identity_name_key(canonical),
            "observed_aliases": "|".join(sorted(names)),
            "ufc_fighter": None,
            "match_confidence": 0.0,
            "match_reason": "no_ufc_match",
            "manual_override": False,
        })
    identity = pd.DataFrame(profile_rows)
    if identity.empty:
        identity = pd.DataFrame(columns=[
            "internal_fighter_id", "fightmatrix_profile_id", "canonical_display_name",
            "normalized_name", "observed_aliases", "ufc_fighter", "match_confidence",
            "match_reason", "manual_override",
        ])

    ufc_names = []
    if ufc_fighters is not None and not ufc_fighters.empty:
        column = "fighter" if "fighter" in ufc_fighters else "fighter_name"
        if column in ufc_fighters:
            ufc_names = sorted(set(ufc_fighters[column].dropna().astype(str)))
    ufc_by_key: dict[str, list[str]] = {}
    for name in ufc_names:
        ufc_by_key.setdefault(identity_name_key(name), []).append(name)
    fm_by_key = identity.groupby("normalized_name")["fightmatrix_profile_id"].apply(list).to_dict()

    for index, row in identity.iterrows():
        fm_ids = fm_by_key.get(row["normalized_name"], [])
        candidates = ufc_by_key.get(row["normalized_name"], [])
        if len(fm_ids) == 1 and len(candidates) == 1:
            identity.loc[index, ["ufc_fighter", "match_confidence", "match_reason"]] = [
                candidates[0], 0.95, "unique_normalized_name_only",
            ]

    overrides = pd.DataFrame()
    if Path(overrides_path).exists():
        overrides = pd.read_csv(overrides_path, dtype=str).dropna(how="all")
    if not overrides.empty:
        for row in overrides.itertuples(index=False):
            pid = _valid_profile_id(row.profile_id)
            match = identity.index[identity["fightmatrix_profile_id"].eq(pid)]
            if pid is None or len(match) != 1:
                continue
            canonical = row.canonical_name if isinstance(row.canonical_name, str) else row.ufc_fighter
            identity.loc[match, [
                "canonical_display_name", "ufc_fighter", "match_confidence",
                "match_reason", "manual_override",
            ]] = [canonical, row.ufc_fighter, 1.0, f"manual_override:{row.reason}", True]

    exception_rows = []
    for key, ids in sorted(fm_by_key.items()):
        if key and len(ids) > 1:
            exception_rows.append({
                "exception_type": "duplicate_normalized_name",
                "normalized_name": key,
                "fighter_name": None,
                "profile_ids": "|".join(sorted(ids, key=int)),
                "confidence": 0.0,
                "reason": "Multiple FightMatrix profile IDs share one normalized name; not merged.",
            })
    mapped_ufc = set(identity["ufc_fighter"].dropna().astype(str))
    for row in identity[identity["ufc_fighter"].notna() & identity["match_confidence"].lt(1.0)].itertuples(index=False):
        exception_rows.append({
            "exception_type": "suspicious_name_only_match",
            "normalized_name": row.normalized_name,
            "fighter_name": row.ufc_fighter,
            "profile_ids": row.fightmatrix_profile_id,
            "confidence": float(row.match_confidence),
            "reason": "Unique normalized-name match; profile ID was not independently cross-referenced.",
        })
    for name in ufc_names:
        if name not in mapped_ufc:
            key = identity_name_key(name)
            candidates = fm_by_key.get(key, [])
            exception_rows.append({
                "exception_type": "unmatched_ufc_fighter" if not candidates else "ambiguous_ufc_match",
                "normalized_name": key,
                "fighter_name": name,
                "profile_ids": "|".join(sorted(candidates, key=int)),
                "confidence": 0.0,
                "reason": "No unique profile-ID-backed match.",
            })
    discovered_ids = set()
    if bouts is not None and not bouts.empty and "opponent_profile_id" in bouts:
        discovered_ids = {_valid_profile_id(value) for value in bouts["opponent_profile_id"]}
        discovered_ids.discard(None)
    fetched_profile_ids = set(profiles["profile_id"].dropna().astype(str)) if profiles is not None and not profiles.empty else set()
    for pid in sorted(discovered_ids - fetched_profile_ids, key=int):
        names = bouts.loc[bouts["opponent_profile_id"].astype(str).eq(pid), "opponent"].dropna()
        exception_rows.append({
            "exception_type": "unresolved_fightmatrix_opponent",
            "normalized_name": identity_name_key(names.iloc[0]) if not names.empty else "",
            "fighter_name": names.iloc[0] if not names.empty else None,
            "profile_ids": pid,
            "confidence": 1.0,
            "reason": "Stable public profile ID discovered but profile has not been parsed.",
        })
    if not overrides.empty:
        for row in overrides.itertuples(index=False):
            exception_rows.append({
                "exception_type": "manual_override",
                "normalized_name": identity_name_key(row.ufc_fighter),
                "fighter_name": row.ufc_fighter,
                "profile_ids": row.profile_id,
                "confidence": 1.0,
                "reason": row.reason,
            })
    exceptions = pd.DataFrame(exception_rows, columns=[
        "exception_type", "normalized_name", "fighter_name", "profile_ids",
        "confidence", "reason",
    ])
    return identity.sort_values("fightmatrix_profile_id").reset_index(drop=True), exceptions
