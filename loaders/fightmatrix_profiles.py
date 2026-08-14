"""Cache and parse the public FightMatrix ranked-cohort fighter profiles.

This is deliberately a bounded crawl: seed profiles come from the persisted
current-division and all-time ranking tables.  Opponent links are recorded but
not recursively crawled.  FightMatrix-derived ranks and percentages are kept
for audit/benchmarking; only official bout results are shaped into rating input.
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import pandas as pd
import requests
from bs4 import BeautifulSoup

from loaders.sherdog_loader import (
    classify_method,
    compute_fight_weights,
    is_title_event,
    org_from_event,
    to_canonical_fights,
)
from project_helpers import normalize_name_key


PROJECT_ROOT = Path(__file__).resolve().parent.parent
BASE_URL = "https://www.fightmatrix.com"
USER_AGENT = "Symon-UFC-Rank-Engine/0.2 (+local research; polite bounded cache)"
DEFAULT_PROFILE_CACHE_DIR = PROJECT_ROOT / "data" / "external" / "fightmatrix" / "profiles"

PROFILE_COLUMNS = [
    "profile_id", "fighter", "profile_url", "sherdog_url", "issue_date",
    "rank_state", "birth_date", "last_five_results", "association",
    "pro_debut_date", "pro_record", "current_ranking_text",
    "big_league_record", "last_three_years_record", "win_finish_pct",
    "combat_age", "quality_performance_pct", "last_quality_performance_date",
    "opponent_540_metric", "rating_points", "ufc_record",
    "octagon_time", "title_bout_record", "ufc_debut_date",
    "last_ufc_fight_date", "seed_divisions", "seed_sources", "seed_rank_min",
    "profile_bout_count",
]

BOUT_COLUMNS = [
    "fight_key", "event_id", "event_url", "event_name", "event_date",
    "event_country_code", "fighter", "fighter_profile_id", "opponent",
    "opponent_profile_id", "opponent_profile_url", "result",
    "opponent_prefight_rank", "opponent_prefight_division", "method_raw",
    "method_class", "end_round", "end_time_seconds", "org",
    "is_title_fight", "source", "source_profile_url",
]

_DIVISION_LABELS = {
    "heavyweight": "Heavyweight",
    "light-heavyweight": "Light Heavyweight",
    "middleweight": "Middleweight",
    "welterweight": "Welterweight",
    "lightweight": "Lightweight",
    "featherweight": "Featherweight",
    "bantamweight": "Bantamweight",
    "flyweight": "Flyweight",
    "womens-bantamweight": "Women's Bantamweight",
    "womens-flyweight": "Women's Flyweight",
    "womens-strawweight": "Women's Strawweight",
}


def _id_from_url(url: str | None, kind: str) -> str | None:
    if not isinstance(url, str):
        return None
    match = re.search(rf"/{kind}/(?:[^/]+/)?(\d+)/?", url)
    return match.group(1) if match else None


def _profile_cache_path(cache_dir: Path, profile_url: str) -> Path:
    profile_id = _id_from_url(profile_url, "fighter-profile")
    if not profile_id:
        raise ValueError(f"FightMatrix profile URL has no numeric id: {profile_url}")
    return cache_dir / f"{profile_id}.html"


def fetch_profile_html(
    profile_url: str,
    cache_dir: Path,
    *,
    refresh: bool = False,
    sleep_seconds: float = 1.0,
    verify_tls: bool = True,
) -> str:
    """Return one public profile page, preferring the persistent local cache."""
    parsed = urlparse(profile_url)
    if parsed.scheme != "https" or parsed.netloc.lower() not in {
        "fightmatrix.com", "www.fightmatrix.com",
    }:
        raise ValueError(f"refusing non-FightMatrix profile URL: {profile_url}")
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = _profile_cache_path(cache_dir, profile_url)
    if path.exists() and not refresh:
        return path.read_text(encoding="utf-8", errors="replace")

    if not verify_tls:
        from urllib3 import disable_warnings
        from urllib3.exceptions import InsecureRequestWarning
        disable_warnings(InsecureRequestWarning)
    response = requests.get(
        profile_url,
        headers={"User-Agent": USER_AGENT},
        timeout=30,
        verify=verify_tls,
    )
    response.raise_for_status()
    path.write_text(response.text, encoding="utf-8")
    if sleep_seconds > 0:
        time.sleep(sleep_seconds)
    return response.text


def _parse_date(value: str | None) -> pd.Timestamp | pd.NaT:
    if not isinstance(value, str) or not value.strip():
        return pd.NaT
    cleaned = re.sub(r"\b(\d{1,2})(st|nd|rd|th)\b", r"\1", value.strip())
    cleaned = re.sub(r"^[A-Za-z]+,\s*", "", cleaned)
    return pd.to_datetime(cleaned, errors="coerce")


def _percent(value: str | None) -> float | None:
    if not isinstance(value, str):
        return None
    number = pd.to_numeric(value.strip().rstrip("%"), errors="coerce")
    return None if pd.isna(number) else float(number)


def _summary_value(text: str, label: str, next_labels: tuple[str, ...]) -> str | None:
    stop = "|".join(re.escape(item) for item in next_labels)
    match = re.search(rf"{re.escape(label)}\s*(.*?)(?=\s+(?:{stop})\s*|$)", text)
    return match.group(1).strip() if match else None


def _match(text: str, pattern: str) -> str | None:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    return match.group(1).strip() if match else None


def _event_org(event_name: str | None) -> str:
    known = org_from_event(event_name)
    if known:
        return known
    name = " ".join(str(event_name or "Unknown").split())
    prefix = re.split(r"\s+-\s+|\s+\d+\b", name, maxsplit=1)[0].strip()
    return prefix or "Unknown"


def _fight_key(event_id: str | None, event_date, fighter: str, opponent: str) -> str:
    people = "::".join(sorted([
        normalize_name_key(fighter, compact=True),
        normalize_name_key(opponent, compact=True),
    ]))
    event_part = event_id or (
        pd.Timestamp(event_date).strftime("%Y%m%d") if pd.notna(event_date) else "undated"
    )
    return f"fightmatrix::{event_part}::{people}"


def parse_profile_html(profile_html: str, profile_url: str) -> tuple[dict, pd.DataFrame]:
    """Parse one FightMatrix public profile into metadata and bout rows."""
    soup = BeautifulSoup(profile_html, "html.parser")
    heading = soup.find("h1")
    fighter = heading.get_text(" ", strip=True) if heading else None
    profile_id = _id_from_url(profile_url, "fighter-profile")
    tables = soup.select("table.tblRank")
    summary_text = " ".join(tables[0].get_text(" ", strip=True).split()) if tables else ""
    page_text = " ".join(soup.get_text(" ", strip=True).split())
    sherdog = soup.select_one('a[href*="sherdog.com/fighter/"]')

    profile = {
        "profile_id": profile_id,
        "fighter": fighter,
        "profile_url": profile_url,
        "sherdog_url": sherdog.get("href") if sherdog else None,
        "issue_date": _parse_date(_match(page_text, r"Issue Date:\s*([0-9/]+)")),
        "rank_state": _match(summary_text, r"Rank State:\s*(.*?)\s+Birth Date:"),
        "birth_date": _parse_date(_match(summary_text, r"Birth Date:\s*(\d{4}-\d{2}-\d{2})")),
        "last_five_results": _match(summary_text, r"Last 5:\s*([WLDNCTKOSUB ]+?)\s+Association:"),
        "association": _summary_value(summary_text, "Association:", ("Pro Debut Date:",)),
        "pro_debut_date": _parse_date(_match(summary_text, r"Pro Debut Date:\s*(\d{4}-\d{2}-\d{2})")),
        "pro_record": _match(summary_text, r"Pro Record:\s*(\d+-\d+-\d+(?:\s*,\s*\d+\s+NC)?)"),
        "current_ranking_text": _match(summary_text, r"Current Ranking:\s*(.*?)\s+'Big League' Record:"),
        "big_league_record": _match(summary_text, r"'Big League' Record:\s*(\d+-\d+-\d+)"),
        "last_three_years_record": _match(summary_text, r"Last 3 Years:\s*(\d+-\d+-\d+)"),
        "win_finish_pct": _percent(_match(summary_text, r"Win Finish %:\s*([0-9.]+%)")),
        "combat_age": pd.to_numeric(_match(summary_text, r"Combat Age:\s*([0-9.]+)"), errors="coerce"),
        "quality_performance_pct": _percent(_match(summary_text, r"Quality Perf\. %:\s*([0-9.]+%)")),
        "last_quality_performance_date": _parse_date(_match(
            summary_text, r"Last Quality Perf\.:\s*(\d{4}-\d{2}-\d{2})"
        )),
        "opponent_540_metric": pd.to_numeric(
            _match(summary_text, r"540 Metric:\s*([0-9.]+)"), errors="coerce"
        ),
        "rating_points": pd.to_numeric(
            _match(summary_text, r"Rating Points:\s*([0-9.]+)"), errors="coerce"
        ),
        "ufc_record": _summary_value(summary_text, "UFC Record:", ("Octagon Time:",)),
        "octagon_time": _match(summary_text, r"Octagon Time:\s*([0-9:]+)"),
        "title_bout_record": _match(summary_text, r"Title Bouts:\s*(\d+-\d+-\d+)"),
        "ufc_debut_date": _parse_date(_match(summary_text, r"UFC Debut:\s*(\d{4}-\d{2}-\d{2})")),
        "last_ufc_fight_date": _parse_date(_match(summary_text, r"Last UFC Fight:\s*(\d{4}-\d{2}-\d{2})")),
    }

    history_table = None
    for table in tables[1:]:
        header = " ".join(table.find("tr").get_text(" ", strip=True).split()) if table.find("tr") else ""
        if "Opponent" in header and "Outcome" in header:
            history_table = table
            break
    if history_table is None:
        return profile, pd.DataFrame(columns=BOUT_COLUMNS)

    rows = history_table.find_all("tr")
    bouts: list[dict] = []
    i = 1
    while i < len(rows):
        result_row = rows[i]
        cells = result_row.find_all("td", recursive=False)
        result = cells[0].get_text(" ", strip=True).upper() if cells else ""
        opponent_link = result_row.select_one('a[href*="fighter-profile"]')
        if result not in {"W", "L", "D", "NC"} or opponent_link is None or i + 1 >= len(rows):
            i += 1
            continue

        event_row = rows[i + 1]
        event_link = event_row.select_one('a[href*="/event/"]')
        opponent = opponent_link.get_text(" ", strip=True)
        opponent_url = urljoin(BASE_URL, opponent_link.get("href"))
        opponent_context = result_row.find("em")
        context_text = opponent_context.get_text(" ", strip=True) if opponent_context else ""
        context_match = re.match(r"#(\d+)\s+(.+)", context_text)
        method_cell = cells[-1].get_text(" ", strip=True) if len(cells) >= 3 else ""
        round_match = re.search(r"\bRound\s+(\d+)\b", method_cell, flags=re.IGNORECASE)
        method_raw = re.sub(r"\s*\bRound\s+\d+\b.*$", "", method_cell, flags=re.IGNORECASE).strip()
        event_url = urljoin(BASE_URL, event_link.get("href")) if event_link else None
        event_id = _id_from_url(event_url, "event")
        event_name = event_link.get_text(" ", strip=True) if event_link else None
        date_node = event_row.find("em")
        event_date = _parse_date(date_node.get_text(" ", strip=True) if date_node else None)
        flag = event_row.select_one('img[src*="/images/flag/"]')
        flag_match = re.search(r"/flag/([A-Za-z]+)\.png", flag.get("src", "")) if flag else None
        result_name = {"W": "win", "L": "loss", "D": "draw", "NC": "nc"}[result]

        bouts.append({
            "fight_key": _fight_key(event_id, event_date, fighter or "", opponent),
            "event_id": event_id,
            "event_url": event_url,
            "event_name": event_name,
            "event_date": event_date,
            "event_country_code": flag_match.group(1).upper() if flag_match else None,
            "fighter": fighter,
            "fighter_profile_id": profile_id,
            "opponent": opponent,
            "opponent_profile_id": _id_from_url(opponent_url, "fighter-profile"),
            "opponent_profile_url": opponent_url,
            "result": result_name,
            "opponent_prefight_rank": int(context_match.group(1)) if context_match else None,
            "opponent_prefight_division": context_match.group(2) if context_match else None,
            "method_raw": method_raw or None,
            "method_class": classify_method(method_raw),
            "end_round": int(round_match.group(1)) if round_match else None,
            "end_time_seconds": None,
            "org": _event_org(event_name),
            "is_title_fight": is_title_event(event_name),
            "source": "fightmatrix_public",
            "source_profile_url": profile_url,
        })
        i += 2

    return profile, pd.DataFrame(bouts, columns=BOUT_COLUMNS)


def _seed_profiles(snapshot_dir: Path) -> pd.DataFrame:
    frames = []
    for filename, source in (
        ("fightmatrix_rankings.parquet", "current"),
        ("fightmatrix_all_time.parquet", "all_time"),
    ):
        path = snapshot_dir / filename
        if not path.exists():
            continue
        frame = pd.read_parquet(path)
        if frame.empty or "profile_url" not in frame.columns:
            continue
        frame = frame[["fighter", "profile_url", "division", "rank"]].copy()
        frame["seed_source"] = source
        frames.append(frame)
    if not frames:
        return pd.DataFrame(columns=["fighter", "profile_url", "seed_divisions", "seed_sources", "seed_rank_min"])
    all_seeds = pd.concat(frames, ignore_index=True).dropna(subset=["profile_url"])
    rows = []
    for url, group in all_seeds.groupby("profile_url", sort=False):
        divisions = sorted(set(group["division"].dropna().astype(str)))
        sources = sorted(set(group["seed_source"].dropna().astype(str)))
        rows.append({
            "fighter": group.iloc[0]["fighter"],
            "profile_url": url,
            "seed_divisions": "|".join(divisions),
            "seed_sources": "|".join(sources),
            "seed_rank_min": int(pd.to_numeric(group["rank"], errors="coerce").min()),
        })
    return pd.DataFrame(rows)


def _name_and_division_maps(snapshot_dir: Path, seeds: pd.DataFrame, profiles: pd.DataFrame):
    db_name_map: dict[str, str] = {}
    division_map: dict[str, str] = {}
    fighters_path = snapshot_dir / "canonical_fighters.parquet"
    if fighters_path.exists():
        for name in pd.read_parquet(fighters_path)["fighter"].dropna().astype(str):
            db_name_map[normalize_name_key(name, compact=True)] = name
    current_path = snapshot_dir / "ratings_current.parquet"
    if current_path.exists():
        current = pd.read_parquet(current_path)
        for row in current.itertuples(index=False):
            name = getattr(row, "fighter", None)
            if not isinstance(name, str):
                continue
            db_name_map[normalize_name_key(name, compact=True)] = name
            division = getattr(row, "recent_division", None) or getattr(row, "career_division", None)
            if isinstance(division, str) and division:
                division_map[normalize_name_key(name, compact=True)] = division

    seed_lookup = dict(zip(seeds["profile_url"], seeds["seed_divisions"]))
    for row in profiles.itertuples(index=False):
        name = row.fighter
        key = normalize_name_key(name, compact=True)
        db_name_map.setdefault(key, name)
        divisions = str(seed_lookup.get(row.profile_url, "")).split("|")
        labels = [_DIVISION_LABELS[d] for d in divisions if d in _DIVISION_LABELS]
        if labels:
            division_map.setdefault(key, labels[0])
    return db_name_map, division_map


def _dedupe_bouts(bouts: pd.DataFrame) -> pd.DataFrame:
    if bouts.empty:
        return bouts
    out = bouts.copy()
    out["_decisive"] = out["result"].isin(["win", "loss"]).astype(int)
    out = out.sort_values(["fight_key", "_decisive"], ascending=[True, False])
    perspectives = out.groupby("fight_key").size().rename("source_perspectives")
    out = out.drop_duplicates("fight_key", keep="first").drop(columns="_decisive")
    return out.merge(perspectives, on="fight_key", how="left")


def _bout_fingerprint(frame: pd.DataFrame) -> pd.Series:
    dates = pd.to_datetime(frame["event_date"], errors="coerce").dt.strftime("%Y%m%d").fillna("")
    pairs = [
        "::".join(sorted([
            normalize_name_key(a, compact=True), normalize_name_key(b, compact=True),
        ]))
        for a, b in zip(frame["fighter_a"], frame["fighter_b"])
    ]
    return dates + "::" + pd.Series(pairs, index=frame.index)


def build_public_profile_snapshot(
    snapshot_dir: Path,
    *,
    cache_dir: Path = DEFAULT_PROFILE_CACHE_DIR,
    refresh: bool = False,
    sleep_seconds: float = 1.0,
    verify_tls: bool = True,
    max_profiles: int | None = None,
    progress: bool = True,
) -> dict:
    """Cache ranked-cohort profiles and stage public bout/cross-org artifacts."""
    snapshot_dir = Path(snapshot_dir).resolve()
    cache_dir = Path(cache_dir).resolve()
    seeds = _seed_profiles(snapshot_dir)
    if max_profiles is not None:
        seeds = seeds.head(max(0, int(max_profiles)))
    if seeds.empty:
        raise ValueError("no FightMatrix profile URLs found; build ranking artifacts first")

    profile_rows: list[dict] = []
    bout_frames: list[pd.DataFrame] = []
    failures: list[dict] = []
    total = len(seeds)
    for position, seed in enumerate(seeds.itertuples(index=False), 1):
        try:
            profile_html = fetch_profile_html(
                seed.profile_url,
                cache_dir,
                refresh=refresh,
                sleep_seconds=sleep_seconds,
                verify_tls=verify_tls,
            )
            profile, bouts = parse_profile_html(profile_html, seed.profile_url)
            profile.update({
                "seed_divisions": seed.seed_divisions,
                "seed_sources": seed.seed_sources,
                "seed_rank_min": seed.seed_rank_min,
                "profile_bout_count": int(len(bouts)),
            })
            profile_rows.append(profile)
            if not bouts.empty:
                bout_frames.append(bouts)
        except Exception as exc:
            failures.append({"profile_url": seed.profile_url, "error": f"{type(exc).__name__}: {exc}"})
        if progress and (position == total or position % 25 == 0):
            print(f"[fightmatrix profiles] {position}/{total}; failures={len(failures)}", flush=True)

    profiles = pd.DataFrame(profile_rows).reindex(columns=PROFILE_COLUMNS)
    all_bouts = pd.concat(bout_frames, ignore_index=True) if bout_frames else pd.DataFrame(columns=BOUT_COLUMNS)
    bouts = _dedupe_bouts(all_bouts)
    profiles.to_parquet(snapshot_dir / "fightmatrix_profiles.parquet", index=False)
    bouts.to_parquet(snapshot_dir / "fightmatrix_bouts.parquet", index=False)

    db_name_map, division_map = _name_and_division_maps(snapshot_dir, seeds, profiles)
    rated_raw = bouts[bouts["org"].ne("UFC")].copy()
    fm_crossorg = to_canonical_fights(rated_raw, db_name_map, division_map)
    if not fm_crossorg.empty:
        fm_crossorg["_fingerprint"] = _bout_fingerprint(fm_crossorg)
        fm_crossorg = fm_crossorg.drop_duplicates("_fingerprint", keep="first")
        canonical_path = snapshot_dir / "canonical_fights.parquet"
        if canonical_path.exists():
            canonical = pd.read_parquet(canonical_path)
            canonical_keys = set(_bout_fingerprint(canonical))
            fm_crossorg = fm_crossorg[~fm_crossorg["_fingerprint"].isin(canonical_keys)]
        fm_crossorg = fm_crossorg.drop(columns="_fingerprint").reset_index(drop=True)
        current = pd.read_parquet(snapshot_dir / "ratings_current.parquet")
        fm_crossorg["org_weight"] = compute_fight_weights(fm_crossorg, current).values
        fm_crossorg["source"] = "fightmatrix_public"
    fm_crossorg.to_parquet(snapshot_dir / "fightmatrix_crossorg_fights.parquet", index=False)

    combined = fm_crossorg.copy()
    existing_path = snapshot_dir / "crossorg_fights.parquet"
    if existing_path.exists():
        existing = pd.read_parquet(existing_path)
        if "source" in existing.columns:
            existing = existing[existing["source"].ne("fightmatrix_public")]
        combined = pd.concat([existing, fm_crossorg], ignore_index=True, sort=False)
    if not combined.empty:
        combined["_fingerprint"] = _bout_fingerprint(combined)
        combined = combined.drop_duplicates("_fingerprint", keep="first").drop(columns="_fingerprint")
    combined.to_parquet(existing_path, index=False)

    org_counts = fm_crossorg["org"].value_counts() if not fm_crossorg.empty else pd.Series(dtype=int)
    top_org_counts = org_counts.head(50).to_dict()
    if len(org_counts) > 50:
        top_org_counts["Other organizations"] = int(org_counts.iloc[50:].sum())
    summary = {
        "source": BASE_URL,
        "scope": "profiles linked from current division and all-time ranking artifacts; no recursive opponent crawl",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "profile_seeds": int(total),
        "profiles_loaded": int(len(profiles)),
        "profile_failures": failures,
        "unique_public_bouts": int(len(bouts)),
        "public_non_ufc_bouts": int(bouts["org"].ne("UFC").sum()) if not bouts.empty else 0,
        "rated_crossorg_bouts": int(len(fm_crossorg)),
        "combined_crossorg_bouts": int(len(combined)),
        "rated_crossorg_org_count": int(len(org_counts)),
        "rated_crossorg_by_org_top50": top_org_counts,
        "profile_cache": str(cache_dir.relative_to(PROJECT_ROOT)),
        "tls_verification": bool(verify_tls),
    }
    (snapshot_dir / "fightmatrix_profiles_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    return summary
