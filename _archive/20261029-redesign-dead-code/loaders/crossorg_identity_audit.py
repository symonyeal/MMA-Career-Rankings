"""Find cross-org fighters who are the same person as a rated UFC fighter.

Name matching across sources is the standing trap in this project: hyphens once
double-counted all thirty-five of Georges St-Pierre's UFC bouts, and cross-org
ingestion multiplies the blast radius, because a missed match does not merely
mis-count a bout -- it splits one career into two fighters and severs the bridge
that anchors a whole promotion to the main scale.

Sherdog indexes by legal name. The canonical UFC set does not always agree:
Sherdog's "Ronaldo Souza" is the UFC set's "Jacare Souza", and an exact
normalized-key join silently drops him along with every bridge he carries.

This module proposes candidates; it does not apply them. Each row is a pair the
key join missed and a reason it is suspicious, for a human to accept or reject.
Auto-applying fuzzy name matches is how two different fighters become one.
"""
from __future__ import annotations

import re
import unicodedata
from collections import defaultdict

import pandas as pd

from project_helpers import normalize_name_key

_NICKNAME_RE = re.compile(r"[\"'‘’“”].*?[\"'‘’“”]")


def _tokens(name: str) -> list[str]:
    text = unicodedata.normalize("NFKD", str(name))
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = _NICKNAME_RE.sub(" ", text).lower()
    text = re.sub(r"[^a-z ]", " ", text)
    return [t for t in text.split() if len(t) > 1]


def _surname_index(names: list[str]) -> dict[str, list[str]]:
    index: dict[str, list[str]] = defaultdict(list)
    for name in names:
        toks = _tokens(name)
        if toks:
            index[toks[-1]].append(name)
    return dict(index)


def audit(
    crossorg_names: list[str],
    core_names: list[str],
    *,
    crossorg_weight: dict[str, int] | None = None,
) -> pd.DataFrame:
    """Candidate identities the exact key join missed.

    ``crossorg_weight`` (bouts per cross-org fighter) orders the output, because
    a missed match on a fighter with twenty bouts costs far more than one with a
    single appearance.
    """
    core_keys = {normalize_name_key(n, compact=True): n for n in core_names}
    by_surname = _surname_index(core_names)
    weight = crossorg_weight or {}

    rows = []
    for name in crossorg_names:
        if normalize_name_key(name, compact=True) in core_keys:
            continue
        toks = _tokens(name)
        if not toks:
            continue
        for candidate in by_surname.get(toks[-1], []):
            ctoks = _tokens(candidate)
            shared = set(toks) & set(ctoks)
            if len(shared) < 1:
                continue
            first_initials = toks[0][:1] == ctoks[0][:1]
            reason = (
                "surname + given name" if len(shared) >= 2
                else "surname + shared initial" if first_initials
                else "surname only"
            )
            rows.append({
                "crossorg_name": name,
                "core_candidate": candidate,
                "shared_tokens": len(shared),
                "same_first_initial": first_initials,
                "reason": reason,
                "crossorg_bouts": int(weight.get(name, 0)),
            })

    out = pd.DataFrame(rows)
    if out.empty:
        return out
    strength = {"surname + given name": 0, "surname + shared initial": 1, "surname only": 2}
    out["_rank"] = out["reason"].map(strength)
    return (out.sort_values(["_rank", "crossorg_bouts"], ascending=[True, False])
            .drop(columns="_rank").reset_index(drop=True))
