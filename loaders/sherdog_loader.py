"""Cross-organization bout ingestion from Sherdog fighter pages.

The canonical UFC snapshot only covers UFC bouts. To rate fighters on their
*whole* careers we pull their pre/non-UFC bouts (PRIDE, StrikeForce, WEC, and
other promotions) from Sherdog, the authoritative MMA record source.

Pipeline per fighter:
  resolve name -> Sherdog fighter URL via the fightfinder search,
  fetch + cache the fighter page HTML,
  parse the ``new_table fighter`` history table
  (Result / Opponent / Event+date / Method/Referee / Round / Time).

We then keep only the non-UFC bouts, dedupe, name-match opponents to the
canonical UFC fighter set, and emit rows shaped like ``canonical_fights`` so
they merge straight into the rating engine. Method-of-victory, round, and time
are sourced so cross-org bouts feed the method and performance sleeves exactly
like UFC bouts; weight class (absent from Sherdog history rows) is filled from
the fighter's UFC division by the caller, and title bouts are flagged from the
event name.

All HTML is cached project-local under ``data/external/sherdog/`` and never
redistributed. bs4 + requests only (no lxml).
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

from project_helpers import normalize_name_key

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CACHE_DIR = PROJECT_ROOT / "data" / "external" / "sherdog"
BASE = "https://www.sherdog.com"
SEARCH_URL = BASE + "/stats/fightfinder?SearchTxt="
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120 Safari/537.36"
)
POLITE_DELAY_SECONDS = 1.2

# Organisations we ingest (everything else from a fighter's record is dropped).
# Each maps event-name regex -> normalized org label. UFC is recognised so we
# can *exclude* it (already in the canonical snapshot) and so the bridge
# calibration can line cross-org careers up against UFC.
_ORG_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bUFC\b|ultimate fighting", "UFC"),
    (r"\bpride\b|pride fc|pride fighting", "PRIDE"),
    (r"strikeforce", "Strikeforce"),
    (r"\bwec\b|world extreme cagefighting", "WEC"),
    (r"elitexc|elite xc|\bexc\b", "EliteXC"),
    (r"affliction", "Affliction"),
    (r"\bbellator\b", "Bellator"),
    (r"\bone\b.*championship|one fc|one:", "ONE"),
    (r"\bdream\b", "DREAM"),
    (r"\bk-1\b|k-1 ", "K-1"),
    (r"\binvicta\b", "Invicta"),
    (r"\brizin\b", "RIZIN"),
)

_TITLE_PATTERNS = re.compile(
    r"title|championship|grand prix final|gp final|\bbelt\b|tournament final",
    re.IGNORECASE,
)

_DATE_RE = re.compile(r"([A-Z][a-z]{2})\s*/\s*(\d{1,2})\s*/\s*(\d{4})")


# ---------------------------------------------------------------------------
# Network (cached)

def _session():
    import requests

    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT})
    return s


def _cached_get(url: str, cache_path: Path, session, *, delay: float = POLITE_DELAY_SECONDS) -> str | None:
    """Return text for ``url``, reading/writing ``cache_path``. Polite on miss."""
    if cache_path.exists():
        return cache_path.read_text(encoding="utf-8", errors="replace")
    try:
        time.sleep(delay)
        resp = session.get(url, timeout=30, allow_redirects=True)
    except Exception:
        return None
    if resp.status_code != 200:
        return None
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(resp.text, encoding="utf-8")
    return resp.text


# ---------------------------------------------------------------------------
# Parsing helpers

def org_from_event(event_name: str | None) -> str | None:
    if not isinstance(event_name, str):
        return None
    low = event_name.lower()
    for pattern, label in _ORG_PATTERNS:
        if re.search(pattern, low):
            return label
    return None


def is_title_event(event_name: str | None) -> bool:
    return bool(event_name) and bool(_TITLE_PATTERNS.search(event_name))


def classify_method(method_raw: str | None) -> str:
    """Map a Sherdog method string to the project's ``method_class`` buckets."""
    if not isinstance(method_raw, str) or not method_raw.strip():
        return "Other"
    m = method_raw.lower()
    if "disqualif" in m or re.search(r"\bdq\b", m):
        return "DQ"
    if "could not continue" in m or "technical draw" in m:
        return "Could Not Continue"
    if "overturn" in m or "no contest" in m or re.search(r"\bnc\b", m):
        return "Overturned"
    if "submission" in m:  # includes "technical submission"
        return "Submission"
    if "ko" in m or "tko" in m:  # KO, TKO, "KO (Punches)", "TKO (Doctor Stoppage)"
        return "KO/TKO"
    if "decision" in m:
        if "split" in m:
            return "Decision - Split"
        if "majority" in m:
            return "Decision - Majority"
        return "Decision - Unanimous"  # unanimous + technical/other decisions
    return "Other"


def _parse_event_cell(td) -> tuple[str | None, pd.Timestamp | None]:
    """Extract (event_name, event_date) from the Event cell."""
    text = td.get_text(" ", strip=True)
    date = None
    dm = _DATE_RE.search(text)
    if dm:
        try:
            date = pd.Timestamp(f"{dm.group(1)} {int(dm.group(2))} {dm.group(3)}")
        except Exception:
            date = None
    a = td.find("a")
    if a is not None and a.get_text(strip=True):
        name = a.get_text(" ", strip=True)
    else:
        name = _DATE_RE.sub("", text).strip(" -–") if dm else text
    return (name or None), date


def parse_fighter_history(html: str) -> pd.DataFrame:
    """Parse the Sherdog fighter-page history table into bout rows."""
    cols = ["result", "opponent", "event_name", "event_date",
            "method_raw", "method_class", "end_round", "end_time_seconds"]
    if not html:
        return pd.DataFrame(columns=cols)
    soup = BeautifulSoup(html, "html.parser")
    target = None
    for t in soup.find_all("table"):
        head = [c.get_text(strip=True) for c in (t.find("tr").find_all(["th", "td"]) if t.find("tr") else [])]
        if "Result" in head and any("Method" in h for h in head):
            target = t
            break
    if target is None:
        return pd.DataFrame(columns=cols)
    rows = []
    for tr in target.find_all("tr")[1:]:
        tds = tr.find_all("td")
        if len(tds) < 6:
            continue
        result = tds[0].get_text(strip=True).lower()
        opponent = tds[1].get_text(" ", strip=True)
        event_name, event_date = _parse_event_cell(tds[2])
        method_raw = tds[3].get_text(" ", strip=True)
        method_raw = re.sub(r"\s*VIEW PLAY-BY-PLAY\s*", "", method_raw, flags=re.IGNORECASE).strip()
        round_txt = tds[4].get_text(strip=True)
        time_txt = tds[5].get_text(strip=True)
        end_round = pd.to_numeric(round_txt, errors="coerce")
        end_seconds = None
        if ":" in time_txt:
            mm, _, ss = time_txt.partition(":")
            try:
                end_seconds = int(mm) * 60 + int(ss)
            except ValueError:
                end_seconds = None
        if not opponent or result not in {"win", "loss", "draw", "nc", "no contest"}:
            continue
        rows.append({
            "result": "nc" if result.startswith("no") else result,
            "opponent": opponent,
            "event_name": event_name,
            "event_date": event_date,
            "method_raw": method_raw,
            "method_class": classify_method(method_raw),
            "end_round": end_round,
            "end_time_seconds": end_seconds,
        })
    return pd.DataFrame(rows, columns=cols)


# ---------------------------------------------------------------------------
# Resolution + fetch

def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "+", name.strip().lower()).strip("+")


def resolve_fighter_url(name: str, session, cache_dir: Path) -> str | None:
    """Resolve a fighter name to a Sherdog ``/fighter/Name-ID`` path.

    Uses the fightfinder search and an exact normalized-name match (the search
    returns several popular fighters first, so the first hit is not reliable).
    """
    key = normalize_name_key(name, compact=True)
    search_cache = cache_dir / "search" / f"{key or _slugify(name)}.html"
    html = _cached_get(SEARCH_URL + _slugify(name), search_cache, session)
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")
    candidates: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if re.fullmatch(r"/fighter/[A-Za-z0-9.\-]+-\d+", href):
            anchor_name = a.get_text(" ", strip=True)
            if anchor_name and normalize_name_key(anchor_name, compact=True) == key:
                return href
            candidates.append(href)
    # Fall back: match the slug portion of the URL against the name key.
    for href in candidates:
        slug = href.split("/fighter/", 1)[1].rsplit("-", 1)[0]
        if normalize_name_key(slug.replace("-", " "), compact=True) == key:
            return href
    return None


def fetch_fighter_history(name: str, session, cache_dir: Path) -> pd.DataFrame:
    url = resolve_fighter_url(name, session, cache_dir)
    if not url:
        return pd.DataFrame()
    fid = url.rsplit("-", 1)[-1]
    page_cache = cache_dir / "fighter" / f"{fid}.html"
    html = _cached_get(BASE + url, page_cache, session)
    if not html:
        return pd.DataFrame()
    hist = parse_fighter_history(html)
    hist["sherdog_url"] = url
    return hist


# ---------------------------------------------------------------------------
# Cross-org bout assembly

def _fight_key(date: pd.Timestamp | None, a: str, b: str) -> str:
    names = "::".join(sorted([normalize_name_key(a, compact=True), normalize_name_key(b, compact=True)]))
    d = "" if date is None or pd.isna(date) else pd.Timestamp(date).strftime("%Y%m%d")
    return f"sherdog::{d}::{names}"


def build_crossorg_bouts(
    fighter_names: list[str],
    *,
    cache_dir: Path | str = DEFAULT_CACHE_DIR,
    include_orgs: tuple[str, ...] = ("PRIDE", "Strikeforce", "WEC"),
    progress: bool = False,
) -> pd.DataFrame:
    """Scrape ``fighter_names`` and return deduped non-UFC bouts (raw, un-joined).

    Output columns: fight_key, org, event_name, event_date, fighter, opponent,
    result, method_class, method_raw, end_round, end_time_seconds,
    is_title_fight, sherdog_url. One row per fighter-perspective; dedup to one
    canonical bout happens in :func:`to_canonical_fights`.
    """
    cache_dir = Path(cache_dir)
    session = _session()
    frames = []
    n = len(fighter_names)
    for i, name in enumerate(fighter_names, 1):
        if progress and (i % 25 == 0 or i == n):
            print(f"[sherdog] {i}/{n} fighters", flush=True)
        hist = fetch_fighter_history(name, session, cache_dir)
        if hist is None or hist.empty:
            continue
        hist = hist.copy()
        hist["org"] = hist["event_name"].map(org_from_event)
        hist = hist[hist["org"].isin(include_orgs)]
        if hist.empty:
            continue
        hist["fighter"] = name
        hist["is_title_fight"] = hist["event_name"].map(is_title_event)
        hist["fight_key"] = [
            _fight_key(d, name, o) for d, o in zip(hist["event_date"], hist["opponent"])
        ]
        frames.append(hist)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


# ---------------------------------------------------------------------------
# Canonicalisation — shape scraped bouts like ``canonical_fights``

_METHOD_SCORES = {
    "KO/TKO": 1.0, "Submission": 1.0,
    "Decision - Unanimous": 0.95, "Decision - Majority": 0.90,
    "Decision - Split": 0.90, "DQ": 0.85,
}


def to_canonical_fights(
    raw_bouts: pd.DataFrame,
    db_name_map: dict[str, str],
    division_map: dict[str, str],
) -> pd.DataFrame:
    """Dedupe scraped per-fighter rows into one canonical-shaped bout each.

    ``db_name_map``  : name_key -> canonical UFC spelling (so a cross-org bout
                       ties to the same fighter node as their UFC bouts).
    ``division_map`` : name_key -> UFC division (fills the weight class Sherdog
                       history rows omit).
    Only bouts with at least one DB-known participant are kept.
    """
    cols = [
        "fight_url", "event_url", "event_name", "event_date", "event_location",
        "bout_string", "fighter_a", "fighter_b", "fighter_a_outcome",
        "fighter_b_outcome", "winner", "loser", "is_draw", "is_nc",
        "is_excluded", "exclusion_reason", "weight_class", "is_title_fight",
        "method_raw", "method_class", "method_score_winner", "end_round",
        "end_time_seconds", "time_format", "referee", "details_text",
        "ped_confirmed", "ped_flagged_fighter", "ped_confirmation_source",
        "ped_confirmation_detail", "org", "source",
    ]
    if raw_bouts is None or raw_bouts.empty:
        return pd.DataFrame(columns=cols)

    def canon(name: str) -> tuple[str, bool]:
        key = normalize_name_key(name, compact=True)
        return db_name_map.get(key, name), (key in db_name_map)

    seen: dict[str, dict] = {}
    for r in raw_bouts.itertuples(index=False):
        result = r.result
        # Always orient as winner-perspective so winner/loser are deterministic.
        f_name, f_in = canon(r.fighter)
        o_name, o_in = canon(r.opponent)
        if not (f_in or o_in):
            continue
        if result == "win":
            a, b, winner, loser = f_name, o_name, f_name, o_name
        elif result == "loss":
            a, b, winner, loser = o_name, f_name, o_name, f_name
        else:  # draw / nc — orient fighter as a, opponent as b
            a, b, winner, loser = f_name, o_name, None, None
        key = r.fight_key
        is_draw = result == "draw"
        is_nc = result == "nc"
        # Prefer to keep a decisive perspective; if a dupe arrives that is
        # decisive and the stored one is not, overwrite.
        existing = seen.get(key)
        if existing is not None and not (existing["winner"] is None and winner is not None):
            continue
        div = division_map.get(normalize_name_key(a, compact=True)) \
            or division_map.get(normalize_name_key(b, compact=True)) \
            or "Open Weight"
        mc = r.method_class
        seen[key] = {
            "fight_url": key,
            "event_url": f"sherdog-event::{key}",
            "event_name": r.event_name,
            "event_date": r.event_date,
            "event_location": None,
            "bout_string": f"{a} vs. {b}",
            "fighter_a": a, "fighter_b": b,
            "fighter_a_outcome": ("W" if winner == a else "L" if winner == b else ("D" if is_draw else "NC")),
            "fighter_b_outcome": ("W" if winner == b else "L" if winner == a else ("D" if is_draw else "NC")),
            "winner": winner, "loser": loser,
            "is_draw": is_draw, "is_nc": is_nc,
            "is_excluded": False, "exclusion_reason": None,
            "weight_class": div,
            "is_title_fight": bool(r.is_title_fight),
            "method_raw": r.method_raw, "method_class": mc,
            "method_score_winner": _METHOD_SCORES.get(mc, 0.90),
            "end_round": r.end_round, "end_time_seconds": r.end_time_seconds,
            "time_format": None, "referee": None, "details_text": None,
            "ped_confirmed": False, "ped_flagged_fighter": None,
            "ped_confirmation_source": None, "ped_confirmation_detail": None,
            "org": r.org, "source": "sherdog",
        }
    out = pd.DataFrame(list(seen.values()), columns=cols)
    # Drop the unified-rules-era cutoff to match the UFC exclusion rule and
    # any bout missing a date (can't be placed in the rating timeline).
    out = out[out["event_date"].notna()]
    out = out[pd.to_datetime(out["event_date"]) >= pd.Timestamp("2000-11-17")]
    return out.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Bridge-calibrated per-org weights
#
# UFC is the elite reference. A non-UFC org's bouts update ratings at "an
# appropriate percentile of UFC", and that percentile is read off the org's
# "bridge" fighters — those who fought in both the org and the UFC. We take
# each bridge fighter's established UFC canonical rating (the cleanest yardstick
# of UFC-caliber), find the org's median bridge rating, and locate it in the
# UFC field's rating distribution. That empirical percentile *is* the weight:
# e.g. PRIDE's median bridge fighter at the 60th UFC percentile -> a PRIDE bout
# counts 0.60 of a UFC bout. Always < 1 (UFC is the full field), differentiated
# by org, and derived entirely from the common fighters, as requested.

def compute_org_weights(
    crossorg_fights: pd.DataFrame,
    ufc_ratings_current: pd.DataFrame,
    *,
    floor: float = 0.5,
    cap: float = 0.95,
    min_fights: int = 3,
) -> dict[str, float]:
    """Return {org -> weight in [floor, cap]} from bridge-fighter UFC percentile."""
    if crossorg_fights is None or crossorg_fights.empty:
        return {}
    ranked = ufc_ratings_current.copy()
    ranked["rating_periods"] = pd.to_numeric(ranked.get("rating_periods"), errors="coerce").fillna(0)
    ranked["mu_canonical"] = pd.to_numeric(ranked["mu_canonical"], errors="coerce")
    estab = ranked[(ranked["rating_periods"] >= min_fights) & ranked["mu_canonical"].notna()]
    established = {
        normalize_name_key(n, compact=True): m
        for n, m in zip(estab["fighter"], estab["mu_canonical"])
    }
    field = estab["mu_canonical"].to_numpy()
    if field.size == 0:
        return {org: floor for org in crossorg_fights["org"].dropna().unique()}

    weights: dict[str, float] = {}
    for org, g in crossorg_fights.groupby("org"):
        participants = pd.unique(pd.concat([g["fighter_a"], g["fighter_b"]]).dropna())
        cal = [established[normalize_name_key(p, compact=True)]
               for p in participants
               if normalize_name_key(p, compact=True) in established]
        if not cal:
            weights[org] = floor
            continue
        org_median = float(pd.Series(cal).median())
        percentile = float((field < org_median).mean())  # empirical CDF at org median
        weights[org] = float(min(cap, max(floor, percentile)))
    return weights


def _ufc_caliber_percentiles(
    ufc_ratings_current: pd.DataFrame, *, min_fights: int = 3,
) -> tuple[dict[str, float], "object"]:
    """Map every UFC fighter to their rating percentile within the UFC field.

    The field is the established (rating_periods >= min_fights) UFC roster; a
    fighter's caliber is where their canonical rating sits in that field's CDF.
    Returns (name_key -> percentile, field_array).
    """
    import numpy as np

    r = ufc_ratings_current.copy()
    r["rating_periods"] = pd.to_numeric(r.get("rating_periods"), errors="coerce").fillna(0)
    r["mu_canonical"] = pd.to_numeric(r["mu_canonical"], errors="coerce")
    field = r.loc[(r["rating_periods"] >= min_fights) & r["mu_canonical"].notna(), "mu_canonical"].to_numpy()
    pct: dict[str, float] = {}
    if field.size:
        for n, m in zip(r["fighter"], r["mu_canonical"]):
            if isinstance(n, str) and not pd.isna(m):
                pct[normalize_name_key(n, compact=True)] = float((field < m).mean())
    return pct, field


def compute_fight_weights(
    crossorg_fights: pd.DataFrame,
    ufc_ratings_current: pd.DataFrame,
    *,
    floor: float = 0.5,
    cap: float = 1.0,
    unknown_pct: float = 0.30,
    min_fights: int = 3,
) -> pd.Series:
    """Per-fight weight from the *participants'* UFC caliber, not the org.

    Each fighter's caliber is the percentile of their established UFC rating
    within the UFC field (bridge anchor); a fighter who never reached the UFC
    gets ``unknown_pct``. A bout's weight is the mean of its two participants'
    caliber, clipped to ``[floor, cap]``. Elite-vs-elite cross-org bouts
    (e.g. Henderson vs Silva) stay near full weight regardless of promotion;
    bouts involving unproven org fighters are down-weighted — which is the
    intent: lesser-known non-UFC fighters should not count like UFC fighters.
    """
    if crossorg_fights is None or crossorg_fights.empty:
        return pd.Series(dtype=float)
    pct, field = _ufc_caliber_percentiles(ufc_ratings_current, min_fights=min_fights)
    if field.size == 0:
        return pd.Series(floor, index=crossorg_fights.index)

    # One bridge hop for fighters who never reached the UFC (e.g. Fedor): infer
    # their caliber from the median UFC-anchored caliber of the opponents they
    # faced in these orgs, so a non-UFC great who beat UFC-caliber fighters is
    # not mistaken for an unknown. Falls back to ``unknown_pct`` if no anchored
    # opponent exists.
    inferred: dict[str, list[float]] = {}
    for fa, fb in zip(crossorg_fights["fighter_a"], crossorg_fights["fighter_b"]):
        ka = normalize_name_key(fa, compact=True) if isinstance(fa, str) else None
        kb = normalize_name_key(fb, compact=True) if isinstance(fb, str) else None
        if ka and kb:
            if ka not in pct and kb in pct:
                inferred.setdefault(ka, []).append(pct[kb])
            if kb not in pct and ka in pct:
                inferred.setdefault(kb, []).append(pct[ka])
    inferred_pct = {k: float(pd.Series(v).median()) for k, v in inferred.items() if v}

    def cal(name) -> float:
        if not isinstance(name, str):
            return unknown_pct
        k = normalize_name_key(name, compact=True)
        if k in pct:
            return pct[k]
        return inferred_pct.get(k, unknown_pct)

    a = crossorg_fights["fighter_a"].map(cal)
    b = crossorg_fights["fighter_b"].map(cal)
    return ((a + b) / 2.0).clip(lower=floor, upper=cap)


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Scrape Sherdog cross-org bouts.")
    ap.add_argument("names", nargs="*", help="fighter names to scrape")
    ap.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR))
    args = ap.parse_args()
    df = build_crossorg_bouts(args.names or ["Fedor Emelianenko", "Anderson Silva"],
                              cache_dir=args.cache_dir, progress=True)
    print(df.to_string())
