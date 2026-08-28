"""Stage the six-promotion Sherdog cards as a rateable snapshot scope.

``build_sherdog_majors.py`` crawls PRIDE, WEC, Strikeforce, Affliction,
Bellator and RIZIN by *event* and writes ``majors_bouts.parquet`` under
``data/external/sherdog/``. The completed whole-career extension is preserved
as ``crossorg_bouts.parquet`` in the same directory. This module is the live
path that resolves those rows and stages ``majors_fights.parquet`` for the
named rating scope; the original era-skew investigation is historical.

The two are not interchangeable and must never be merged silently. Measured on
the same functional and the same 0.9 bar, snapshot 2026-08-13:

===================================  ==========  ============  =============
scope                                top-100     median debut  pre-2010
                                     active '24                debuts in 100
===================================  ==========  ============  =============
UFC only                                     70          2015             18
+ majors (this module)                       57          2009             57
+ FightMatrix depth-one                      85          2012             28
===================================  ==========  ============  =============

The majors corpus back-fills the early era; the FightMatrix crawl is seeded from
current rankings and back-fills the modern regional circuit. Both are real
scopes; they answer different questions and are named separately for that
reason.

They are also justified on different grounds. On held-out UFC bouts with both
fighters covered, `fightmatrix` is worth -0.01896 [-0.02376, -0.01397] log-loss
and `majors` is **unresolved** at +0.00391 [-0.00484, +0.01245] on n=435. That
is structural rather than a defect: this corpus back-fills careers that are
largely over before the 2010+ evaluation window opens. **It is justified on
completeness, explicitly, and never on prediction.**

One caution that travels with any board built from it: the 0.9 year bar was
calibrated on the UFC-only population (~60 fighter-years of ~578). Here the same
quantile admits 197-419. See the note above ``DEFAULT_CAREER_REFERENCE`` in
``ratings/symon_score.py``.

No organisation weight is applied, here or anywhere. Relative promotion
strength is an output of the joint fit, read off the fighters who crossed
between promotions; a weight would assert the answer the fit exists to
estimate.
"""
from __future__ import annotations

import gzip
import re
from pathlib import Path

import numpy as np
import pandas as pd

from loaders.career_coverage import (
    cached_page_ids,
    coverage_rows,
    coverage_summary,
    describe,
    is_coverage_symmetric,
)
from loaders.crossorg_identity import (
    apply_identity_map,
    build_identity_map,
    resolve_by_bout_evidence,
    resolve_collisions,
)
from loaders.sherdog_loader import classify_method
from project_helpers import normalize_name_key

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MAJORS_DIR = PROJECT_ROOT / "data" / "external" / "sherdog"
MAJORS_BOUTS = "majors_bouts.parquet"
# The archived ``build_crossorg_careers.py`` wrote event cards and whole-career
# pages already merged into one table. It SUPERSEDES ``majors_bouts`` -- it is
# not an extension to concatenate alongside it.
MAJORS_CAREERS = "crossorg_bouts.parquet"
SNAPSHOT_ARTIFACT = "majors_fights.parquet"
CAREER_COVERAGE_ARTIFACT = "career_coverage.parquet"
SHERDOG_BIRTH_DATES_ARTIFACT = "sherdog_birth_dates.parquet"
_BIRTH_DATE_RE = re.compile(
    r'itemprop=["\']birthDate["\'][^>]*>\s*([^<]+?)\s*</span>', re.IGNORECASE
)

# Same buckets the UFCStats loader scores. Kept here rather than imported so a
# change to one source's scoring is a deliberate change to both.
METHOD_SCORE = {
    "KO/TKO": 1.00,
    "Submission": 1.00,
    "Decision - Unanimous": 0.90,
    "Decision - Majority": 0.85,
    "Decision - Split": 0.80,
    "DQ": 0.50,
    "Could Not Continue": 0.50,
    "Overturned": 0.50,
    "Other": 0.90,
}
# Bouts whose result the rating must not read, matching the canonical policy.
UNRATEABLE_METHODS = {"Overturned", "Could Not Continue"}

CANONICAL_COLUMNS = [
    "fight_url", "event_url", "event_name", "event_date", "event_location",
    "fighter_a", "fighter_b", "fighter_a_outcome", "fighter_b_outcome",
    "winner", "loser", "is_draw", "is_nc", "is_excluded", "exclusion_reason",
    "weight_class", "is_title_fight", "method_raw", "method_class",
    "method_score_winner", "end_round", "end_time_seconds", "referee",
    "details_text", "org", "source", "org_weight",
]


def load_majors_bouts(majors_dir: Path = DEFAULT_MAJORS_DIR) -> pd.DataFrame:
    """The whole-career table where it exists, else the event cards alone.

    The event crawl is roster-complete *within six promotions*, which applies
    the same censoring one level down: a Bellator fighter's non-Bellator record
    is missing unless it happens to fall in another major. Fedor gets his PRIDE
    and Strikeforce years and loses RINGS -- the twelve bouts from May 2000
    where he was actually built.

    The completed whole-career crawl removed that boundary by reading one page
    per fighter, and its artifact holds event and career rows **already
    merged**. So this prefers that file outright rather than concatenating the
    two, which would double every bout the event crawl already had.

    The whole-career table is also what makes the identity join work. Sherdog's
    fighter page carries the subject's *whole* record, UFC bouts included, so
    ``resolve_by_bout_evidence`` can join an id to a canonical fighter on shared
    (date, opponent) pairs -- the tier that recovers a fighter indexed under a
    legal name their UFC record does not use. Event cards alone carry no UFC
    bouts, so that tier resolves nobody.
    """
    majors_dir = Path(majors_dir)
    careers_path = majors_dir / MAJORS_CAREERS
    bouts_path = majors_dir / MAJORS_BOUTS
    path = careers_path if careers_path.exists() else bouts_path
    if not path.exists():
        raise FileNotFoundError(
            f"{bouts_path} does not exist. Run build_sherdog_majors.py first "
            "(cached pages are free). The optional completed whole-career "
            "artifact is crossorg_bouts.parquet."
        )
    bouts = pd.read_parquet(path)
    bouts["event_date"] = pd.to_datetime(bouts["event_date"], errors="coerce")
    return bouts.dropna(subset=["event_date", "fighter_a_id", "fighter_b_id"])


def resolve_identities(bouts: pd.DataFrame, canonical_fights: pd.DataFrame) -> pd.DataFrame:
    """Sherdog ids resolved to the canonical names the engine rates under.

    Three tiers, in the repo's own order of evidential strength: hand-verified
    overrides, then an exact normalized-name key, then shared bouts. A name
    that matches nothing keeps its Sherdog identity and is still rated -- it
    simply is not asserted to be someone already in the UFC set.
    """
    core = sorted(set(canonical_fights["fighter_a"]) | set(canonical_fights["fighter_b"]))
    identity = build_identity_map(bouts, core)
    identity = resolve_collisions(identity, bouts, canonical_fights)
    return resolve_by_bout_evidence(identity, bouts, canonical_fights)


def to_canonical_fights(bouts: pd.DataFrame, identity: pd.DataFrame) -> pd.DataFrame:
    """Reshape resolved card bouts into the canonical fight table's columns."""
    joined = apply_identity_map(bouts, identity)
    if joined.empty:
        return pd.DataFrame(columns=CANONICAL_COLUMNS)

    a_out = joined["fighter_a_outcome"].astype(str).str.lower().str.strip()
    b_out = joined["fighter_b_outcome"].astype(str).str.lower().str.strip()
    usable = a_out.isin(["win", "loss", "draw", "nc"]) & b_out.isin(["win", "loss", "draw", "nc"])
    joined, a_out, b_out = joined[usable], a_out[usable], b_out[usable]
    joined = joined[joined["fighter_a"].ne(joined["fighter_b"])]
    a_out, b_out = a_out.loc[joined.index], b_out.loc[joined.index]
    if joined.empty:
        return pd.DataFrame(columns=CANONICAL_COLUMNS)

    is_draw = a_out.eq("draw") | b_out.eq("draw")
    is_nc = a_out.eq("nc") | b_out.eq("nc")
    winner = pd.Series(
        np.where(a_out.eq("win"), joined["fighter_a"],
                 np.where(b_out.eq("win"), joined["fighter_b"], None)),
        index=joined.index, dtype=object,
    )
    loser = pd.Series(
        np.where(a_out.eq("win"), joined["fighter_b"],
                 np.where(b_out.eq("win"), joined["fighter_a"], None)),
        index=joined.index, dtype=object,
    )
    method_class = joined["method_raw"].map(classify_method)
    # A card row can be a bare "Sherdog id pair on a date"; that is enough to
    # key it, and it is the same key the dedupe guard fingerprints on.
    fight_url = (
        "sherdog-majors::" + joined["event_id"].astype(str)
        + "::" + joined["fighter_a_id"].astype(str)
        + "::" + joined["fighter_b_id"].astype(str)
    )

    out = pd.DataFrame({
        "fight_url": fight_url,
        "event_url": "sherdog-event::" + joined["event_id"].astype(str),
        "event_name": joined["org"].astype(str) + " | " + joined["event_name"].astype(str),
        "event_date": joined["event_date"],
        "event_location": joined.get("event_location"),
        "fighter_a": joined["fighter_a"],
        "fighter_b": joined["fighter_b"],
        "fighter_a_outcome": a_out,
        "fighter_b_outcome": b_out,
        "winner": winner,
        "loser": loser,
        "is_draw": is_draw,
        "is_nc": is_nc,
        "weight_class": joined.get("weight_class"),
        "is_title_fight": joined.get("is_title_fight", False),
        "method_raw": joined["method_raw"],
        "method_class": method_class,
        "method_score_winner": method_class.map(METHOD_SCORE).fillna(0.90),
        "end_round": joined.get("end_round"),
        "end_time_seconds": joined.get("end_time_seconds"),
        "referee": joined.get("referee"),
        "details_text": "",
        "org": joined["org"],
        "source": "sherdog_majors",
        # Never an organisation weight. See the module docstring.
        "org_weight": 1.0,
    })
    unrateable = out["method_class"].isin(UNRATEABLE_METHODS) | out["is_nc"]
    out["is_excluded"] = unrateable
    out["exclusion_reason"] = np.where(
        unrateable, "result_not_rateable::" + out["method_class"].astype(str), None)
    out = out[CANONICAL_COLUMNS].sort_values(["event_date", "fight_url"])
    return out.reset_index(drop=True)


def _build_majors_fights(
    canonical_fights: pd.DataFrame,
    *,
    majors_dir: Path = DEFAULT_MAJORS_DIR,
) -> tuple[pd.DataFrame, dict, pd.DataFrame]:
    """The majors scope as canonical-shaped rows, plus a coverage report."""
    bouts = load_majors_bouts(majors_dir)
    identity = resolve_identities(bouts, canonical_fights)
    fights = to_canonical_fights(bouts, identity)

    core = set(canonical_fights["fighter_a"]) | set(canonical_fights["fighter_b"])
    joined_names = set(fights["fighter_a"]) | set(fights["fighter_b"])
    by_method = identity["join_method"].value_counts()
    report = {
        "source_bouts": int(len(bouts)),
        "rateable_bouts": int((~fights["is_excluded"]).sum()),
        "excluded_bouts": int(fights["is_excluded"].sum()),
        "fighters": int(len(joined_names)),
        "fighters_shared_with_ufc": int(len(joined_names & core)),
        "identity_join_methods": {str(k): int(v) for k, v in by_method.items()},
        "by_org": fights["org"].value_counts().to_dict(),
        "date_span": [str(fights["event_date"].min().date()),
                      str(fights["event_date"].max().date())] if len(fights) else None,
        "careers_extension_present": (Path(majors_dir) / MAJORS_CAREERS).exists(),
        "promotions_named": int(fights["org"].notna().sum()),
        "promotions_unnamed": int(fights["org"].isna().sum()),
    }
    return fights, report, identity


def build_majors_fights(
    canonical_fights: pd.DataFrame,
    *,
    majors_dir: Path = DEFAULT_MAJORS_DIR,
) -> tuple[pd.DataFrame, dict]:
    """Public two-value form retained for callers that do not need identity."""
    fights, report, _ = _build_majors_fights(
        canonical_fights, majors_dir=majors_dir
    )
    return fights, report


def sherdog_birth_dates(
    identity: pd.DataFrame,
    *,
    cache_dir: Path,
) -> pd.DataFrame:
    """Birth dates from cached Sherdog profiles, under resolved rating names."""
    names = identity.set_index(identity["sherdog_id"].astype(str))["canonical_name"]
    rows = []
    for path in sorted(Path(cache_dir).glob("*.html.gz")):
        fighter_id = path.name.split(".", 1)[0]
        if fighter_id not in names.index:
            continue
        try:
            with gzip.open(path, "rt", encoding="utf-8", errors="ignore") as handle:
                match = _BIRTH_DATE_RE.search(handle.read())
        except OSError:
            continue
        if match is None:
            continue
        dob = pd.to_datetime(match.group(1).strip(), errors="coerce")
        if pd.isna(dob):
            continue
        rows.append({
            "fighter": names.loc[fighter_id],
            "dob": dob,
            "source": "sherdog_profile",
            "source_id": fighter_id,
        })
    if not rows:
        return pd.DataFrame(columns=["fighter", "dob", "source", "source_id"])
    out = pd.DataFrame(rows).sort_values(["fighter", "source_id"])
    # Identity collisions are already resolved upstream. If multiple Sherdog
    # ids land on one canonical name, agree-or-first is deterministic and the
    # UFCStats date will take precedence in ratings.age.load_birth_dates.
    return out.drop_duplicates("fighter", keep="first").reset_index(drop=True)


def stage_majors_scope(
    snapshot_dir: Path,
    *,
    majors_dir: Path = DEFAULT_MAJORS_DIR,
) -> dict:
    """Write ``majors_fights.parquet`` beside the snapshot it belongs to."""
    snapshot_dir = Path(snapshot_dir)
    canonical = pd.read_parquet(snapshot_dir / "canonical_fights.parquet")
    fights, report, identity = _build_majors_fights(canonical, majors_dir=majors_dir)
    fights.to_parquet(snapshot_dir / SNAPSHOT_ARTIFACT, index=False)
    cache_dir = Path(majors_dir) / "fighters"
    births = sherdog_birth_dates(identity, cache_dir=cache_dir)
    births.to_parquet(snapshot_dir / SHERDOG_BIRTH_DATES_ARTIFACT, index=False)
    report["birth_dates"] = int(len(births))
    report["artifact"] = str(snapshot_dir / SNAPSHOT_ARTIFACT)

    # Whether the corpus applies one coverage rule to every fighter is a
    # property of what was staged, so it is measured here, next to the staging,
    # rather than inferred later from ratings that already contain the defect.
    resolved = identity[identity["join_method"].ne("unjoined")]
    coverage = coverage_rows(
        canonical,
        pd.concat([canonical, fights], ignore_index=True, sort=False),
        sherdog_ids=(
            resolved.assign(_id=resolved["sherdog_id"].astype(str))
            .drop_duplicates("canonical_name")
            .set_index("canonical_name")["_id"]
        ),
        read_ids=cached_page_ids(cache_dir),
    )
    coverage.to_parquet(snapshot_dir / CAREER_COVERAGE_ARTIFACT, index=False)
    summary = coverage_summary(coverage)
    report["career_coverage"] = summary
    print(f"[majors] {describe(summary)}")
    if not is_coverage_symmetric(summary):
        print(
            "[majors] WARNING: the corpus holds whole careers for some fighters and "
            "only their crawled-promotion bouts for others. A low-loss record's "
            "rating grows with the number of bouts the corpus happens to hold, so "
            "this is a rating defect, not a reporting one. "
            "Run build_sherdog_careers.py."
        )
    return report


def unmatched_names(bouts: pd.DataFrame, identity: pd.DataFrame, *, top: int = 40) -> pd.DataFrame:
    """The busiest Sherdog ids that did not join a canonical fighter.

    A name-matching audit, not a rating input: these fighters are still rated
    under their Sherdog identity. A UFC fighter appearing here is a missed
    join, and the fix is an entry in ``identity_overrides.csv``.
    """
    unjoined = identity[identity["join_method"].isin({"unjoined", "collision"})]
    counts = pd.concat([bouts["fighter_a_id"], bouts["fighter_b_id"]]).value_counts()
    out = unjoined.assign(bouts=unjoined["sherdog_id"].map(counts).fillna(0).astype(int))
    out["name_key"] = out["sherdog_name"].map(lambda n: normalize_name_key(n, compact=True))
    return out.sort_values("bouts", ascending=False).head(top).reset_index(drop=True)
