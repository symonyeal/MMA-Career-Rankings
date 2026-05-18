"""PED / anti-doping annotations derived from auditable fight text.

The v1 source is intentionally conservative: only Greco rows whose official
details text explicitly says a fight was overturned for a failed drug test or
similar in-competition anti-doping violation are flagged. Broader athlete
sanctions that are not tied to a specific bout are not inferred here.
"""
from __future__ import annotations

import re

import pandas as pd


PED_DETAIL_RE = re.compile(
    r"(?:failed\s+drug\s+test|illegal\s+inhaler\s+use)",
    flags=re.IGNORECASE,
)


def _name_tokens(name: str | None) -> list[str]:
    if not isinstance(name, str):
        return []
    return [
        token.casefold()
        for token in re.findall(r"[A-Za-z']+", name)
        if len(token) > 1
    ]


def _infer_flagged_fighter(row: pd.Series) -> str | None:
    text = str(row.get("details_text") or "")
    if not PED_DETAIL_RE.search(text):
        return None

    lowered = text.casefold()
    candidates = [row.get("fighter_a"), row.get("fighter_b")]
    scored: list[tuple[int, str]] = []
    for fighter in candidates:
        if not isinstance(fighter, str):
            continue
        tokens = _name_tokens(fighter)
        if not tokens:
            continue
        score = sum(1 for token in tokens if token in lowered)
        # Last names are usually what Greco appends after "by".
        if tokens[-1] in lowered:
            score += 2
        if score:
            scored.append((score, fighter))

    if not scored:
        return None
    scored.sort(reverse=True)
    if len(scored) > 1 and scored[0][0] == scored[1][0]:
        return None
    return scored[0][1]


def annotate_ped_flags(fights: pd.DataFrame) -> pd.DataFrame:
    """Add per-fight PED confirmation columns.

    Columns added:
    - ped_confirmed: details text confirms a fight-specific anti-doping issue.
    - ped_flagged_fighter: fighter named by the details text when inferable.
    - ped_confirmation_source: source field used for the flag.
    - ped_confirmation_detail: original details text for audit.
    """
    out = fights.copy()
    details = out.get("details_text", pd.Series(index=out.index, dtype="object")).fillna("")
    out["ped_confirmed"] = details.astype("string").str.contains(PED_DETAIL_RE, na=False)
    out["ped_flagged_fighter"] = out.apply(_infer_flagged_fighter, axis=1)
    out.loc[~out["ped_confirmed"], "ped_flagged_fighter"] = None
    out["ped_confirmation_source"] = None
    out.loc[out["ped_confirmed"], "ped_confirmation_source"] = "Greco details_text"
    out["ped_confirmation_detail"] = None
    out.loc[out["ped_confirmed"], "ped_confirmation_detail"] = out.loc[out["ped_confirmed"], "details_text"]
    return out
