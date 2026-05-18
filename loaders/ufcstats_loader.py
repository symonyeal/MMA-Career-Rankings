"""Build the canonical snapshot from the local Greco1899 ufcstats CSVs.

Reads the 6 Greco CSVs, applies the
UFC 28+ era filter, splits excluded bouts (NC / Overturned / Could Not Continue
/ pre-unified-rules) into a sidecar CSV, and writes the rest as a parquet
bundle in `data/snapshots/<date>/`.

Run from the project root:
    python -m loaders.ufcstats_loader --snapshot-date 2026-05-13
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import date
from pathlib import Path

import pandas as pd

try:
    from .ped_flags import annotate_ped_flags
except ImportError:  # pragma: no cover - direct script execution
    from ped_flags import annotate_ped_flags


# ---------------------------------------------------------------------------
# Constants

GRECO_FILES = {
    "events":   "ufc_event_details.csv",
    "details":  "ufc_fight_details.csv",
    "results":  "ufc_fight_results.csv",
    "stats":    "ufc_fight_stats.csv",
    "fighters": "ufc_fighter_details.csv",
    "tott":     "ufc_fighter_tott.csv",
}


def has_greco_files(path: Path) -> bool:
    return all((path / filename).exists() for filename in GRECO_FILES.values())


def default_greco_dir(project_root: Path, snapshot_date: str) -> Path:
    candidates = [
        project_root / "data" / "raw" / snapshot_date,
        project_root / "scrape_ufc_stats-main" / "scrape_ufc_stats-main",
        project_root.parent / "scrape_ufc_stats-main" / "scrape_ufc_stats-main",
    ]
    for candidate in candidates:
        if has_greco_files(candidate):
            return candidate
    return candidates[0]

# Unified-rules cutoff. UFC 28 (Tito Ortiz vs Yuki Kondo) was the first event
# under unified rules. Everything strictly before is dropped.
UFC_28_DATE = pd.Timestamp("2000-11-17")

# Glicko-2 winner score for the mu_method (method-bonus) rating only.
# mu_canonical ignores this and always uses {0, 0.5, 1}.
#
# 2026-05-15 widening: decisions now spread 0.85 - 0.97 so the engine can tell
# a split from a unanimous, and a unanimous from a one-sided five-round win.
# Finish stays at 1.00 but Unanimous = 0.95 keeps opponent quality (not the
# finish bonus) the dominant per-fight signal. The 0.97 dominant-decision
# tier is decided in performance_adjustment.decision_quality_score from the
# judges' cards; this dict provides the base method tier.
#
# Tiers:
#   KO/TKO, Submission   1.00  finish
#   Decision - Unanimous 0.95  unanimous (the 0.97 dominant-5rd lift is
#                              applied downstream when every judge cards
#                              the full sweep over 5 rounds)
#   Decision - Majority  0.90  non-unanimous: one judge dissents
#   Decision - Split     0.90  non-unanimous: one judge scored the other way
#   DQ                   0.85  win by disqualification, before integrity
from ratings.constants import (
    METHOD_SCORE_DQ,
    METHOD_SCORE_FINISH,
    METHOD_SCORE_NON_UNANIMOUS_DECISION,
    METHOD_SCORE_UNANIMOUS,
)

METHOD_SCORES = {
    "KO/TKO":               METHOD_SCORE_FINISH,
    "Submission":           METHOD_SCORE_FINISH,
    "Decision - Unanimous": METHOD_SCORE_UNANIMOUS,
    "Decision - Majority":  METHOD_SCORE_NON_UNANIMOUS_DECISION,
    "Decision - Split":     METHOD_SCORE_NON_UNANIMOUS_DECISION,
    "DQ":                   METHOD_SCORE_DQ,
}


# ---------------------------------------------------------------------------
# Cell-level parsers

def _strip_object_cols(df: pd.DataFrame) -> pd.DataFrame:
    # pandas 3.x exposes a `"string"` dtype alongside legacy `"object"`; include both
    # so the strip works regardless of which one read_csv picked.
    for c in df.select_dtypes(include=["object", "string"]).columns:
        df[c] = df[c].apply(lambda x: x.strip() if isinstance(x, str) else x)
    return df


def parse_bout(s):
    """'A vs. B' -> ('A', 'B')."""
    if not isinstance(s, str):
        return (None, None)
    parts = s.split(" vs. ")
    if len(parts) != 2:
        return (None, None)
    return parts[0].strip(), parts[1].strip()


def parse_outcome(s):
    """'W/L' -> ('W','L'). Also handles L/W, D/D, NC/NC."""
    if not isinstance(s, str):
        return (None, None)
    parts = s.split("/")
    if len(parts) != 2:
        return (None, None)
    return parts[0].strip().upper(), parts[1].strip().upper()


def parse_method(s):
    """Bucket Greco's METHOD string. v1: KO and TKO lumped; KO-by-sub lumped
    with regular Submission (Greco doesn't tag these separately)."""
    if not isinstance(s, str):
        return None
    s = s.strip()
    if s.startswith("KO/TKO") or s.startswith("TKO"):
        return "KO/TKO"
    if s.startswith("Submission") or s == "SUB":
        return "Submission"
    if s.startswith("Decision - Unanimous"):
        return "Decision - Unanimous"
    if s.startswith("Decision - Majority"):
        return "Decision - Majority"
    if s.startswith("Decision - Split"):
        return "Decision - Split"
    if s == "DQ":
        return "DQ"
    if s.startswith("Could Not Continue") or s == "CNC":
        return "Could Not Continue"
    if s == "Overturned":
        return "Overturned"
    if s == "Other":
        return "Other"
    return s  # unknown -> keep raw


def parse_x_of_y(s):
    """'5 of 11' -> (5, 11). '--'/empty/None -> (None, None)."""
    if not isinstance(s, str):
        return (None, None)
    m = re.match(r"^\s*(\d+)\s*of\s*(\d+)\s*$", s)
    if not m:
        return (None, None)
    return int(m.group(1)), int(m.group(2))


def parse_mmss_to_seconds(s):
    """'4:47' -> 287. Invalid -> None."""
    if not isinstance(s, str):
        return None
    m = re.match(r"^\s*(\d+):(\d+)\s*$", s)
    if not m:
        return None
    return int(m.group(1)) * 60 + int(m.group(2))


def parse_pct(s):
    if not isinstance(s, str):
        return None
    m = re.match(r"^\s*(\d+)\s*%\s*$", s)
    if not m:
        return None
    return int(m.group(1))


def parse_height_to_inches(s):
    """'5\\' 11\"' -> 71."""
    if not isinstance(s, str) or s.strip() in ("", "--"):
        return None
    m = re.match(r"^\s*(\d+)'\s*(\d+)\s*\"\s*$", s)
    if not m:
        return None
    return int(m.group(1)) * 12 + int(m.group(2))


def parse_weight_to_lb(s):
    if not isinstance(s, str) or s.strip() in ("", "--"):
        return None
    m = re.match(r"^\s*(\d+)\s*lbs?\.?\s*$", s)
    if not m:
        return None
    return int(m.group(1))


def parse_reach_to_inches(s):
    if not isinstance(s, str) or s.strip() in ("", "--"):
        return None
    m = re.match(r'^\s*(\d+(?:\.\d+)?)\s*"\s*$', s)
    if not m:
        return None
    return float(m.group(1))


def parse_dob(s):
    if not isinstance(s, str) or s.strip() in ("", "--"):
        return pd.NaT
    return pd.to_datetime(s, format="%b %d, %Y", errors="coerce")


# ---------------------------------------------------------------------------
# Table builders

def load_raw(greco_dir: Path) -> dict[str, pd.DataFrame]:
    raw = {}
    for key, fname in GRECO_FILES.items():
        path = greco_dir / fname
        if not path.exists():
            raise FileNotFoundError(f"missing Greco CSV: {path}")
        df = pd.read_csv(path)
        raw[key] = _strip_object_cols(df)
    return raw


def parse_events(events: pd.DataFrame) -> pd.DataFrame:
    out = events.copy()
    out["event_date"] = pd.to_datetime(out["DATE"], format="%B %d, %Y", errors="coerce")
    out = out.rename(columns={"EVENT": "event_name", "URL": "event_url", "LOCATION": "event_location"})
    return out[["event_name", "event_url", "event_date", "event_location"]]


def build_canonical_fights(results: pd.DataFrame, events_parsed: pd.DataFrame) -> pd.DataFrame:
    f = results.copy()
    f["event_name"] = f["EVENT"]
    f = f.merge(
        events_parsed[["event_name", "event_date", "event_url", "event_location"]],
        on="event_name", how="left",
    )

    bouts = f["BOUT"].apply(lambda s: pd.Series(parse_bout(s), index=["fighter_a", "fighter_b"]))
    f = pd.concat([f, bouts], axis=1)

    outs = f["OUTCOME"].apply(lambda s: pd.Series(parse_outcome(s), index=["fighter_a_outcome", "fighter_b_outcome"]))
    f = pd.concat([f, outs], axis=1)

    f["method_class"] = f["METHOD"].apply(parse_method)
    f["method_score_winner"] = f["method_class"].map(METHOD_SCORES)
    f["is_title_fight"] = f["WEIGHTCLASS"].astype("string").str.contains("Title", case=False, na=False)

    def winner_of(row):
        a, b = row["fighter_a_outcome"], row["fighter_b_outcome"]
        if a == "W" and b == "L": return row["fighter_a"]
        if a == "L" and b == "W": return row["fighter_b"]
        return None

    def loser_of(row):
        a, b = row["fighter_a_outcome"], row["fighter_b_outcome"]
        if a == "W" and b == "L": return row["fighter_b"]
        if a == "L" and b == "W": return row["fighter_a"]
        return None

    f["winner"] = f.apply(winner_of, axis=1)
    f["loser"] = f.apply(loser_of, axis=1)
    f["is_draw"] = (f["fighter_a_outcome"] == "D") & (f["fighter_b_outcome"] == "D")
    f["is_nc"] = (f["fighter_a_outcome"] == "NC") | (f["fighter_b_outcome"] == "NC")

    f["is_excluded"] = (
        f["is_nc"]
        | (f["method_class"] == "Overturned")
        | (f["method_class"] == "Could Not Continue")
    )

    def exclusion_reason(row):
        if row["method_class"] == "Overturned": return "method_overturned"
        if row["method_class"] == "Could Not Continue": return "could_not_continue"
        if row["is_nc"]: return "no_contest"
        return None

    f["exclusion_reason"] = f.apply(exclusion_reason, axis=1)

    f["end_round"] = pd.to_numeric(f["ROUND"], errors="coerce").astype("Int64")
    f["end_time_seconds"] = f["TIME"].apply(parse_mmss_to_seconds)

    f = f.rename(columns={
        "URL": "fight_url",
        "BOUT": "bout_string",
        "WEIGHTCLASS": "weight_class",
        "METHOD": "method_raw",
        "TIME FORMAT": "time_format",
        "REFEREE": "referee",
        "DETAILS": "details_text",
    })

    keep = [
        "fight_url", "event_url", "event_name", "event_date", "event_location",
        "bout_string", "fighter_a", "fighter_b",
        "fighter_a_outcome", "fighter_b_outcome",
        "winner", "loser", "is_draw", "is_nc", "is_excluded", "exclusion_reason",
        "weight_class", "is_title_fight",
        "method_raw", "method_class", "method_score_winner",
        "end_round", "end_time_seconds", "time_format", "referee", "details_text",
    ]
    return f[keep].copy()


_PAIR_COLS = ["SIG.STR.", "TOTAL STR.", "TD", "HEAD", "BODY", "LEG", "DISTANCE", "CLINCH", "GROUND"]


def _pair_col_names(raw: str) -> tuple[str, str]:
    base = raw.lower().rstrip(".").replace(".", "_").replace(" ", "_")
    return f"{base}_landed", f"{base}_attempted"


def build_canonical_rounds(stats: pd.DataFrame, fights: pd.DataFrame) -> pd.DataFrame:
    s = stats.copy()
    s["event_name"] = s["EVENT"]
    s["bout_string"] = s["BOUT"]
    s = s.merge(
        fights[["event_name", "bout_string", "fight_url", "event_date"]],
        on=["event_name", "bout_string"], how="left",
    )

    s["round_num"] = s["ROUND"].astype("string").str.extract(r"Round\s*(\d+)").astype("Int64")

    for col in _PAIR_COLS:
        landed_att = s[col].apply(lambda v: pd.Series(parse_x_of_y(v), index=_pair_col_names(col)))
        s = pd.concat([s, landed_att], axis=1)

    s["kd"] = pd.to_numeric(s["KD"], errors="coerce").astype("Int64")
    s["sub_att"] = pd.to_numeric(s["SUB.ATT"], errors="coerce").astype("Int64")
    s["rev"] = pd.to_numeric(s["REV."], errors="coerce").astype("Int64")
    s["sig_str_pct"] = s["SIG.STR. %"].apply(parse_pct)
    s["td_pct"] = s["TD %"].apply(parse_pct)
    s["ctrl_seconds"] = s["CTRL"].apply(parse_mmss_to_seconds)
    s["fighter"] = s["FIGHTER"]

    keep = [
        "fight_url", "event_name", "event_date", "bout_string", "round_num", "fighter",
        "kd",
        "sig_str_landed", "sig_str_attempted", "sig_str_pct",
        "total_str_landed", "total_str_attempted",
        "td_landed", "td_attempted", "td_pct",
        "sub_att", "rev", "ctrl_seconds",
        "head_landed", "head_attempted",
        "body_landed", "body_attempted",
        "leg_landed", "leg_attempted",
        "distance_landed", "distance_attempted",
        "clinch_landed", "clinch_attempted",
        "ground_landed", "ground_attempted",
    ]
    return s[keep].copy()


def build_canonical_fighters(tott: pd.DataFrame, details: pd.DataFrame) -> pd.DataFrame:
    t = tott.copy()
    t["fighter"] = t["FIGHTER"]
    t["fighter_url"] = t["URL"]
    t["height_inches"] = t["HEIGHT"].apply(parse_height_to_inches)
    t["weight_lb"] = t["WEIGHT"].apply(parse_weight_to_lb)
    t["reach_inches"] = t["REACH"].apply(parse_reach_to_inches)
    t["stance"] = t["STANCE"].replace({"": None, "--": None})
    t["dob"] = t["DOB"].apply(parse_dob)

    d = details.copy()
    d["fighter_url"] = d["URL"]
    d["nickname"] = d["NICKNAME"].replace({"": None})

    out = t.merge(d[["fighter_url", "FIRST", "LAST", "nickname"]], on="fighter_url", how="left")
    out = out.rename(columns={"FIRST": "first_name", "LAST": "last_name"})
    keep = [
        "fighter", "fighter_url", "first_name", "last_name", "nickname",
        "height_inches", "weight_lb", "reach_inches", "stance", "dob",
    ]
    return out[keep]


# ---------------------------------------------------------------------------
# Sidecar schemas (per parquet)

SCHEMAS = {
    "canonical_fights": {
        "primary_key": "fight_url",
        "source": "Greco/ufc_fight_results.csv + ufc_event_details.csv",
        "row_grain": "one row per UFC bout (post-2000-11-17, non-excluded)",
        "columns": {
            "fight_url": "Greco ufc_fight_results.URL — canonical fight PK",
            "event_url": "Greco ufc_event_details.URL",
            "event_name": "Greco EVENT",
            "event_date": "Greco DATE parsed to datetime",
            "event_location": "Greco LOCATION",
            "bout_string": "Greco BOUT raw 'A vs. B'",
            "fighter_a": "first half of BOUT split",
            "fighter_b": "second half of BOUT split",
            "fighter_a_outcome": "W | L | D | NC",
            "fighter_b_outcome": "W | L | D | NC",
            "winner": "derived; null for draws and NCs",
            "loser": "derived; null for draws and NCs",
            "is_draw": "bool",
            "is_nc": "bool",
            "is_excluded": "true for NC / Overturned / Could Not Continue (these rows live in _excluded_bouts.csv only)",
            "exclusion_reason": "no_contest | method_overturned | could_not_continue | pre_unified_rules | null",
            "weight_class": "Greco WEIGHTCLASS",
            "is_title_fight": "derived; WEIGHTCLASS contains 'Title'",
            "method_raw": "Greco METHOD verbatim",
            "method_class": "bucketed: KO/TKO | Submission | Decision - Unanimous/Majority/Split | DQ | Could Not Continue | Overturned | Other",
            "method_score_winner": "winner score for μ_method rating; null for μ_canonical inputs",
            "end_round": "int",
            "end_time_seconds": "TIME parsed mm:ss",
            "time_format": "Greco TIME FORMAT",
            "referee": "Greco REFEREE",
            "details_text": "Greco DETAILS verbatim (judge scorecards live here)",
            "ped_confirmed": "derived from details_text; true when Greco confirms a failed drug test or anti-doping violation tied to the bout",
            "ped_flagged_fighter": "fighter named by the PED confirmation text, when inferable",
            "ped_confirmation_source": "source field used for the PED flag",
            "ped_confirmation_detail": "verbatim details_text used for PED audit",
        },
    },
    "canonical_rounds": {
        "primary_key": ["fight_url", "round_num", "fighter"],
        "source": "Greco/ufc_fight_stats.csv",
        "row_grain": "one row per (fight, round, fighter)",
        "columns": {
            "fight_url": "FK to canonical_fights.fight_url",
            "round_num": "int extracted from 'Round N'",
            "fighter": "fighter name (matches canonical_fighters.fighter)",
            "kd": "knockdowns landed",
            "sig_str_landed/_attempted/_pct": "Greco SIG.STR. parsed",
            "total_str_landed/_attempted": "Greco TOTAL STR. parsed",
            "td_landed/_attempted/_pct": "Greco TD parsed",
            "sub_att": "submission attempts",
            "rev": "reversals",
            "ctrl_seconds": "Greco CTRL mm:ss to seconds",
            "head_/body_/leg_/distance_/clinch_/ground_*": "by-target sig-strike pairs",
        },
    },
    "canonical_fighters": {
        "primary_key": "fighter_url",
        "source": "Greco/ufc_fighter_tott.csv + ufc_fighter_details.csv",
        "row_grain": "one row per fighter ever in the Greco universe (not all are UFC-active)",
        "columns": {
            "fighter": "display name (matches canonical_rounds.fighter)",
            "fighter_url": "Greco fighter PK",
            "first_name": "Greco FIRST",
            "last_name": "Greco LAST",
            "nickname": "Greco NICKNAME (empty -> null)",
            "height_inches": "parsed from \"5' 11\\\"\"",
            "weight_lb": "parsed from '155 lbs.'",
            "reach_inches": "parsed from '70\"' (float)",
            "stance": "Greco STANCE (Orthodox/Southpaw/Switch/Open Stance/null)",
            "dob": "Greco DOB parsed",
        },
    },
    "canonical_events": {
        "primary_key": "event_url",
        "source": "Greco/ufc_event_details.csv",
        "row_grain": "one row per UFC event from UFC 28 onward",
        "columns": {
            "event_name": "Greco EVENT",
            "event_url": "Greco URL",
            "event_date": "Greco DATE parsed",
            "event_location": "Greco LOCATION",
        },
    },
}


def write_schema_sidecar(snapshot_dir: Path, name: str) -> None:
    payload = SCHEMAS[name]
    (snapshot_dir / f"{name}.schema.json").write_text(
        json.dumps(payload, indent=2, default=str), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Orchestration

def build_snapshot(greco_dir: Path, snapshot_dir: Path) -> dict[str, int]:
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    raw = load_raw(greco_dir)
    raw_counts = {k: len(v) for k, v in raw.items()}

    events_parsed = parse_events(raw["events"])
    fights_all = annotate_ped_flags(build_canonical_fights(raw["results"], events_parsed))

    # Era filter: drop UFC 1–27.
    pre_unified = fights_all[fights_all["event_date"] < UFC_28_DATE].copy()
    pre_unified["is_excluded"] = True
    pre_unified["exclusion_reason"] = "pre_unified_rules"
    fights_unified = fights_all[fights_all["event_date"] >= UFC_28_DATE].copy()

    excluded = pd.concat(
        [pre_unified, fights_unified[fights_unified["is_excluded"]]],
        ignore_index=True,
    )
    canonical_fights = fights_unified[~fights_unified["is_excluded"]].copy()

    rounds_all = build_canonical_rounds(raw["stats"], fights_all)
    canonical_rounds = rounds_all[rounds_all["fight_url"].isin(canonical_fights["fight_url"])].copy()

    canonical_fighters = build_canonical_fighters(raw["tott"], raw["fighters"])
    canonical_events = events_parsed[events_parsed["event_date"] >= UFC_28_DATE].copy()

    # Write parquet bundle + sidecar JSON schemas.
    canonical_fights.to_parquet(snapshot_dir / "canonical_fights.parquet", index=False)
    canonical_rounds.to_parquet(snapshot_dir / "canonical_rounds.parquet", index=False)
    canonical_fighters.to_parquet(snapshot_dir / "canonical_fighters.parquet", index=False)
    canonical_events.to_parquet(snapshot_dir / "canonical_events.parquet", index=False)
    excluded.to_csv(snapshot_dir / "_excluded_bouts.csv", index=False)
    ped_confirmed = pd.concat(
        [
            canonical_fights[canonical_fights["ped_confirmed"]],
            excluded[excluded["ped_confirmed"]],
        ],
        ignore_index=True,
    )
    ped_confirmed.to_csv(snapshot_dir / "ped_confirmed_bouts.csv", index=False)
    for name in SCHEMAS:
        write_schema_sidecar(snapshot_dir, name)

    return {
        "raw_events":      raw_counts["events"],
        "raw_results":     raw_counts["results"],
        "raw_stats":       raw_counts["stats"],
        "raw_tott":        raw_counts["tott"],
        "events_kept":     len(canonical_events),
        "fighters_seen":   len(canonical_fighters),
        "fights_kept":     len(canonical_fights),
        "rounds_kept":     len(canonical_rounds),
        "excluded_bouts":  len(excluded),
        "excluded_pre_unified":  int((excluded["exclusion_reason"] == "pre_unified_rules").sum()),
        "excluded_nc":           int((excluded["exclusion_reason"] == "no_contest").sum()),
        "excluded_overturned":   int((excluded["exclusion_reason"] == "method_overturned").sum()),
        "excluded_cnc":          int((excluded["exclusion_reason"] == "could_not_continue").sum()),
    }, canonical_fights


def main() -> None:
    parser = argparse.ArgumentParser(description="Build canonical UFC snapshot from local Greco CSVs.")
    parser.add_argument("--greco-dir", default=None,
                        help="Path to a directory containing the six Greco CSVs. "
                             "Defaults to data/raw/<snapshot-date> when present.")
    parser.add_argument("--snapshot-date", default=str(date.today()),
                        help="YYYY-MM-DD label for the snapshot folder.")
    parser.add_argument("--project-root", default=None,
                        help="Override project root (default: parent of this file's directory).")
    args = parser.parse_args()

    here = Path(__file__).resolve().parent
    project_root = Path(args.project_root).resolve() if args.project_root else here.parent
    greco_dir = (
        Path(args.greco_dir).resolve() if args.greco_dir
        else default_greco_dir(project_root, args.snapshot_date).resolve()
    )
    snapshot_dir = project_root / "data" / "snapshots" / args.snapshot_date

    print(f"[load] greco_dir   = {greco_dir}")
    print(f"[load] snapshot_dir= {snapshot_dir}")

    counts, canonical_fights = build_snapshot(greco_dir, snapshot_dir)

    print()
    print("=== RAW (pre-filter) ===")
    print(f"  events  : {counts['raw_events']:>6}")
    print(f"  results : {counts['raw_results']:>6}")
    print(f"  stats   : {counts['raw_stats']:>6} (per-round per-fighter rows)")
    print(f"  tott    : {counts['raw_tott']:>6}")
    print()
    print("=== SNAPSHOT (post UFC-28 filter & exclusions) ===")
    print(f"  events kept   : {counts['events_kept']:>6}")
    print(f"  fighters seen : {counts['fighters_seen']:>6}")
    print(f"  fights kept   : {counts['fights_kept']:>6}")
    print(f"  fight-rounds  : {counts['rounds_kept']:>6}")
    print(f"  excluded bouts: {counts['excluded_bouts']:>6}"
          f"  (pre-unified={counts['excluded_pre_unified']},"
          f" NC={counts['excluded_nc']},"
          f" overturned={counts['excluded_overturned']},"
          f" CNC={counts['excluded_cnc']})")
    print()
    sample_cols = [
        "event_date", "event_name", "fighter_a", "fighter_b", "winner",
        "weight_class", "method_class", "end_round", "end_time_seconds", "is_title_fight",
    ]
    print("--- canonical_fights sample (5 most recent) ---")
    sample = canonical_fights.sort_values("event_date", ascending=False).head(5)[sample_cols]
    with pd.option_context("display.max_colwidth", 40, "display.width", 200):
        print(sample.to_string(index=False))


if __name__ == "__main__":
    main()
