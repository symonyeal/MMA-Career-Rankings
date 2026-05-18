"""Per-fight integrity annotations: PED, DQ wins, and missed-weight wins.

This module is the data half of the integrity sleeve. It reads from
authoritative sources already in the snapshot bundle:

* Greco ``details_text`` — explicit PED/anti-doping confirmation language
  (delegated to ``loaders.ped_flags.annotate_ped_flags``).
* Greco ``method_class == "DQ"`` plus the recorded winner.
* Greco ``details_text`` — explicit ``missed weight`` mention paired with
  the winner's name tokens.

The mdabbert weight-cross-check signal was evaluated and dropped:
``R_Weight_lbs`` / ``B_Weight_lbs`` in the dataset record each fighter's
listed fighting weight, not their weigh-in weight, so any divergence vs
``weight_class`` reflects catchweight / move-up information rather than a
missed-weight event. Greco DETAILS remains the authoritative source.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

import pandas as pd

from loaders.ped_flags import PED_DETAIL_RE, annotate_ped_flags
from project_helpers import normalize_name_key


_MISSED_WEIGHT_RE = re.compile(r"missed?\s+weight", re.IGNORECASE)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CURATED_PED_PATH = PROJECT_ROOT / "data" / "external" / "integrity" / "ped_bouts.csv"

_CURATED_PED_COLUMNS = (
    "event_date",
    "event_name",
    "fighter",
    "opponent",
    "sanctioning_body",
    "substance",
    "finding_type",
    "source_url",
    "notes",
)

_LOG = logging.getLogger(__name__)


INTEGRITY_COLUMNS = (
    "fight_url",
    "ped_confirmed",
    "ped_flagged_fighter",
    "ped_confirmation_source",
    "ped_confirmation_detail",
    "is_dq",
    "dq_winner",
    "missed_weight",
    "missed_weight_fighter",
    "missed_weight_source",
)


def _winner_named_in_text(winner: str | None, text: str | None) -> bool:
    if not isinstance(winner, str) or not isinstance(text, str):
        return False
    text_key = normalize_name_key(text, compact=True)
    winner_key = normalize_name_key(winner, compact=False)
    parts = [p for p in winner_key.split() if len(p) >= 3]
    if not parts:
        return False
    return any(normalize_name_key(p, compact=True) in text_key for p in parts)


def annotate_dq_wins(fights: pd.DataFrame) -> pd.DataFrame:
    """Add ``is_dq`` and ``dq_winner`` columns.

    Greco buckets the disqualification method as ``"DQ"`` in
    ``method_class``. The winner of a DQ bout — i.e., the fighter who was
    NOT disqualified — carries an integrity-sleeve damp on this result.
    """
    out = fights.copy()
    method = out.get("method_class")
    if method is None:
        out["is_dq"] = False
    else:
        out["is_dq"] = method.eq("DQ")
    out["dq_winner"] = None
    if out["is_dq"].any():
        out.loc[out["is_dq"], "dq_winner"] = out.loc[out["is_dq"], "winner"]
    return out


def annotate_missed_weight(fights: pd.DataFrame) -> pd.DataFrame:
    """Add ``missed_weight``, ``missed_weight_fighter``, ``missed_weight_source``.

    Sole signal today: Greco ``details_text`` contains the "missed weight"
    phrase and the winner's name (token-match) appears in the text. The
    source label is ``"greco"`` for any row flagged.
    """
    out = fights.copy()
    out["missed_weight"] = False
    out["missed_weight_fighter"] = None
    out["missed_weight_source"] = None

    text = out.get("details_text", pd.Series(index=out.index, dtype="object")).fillna("")
    has_phrase = text.astype("string").str.contains(_MISSED_WEIGHT_RE, na=False)
    candidate_mask = has_phrase & out.get("winner").notna()
    if candidate_mask.any():
        winners = out.loc[candidate_mask, "winner"]
        texts = out.loc[candidate_mask, "details_text"]
        winner_named = [
            _winner_named_in_text(w, t)
            for w, t in zip(winners, texts)
        ]
        idx = winners.index[pd.Series(winner_named).to_numpy()]
        out.loc[idx, "missed_weight"] = True
        out.loc[idx, "missed_weight_fighter"] = out.loc[idx, "winner"]
        out.loc[idx, "missed_weight_source"] = "greco"
    return out


def _load_curated_ped_bouts(
    curated_csv: Path | None = None,
) -> pd.DataFrame:
    """Load the project-level curated PED side-table.

    Schema documented in ``data/external/integrity/ped_bouts.csv``. Returns
    an empty frame with the curated columns if the file does not exist; this
    function never raises on missing file.
    """
    path = Path(curated_csv) if curated_csv else DEFAULT_CURATED_PED_PATH
    if not path.exists():
        return pd.DataFrame(columns=list(_CURATED_PED_COLUMNS))
    df = pd.read_csv(path, dtype=str).fillna("")
    missing = [c for c in _CURATED_PED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            f"curated PED bouts file {path} is missing required columns: {missing}"
        )
    df["event_date"] = pd.to_datetime(df["event_date"], errors="coerce")
    if df["event_date"].isna().any():
        bad = df.loc[df["event_date"].isna(), "event_name"].tolist()
        raise ValueError(
            f"curated PED bouts file {path} has unparseable event_date values for: {bad}"
        )
    return df


def _apply_curated_ped_flags(
    fights: pd.DataFrame,
    curated: pd.DataFrame,
) -> pd.DataFrame:
    """Overlay curated PED flags onto an already-annotated fights frame.

    Match key is ``(event_date, event_name)``; the curated row's ``fighter``
    must equal ``fighter_a`` or ``fighter_b``. Rows that do not resolve are
    logged at WARNING level and skipped — a curation error in the CSV
    should not crash the pipeline.

    Curated rows win over regex hits on the same ``(fight_url, fighter)``
    pair: the curated source/detail strings replace the Greco ones, since
    the curated row carries the citation. Regex hits on a different
    fighter at the same bout are not removed.
    """
    if curated is None or curated.empty:
        return fights
    out = fights.copy()
    fights_dates = pd.to_datetime(out["event_date"], errors="coerce")
    for _, row in curated.iterrows():
        target_date = pd.Timestamp(row["event_date"])
        target_event = row["event_name"]
        bout_mask = (fights_dates == target_date) & (out["event_name"] == target_event)
        if not bout_mask.any():
            _LOG.warning(
                "curated PED row does not resolve to any Greco bout: %s / %s / %s",
                row["event_date"], row["event_name"], row["fighter"],
            )
            continue
        fighter_mask = bout_mask & (
            (out["fighter_a"] == row["fighter"]) | (out["fighter_b"] == row["fighter"])
        )
        if not fighter_mask.any():
            _LOG.warning(
                "curated PED row names a fighter not in the bout: %s / %s / %s",
                row["event_date"], row["event_name"], row["fighter"],
            )
            continue
        idx = out.index[fighter_mask]
        out.loc[idx, "ped_confirmed"] = True
        out.loc[idx, "ped_flagged_fighter"] = row["fighter"]
        out.loc[idx, "ped_confirmation_source"] = f"curated:{row['sanctioning_body']}"
        out.loc[idx, "ped_confirmation_detail"] = (
            f"{row['substance']}; {row['finding_type']}; {row['source_url']}"
        )
    return out


def build_integrity_flags(
    fights: pd.DataFrame,
    *,
    mdabbert_csv: Path | None = None,
    curated_ped_csv: Path | None = None,
) -> pd.DataFrame:
    """Produce the long-form per-fight integrity flag table.

    Returns the per-fight rows with the union of PED + DQ + missed-weight
    columns. Callers merge by ``fight_url``. The ``mdabbert_csv`` argument
    is accepted for backwards compatibility but currently unused; see the
    module docstring.

    ``curated_ped_csv`` overrides the default project-level curated PED
    side-table path; pass ``None`` to use the default. Curated flags are
    unioned with the regex-derived flags, with curated taking precedence
    on overlapping ``(fight_url, fighter)`` pairs.
    """
    _ = mdabbert_csv  # reserved
    if fights is None or fights.empty:
        return pd.DataFrame(columns=INTEGRITY_COLUMNS)

    out = annotate_ped_flags(fights)
    curated = _load_curated_ped_bouts(curated_ped_csv)
    out = _apply_curated_ped_flags(out, curated)
    out = annotate_dq_wins(out)
    out = annotate_missed_weight(out)
    return out[list(INTEGRITY_COLUMNS)].copy()


def confirmed_counts(flags: pd.DataFrame) -> pd.DataFrame:
    """Per-fighter counts of PED-confirmed, DQ wins, and missed-weight wins."""
    rows = []
    if "ped_flagged_fighter" in flags.columns:
        ped = (
            flags[flags["ped_confirmed"].fillna(False) & flags["ped_flagged_fighter"].notna()]
            .groupby("ped_flagged_fighter").size()
            .rename("ped_confirmed_fights").reset_index()
            .rename(columns={"ped_flagged_fighter": "fighter"})
        )
        rows.append(ped)
    if "dq_winner" in flags.columns:
        dq = (
            flags[flags["is_dq"].fillna(False) & flags["dq_winner"].notna()]
            .groupby("dq_winner").size()
            .rename("dq_wins").reset_index()
            .rename(columns={"dq_winner": "fighter"})
        )
        rows.append(dq)
    if "missed_weight_fighter" in flags.columns:
        mw = (
            flags[flags["missed_weight"].fillna(False) & flags["missed_weight_fighter"].notna()]
            .groupby("missed_weight_fighter").size()
            .rename("missed_weight_wins").reset_index()
            .rename(columns={"missed_weight_fighter": "fighter"})
        )
        rows.append(mw)
    if not rows:
        return pd.DataFrame(columns=["fighter", "ped_confirmed_fights", "dq_wins", "missed_weight_wins"])
    out = rows[0]
    for nxt in rows[1:]:
        out = out.merge(nxt, on="fighter", how="outer")
    for c in ("ped_confirmed_fights", "dq_wins", "missed_weight_wins"):
        if c in out.columns:
            out[c] = out[c].fillna(0).astype(int)
    return out
