"""Fetch and parse FightMatrix ranking pages.

The linked Node packages were useful as references, but the live, working path
is simpler: request FightMatrix's public ranking pages directly, cache the HTML
inside this project, and parse each division table into parquet.
"""
from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from urllib.parse import urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup


PROJECT_ROOT = Path(__file__).resolve().parent.parent
BASE_URL = "https://www.fightmatrix.com"
USER_AGENT = "Symon-UFC-Rank-Engine/0.1 (+local research; polite cache)"

DIVISION_URLS = {
    "heavyweight": "/mma-ranks/heavyweight/",
    "light-heavyweight": "/mma-ranks/light-heavyweight/",
    "middleweight": "/mma-ranks/middleweight/",
    "welterweight": "/mma-ranks/welterweight/",
    "lightweight": "/mma-ranks/lightweight/",
    "featherweight": "/mma-ranks/featherweight/",
    "bantamweight": "/mma-ranks/bantamweight/",
    "flyweight": "/mma-ranks/flyweight/",
    "womens-pound-for-pound": "/mma-ranks/womens-pound-for-pound/",
    "womens-bantamweight": "/mma-ranks/womens-bantamweight/",
    "womens-flyweight": "/mma-ranks/womens-flyweight/",
    "womens-strawweight": "/mma-ranks/womens-strawweight/",
}


def _cache_path(cache_dir: Path, division: str) -> Path:
    safe = re.sub(r"[^a-z0-9_-]+", "_", division.lower())
    return cache_dir / f"{safe}.html"


def fetch_division_html(division: str, cache_dir: Path, refresh: bool = False, sleep_seconds: float = 1.0) -> str:
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = _cache_path(cache_dir, division)
    if path.exists() and not refresh:
        return path.read_text(encoding="utf-8")

    if division not in DIVISION_URLS:
        raise KeyError(f"unknown FightMatrix division: {division}")

    url = urljoin(BASE_URL, DIVISION_URLS[division])
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    response.raise_for_status()
    path.write_text(response.text, encoding="utf-8")
    if sleep_seconds > 0:
        time.sleep(sleep_seconds)
    return response.text


def _parse_name_age(text: str) -> tuple[str, int | None]:
    text = " ".join(text.split())
    match = re.match(r"^(?P<name>.+?)\s+\((?P<age>\d+)\)$", text)
    if not match:
        return text, None
    return match.group("name").strip(), int(match.group("age"))


def parse_rankings_html(html: str, division: str) -> pd.DataFrame:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one("table.tblRank")
    if table is None:
        return pd.DataFrame(columns=[
            "division", "rank", "fighter", "age", "record", "points", "profile_url",
            "last_fight_text", "next_fight_text",
        ])

    rows = []
    for tr in table.select("tr"):
        cells = [td.get_text(" ", strip=True) for td in tr.select("td")]
        if len(cells) < 4:
            continue
        rank_text = cells[0]
        if not re.match(r"^\d+$", rank_text):
            continue

        link = tr.select_one('a[href*="fighter-profile"]')
        fighter_cell = cells[3] if len(cells) >= 6 else cells[1]
        record_cell = cells[4] if len(cells) >= 6 else cells[2]
        points_cell = cells[5] if len(cells) >= 6 else cells[3]
        last_cell = cells[6] if len(cells) >= 7 else None
        next_cell = cells[7] if len(cells) >= 8 else None
        fighter_text = link.get_text(" ", strip=True) if link else fighter_cell
        fighter, age = _parse_name_age(fighter_text)
        profile_url = urljoin(BASE_URL, link.get("href")) if link else None
        full_text = tr.get_text(" ", strip=True)

        last_fight = None
        next_fight = None
        if last_cell:
            last_fight = last_cell.replace("Last Fight:", "").strip()
        elif "Last Fight:" in full_text:
            last_fight = full_text.split("Last Fight:", 1)[1].split("Next Fight:", 1)[0].strip()
        if next_cell:
            next_fight = next_cell.replace("Next Fight:", "").strip()
        elif "Next Fight:" in full_text:
            next_fight = full_text.split("Next Fight:", 1)[1].strip()

        rows.append({
            "division": division,
            "rank": int(rank_text),
            "fighter": fighter,
            "age": age,
            "record": record_cell,
            "points": pd.to_numeric(points_cell, errors="coerce"),
            "profile_url": profile_url,
            "last_fight_text": last_fight,
            "next_fight_text": next_fight,
        })
    return pd.DataFrame(rows)


def build_snapshot(
    snapshot_dir: Path,
    cache_dir: Path,
    divisions: list[str] | None = None,
    refresh: bool = False,
    sleep_seconds: float = 1.0,
) -> dict:
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    divisions = divisions or list(DIVISION_URLS)

    frames = []
    fetched = []
    for division in divisions:
        html = fetch_division_html(division, cache_dir=cache_dir, refresh=refresh, sleep_seconds=sleep_seconds)
        parsed = parse_rankings_html(html, division)
        frames.append(parsed)
        fetched.append({"division": division, "rows": int(len(parsed)), "cache": str(_cache_path(cache_dir, division))})

    rankings = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    rankings.to_parquet(snapshot_dir / "fightmatrix_rankings.parquet", index=False)
    summary = {
        "source": BASE_URL,
        "rows": int(len(rankings)),
        "divisions": fetched,
        "output": str((snapshot_dir / "fightmatrix_rankings.parquet").relative_to(PROJECT_ROOT)),
    }
    (snapshot_dir / "fightmatrix_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch FightMatrix current ranking pages into a snapshot.")
    parser.add_argument("--snapshot-dir", required=True, help="data/snapshots/<date>")
    parser.add_argument("--cache-dir", default="data/external/fightmatrix/html", help="Project-local HTML cache.")
    parser.add_argument("--division", action="append", choices=sorted(DIVISION_URLS), help="Division key; repeatable.")
    parser.add_argument("--refresh", action="store_true", help="Re-fetch HTML instead of using cache.")
    parser.add_argument("--sleep-seconds", type=float, default=1.0, help="Delay between FightMatrix requests.")
    args = parser.parse_args()

    summary = build_snapshot(
        snapshot_dir=Path(args.snapshot_dir).resolve(),
        cache_dir=Path(args.cache_dir).resolve(),
        divisions=args.division,
        refresh=args.refresh,
        sleep_seconds=args.sleep_seconds,
    )
    print(f"[fightmatrix] rows={summary['rows']:,} output={summary['output']}")
    for div in summary["divisions"]:
        print(f"[fightmatrix] {div['division']}: rows={div['rows']}")


if __name__ == "__main__":
    main()
