"""Live UFCStats scraper that produces Greco-schema CSVs.

Why this exists: the Greco1899/scrape_ufc_stats GitHub mirror (the project's
historical source for the six ``ufc_*.csv`` files) stopped refreshing in
mid-2026, and ufcstats.com now gates every page behind a small client-side
SHA-256 proof-of-work ("Checking your browser...") that defeats a plain
``requests.get``. This module replicates that proof-of-work, then scrapes the
events newer than an existing raw bundle and appends them — preserving the
historical rows byte-for-byte — so ``refresh.py`` can rebuild the snapshot.

Pure functions (parsers, the PoW solver) do no network I/O at import time; the
network is only touched when ``make_session`` / ``scrape_new_events`` run.

CLI:
    python -m loaders.ufcstats_scrape \
        --old-raw data/raw/2026-05-13 --out-raw data/raw/2026-06-23
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import re
import time
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

BASE = "http://ufcstats.com"
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# Greco CSV file names and their exact column order.
GRECO_FILES = {
    "events": "ufc_event_details.csv",
    "details": "ufc_fight_details.csv",
    "results": "ufc_fight_results.csv",
    "stats": "ufc_fight_stats.csv",
    "fighters": "ufc_fighter_details.csv",
    "tott": "ufc_fighter_tott.csv",
}
EVENT_COLS = ["EVENT", "URL", "DATE", "LOCATION"]
DETAIL_COLS = ["EVENT", "BOUT", "URL"]
RESULT_COLS = ["EVENT", "BOUT", "OUTCOME", "WEIGHTCLASS", "METHOD", "ROUND", "TIME",
               "TIME FORMAT", "REFEREE", "DETAILS", "URL"]
STAT_COLS = ["EVENT", "BOUT", "ROUND", "FIGHTER", "KD", "SIG.STR.", "SIG.STR. %",
             "TOTAL STR.", "TD", "TD %", "SUB.ATT", "REV.", "CTRL", "HEAD", "BODY",
             "LEG", "DISTANCE", "CLINCH", "GROUND"]
FDET_COLS = ["FIRST", "LAST", "NICKNAME", "URL"]
TOTT_COLS = ["FIGHTER", "HEIGHT", "WEIGHT", "REACH", "STANCE", "DOB", "URL"]

_NONCE_RE = re.compile(r'nonce="([0-9a-fA-F]+)"')
_TARGET_RE = re.compile(r"target=new Array\((\d+)\+1\)\.join\('0'\)")


# ---------------------------------------------------------------------------
# Proof-of-work wall

def is_challenge(text: str) -> bool:
    return "Checking your browser" in text or "/__c" in text


def solve_pow(nonce: str, zeros: int) -> int:
    """Smallest n where sha256('<nonce>:<n>') starts with `zeros` hex zeros."""
    target = "0" * zeros
    n = 0
    while hashlib.sha256(f"{nonce}:{n}".encode()).hexdigest()[:zeros] != target:
        n += 1
    return n


def _clear_challenge(session: requests.Session, text: str) -> None:
    nonce = _NONCE_RE.search(text).group(1)
    zeros = int(_TARGET_RE.search(text).group(1))
    n = solve_pow(nonce, zeros)
    session.post(
        f"{BASE}/__c",
        data={"nonce": nonce, "n": n},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    resp = session.get(f"{BASE}/statistics/events/completed", timeout=60)
    if is_challenge(resp.text):
        _clear_challenge(session, resp.text)
    return session


def get(session: requests.Session, url: str, *, tries: int = 4, pause: float = 0.6) -> requests.Response:
    last = None
    for _ in range(tries):
        last = session.get(url, timeout=60)
        if not is_challenge(last.text):
            return last
        _clear_challenge(session, last.text)
        time.sleep(pause)
    return last


# ---------------------------------------------------------------------------
# Pure parsers

def _txt(el) -> str:
    return " ".join(el.get_text(" ", strip=True).split()) if el else ""


def _cell_pair(td) -> tuple[str, str]:
    """A UFCStats stats cell holds two <p> (fighter A / fighter B)."""
    ps = td.select("p")
    if len(ps) >= 2:
        return ps[0].get_text(strip=True), ps[1].get_text(strip=True)
    if len(ps) == 1:
        return ps[0].get_text(strip=True), ""
    return td.get_text(strip=True), ""


def parse_event_page(html: str) -> tuple[dict, list[str]]:
    soup = BeautifulSoup(html, "lxml")
    meta = {"EVENT": _txt(soup.select_one("h2.b-content__title")), "DATE": "", "LOCATION": ""}
    for li in soup.select("li.b-list__box-list-item"):
        t = _txt(li)
        if t.lower().startswith("date:"):
            meta["DATE"] = t.split(":", 1)[1].strip()
        elif t.lower().startswith("location:"):
            meta["LOCATION"] = t.split(":", 1)[1].strip()
    links = [tr.get("data-link") for tr in soup.select("tr.b-fight-details__table-row[data-link]")
             if tr.get("data-link") and "fight-details" in tr.get("data-link")]
    return meta, links


def parse_fight_page(html: str, event_name: str) -> dict | None:
    soup = BeautifulSoup(html, "lxml")
    persons = soup.select("div.b-fight-details__person")
    names, statuses, furls = [], [], []
    for p in persons:
        names.append(_txt(p.select_one("h3.b-fight-details__person-name")))
        statuses.append(_txt(p.select_one("i.b-fight-details__person-status")))
        a = p.select_one("h3.b-fight-details__person-name a")
        furls.append(a.get("href") if a else None)
    if len(names) != 2:
        return None
    fa, fb = names[0], names[1]
    bout = f"{fa} vs. {fb}"

    method = round_ = time_ = time_fmt = referee = ""
    first = soup.select_one("i.b-fight-details__text-item_first")
    if first and ":" in _txt(first):
        method = _txt(first).split(":", 1)[1].strip()
    for it in soup.select("i.b-fight-details__text-item"):
        t = _txt(it)
        if ":" not in t:
            continue
        label, _, value = t.partition(":")
        label, value = label.strip().lower(), value.strip()
        if label == "round":
            round_ = value
        elif label == "time":
            time_ = value
        elif label == "time format":
            time_fmt = value
        elif label == "referee":
            referee = value

    details = ""
    for p in soup.select("p.b-fight-details__text"):
        t = _txt(p)
        if t.lower().startswith("details:"):
            details = t.split(":", 1)[1].strip()
            break

    result = {
        "EVENT": event_name, "BOUT": bout, "OUTCOME": f"{statuses[0]}/{statuses[1]}",
        "WEIGHTCLASS": _txt(soup.select_one("i.b-fight-details__fight-title")),
        "METHOD": method, "ROUND": round_, "TIME": time_, "TIME FORMAT": time_fmt,
        "REFEREE": referee, "DETAILS": details,
    }

    tables = soup.select("table")
    totals_pr = tables[1] if len(tables) >= 2 else None
    sig_pr = tables[3] if len(tables) >= 4 else None
    t_rows = totals_pr.select("tbody tr") if totals_pr is not None else []
    s_rows = sig_pr.select("tbody tr") if sig_pr is not None else []
    stat_rows = []
    for ri in range(max(len(t_rows), len(s_rows))):
        tds_t = t_rows[ri].select("td") if ri < len(t_rows) else []
        tds_s = s_rows[ri].select("td") if ri < len(s_rows) else []

        def val(tds, idx):
            return _cell_pair(tds[idx]) if idx < len(tds) else ("", "")

        cols = {
            "KD": val(tds_t, 1), "SIG.STR.": val(tds_t, 2), "SIG.STR. %": val(tds_t, 3),
            "TOTAL STR.": val(tds_t, 4), "TD": val(tds_t, 5), "TD %": val(tds_t, 6),
            "SUB.ATT": val(tds_t, 7), "REV.": val(tds_t, 8), "CTRL": val(tds_t, 9),
            "HEAD": val(tds_s, 3), "BODY": val(tds_s, 4), "LEG": val(tds_s, 5),
            "DISTANCE": val(tds_s, 6), "CLINCH": val(tds_s, 7), "GROUND": val(tds_s, 8),
        }
        for fi, fighter in enumerate((fa, fb)):
            row = {"EVENT": event_name, "BOUT": bout, "ROUND": f"Round {ri + 1}", "FIGHTER": fighter}
            row.update({k: v[fi] for k, v in cols.items()})
            stat_rows.append(row)

    return {"result": result, "stats": stat_rows, "fighters": list(zip(names, furls))}


def parse_fighter_page(html: str) -> tuple[dict, dict]:
    soup = BeautifulSoup(html, "lxml")
    full = _txt(soup.select_one("span.b-content__title-highlight"))
    nick = _txt(soup.select_one("p.b-content__Nickname"))
    parts = full.split()
    vals = {"HEIGHT": "--", "WEIGHT": "--", "REACH": "--", "STANCE": "", "DOB": "--"}
    for li in soup.select("li.b-list__box-list-item"):
        t = _txt(li)
        if ":" not in t:
            continue
        label, _, value = t.partition(":")
        label = label.strip().upper()
        if label in vals:
            vals[label] = value.strip()
    fdet = {"FIRST": parts[0] if parts else "", "LAST": " ".join(parts[1:]), "NICKNAME": nick}
    tott = {"FIGHTER": full, **{k: vals[k] for k in ("HEIGHT", "WEIGHT", "REACH", "STANCE", "DOB")}}
    return fdet, tott


# ---------------------------------------------------------------------------
# Orchestration

def _read_old(old_raw: Path) -> dict[str, pd.DataFrame]:
    return {k: pd.read_csv(old_raw / fn, dtype=str, keep_default_na=False)
            for k, fn in GRECO_FILES.items()}


def _append(old_df: pd.DataFrame, new_rows: list[dict], cols: list[str],
            key: list[str]) -> pd.DataFrame:
    """Preserve every historical row; append only new rows with unseen keys."""
    new_df = pd.DataFrame(new_rows, columns=cols).drop_duplicates(subset=key, keep="first")
    if len(old_df) and len(new_df):
        old_keys = set(map(tuple, old_df[key].astype(str).values))
        mask = ~new_df[key].astype(str).apply(tuple, axis=1).isin(old_keys)
        new_df = new_df[mask]
    return pd.concat([old_df[cols], new_df], ignore_index=True)


def scrape_new_events(old_raw: Path, out_raw: Path, *, sleep: float = 0.3,
                      session: requests.Session | None = None) -> dict:
    """Scrape events newer than `old_raw` and write a full Greco bundle to `out_raw`."""
    session = session or make_session()
    old = _read_old(old_raw)
    existing_event_urls = set(old["events"]["URL"])
    existing_fighter_urls = set(old["fighters"]["URL"])
    max_date = pd.to_datetime(old["events"]["DATE"], format="%B %d, %Y",
                              errors="coerce").max().date()

    soup = BeautifulSoup(get(session, f"{BASE}/statistics/events/completed?page=all").text, "lxml")
    new_events = []
    for row in soup.select("tr.b-statistics__table-row"):
        a = row.select_one("a.b-link")
        d = row.select_one("span.b-statistics__date")
        if not (a and d):
            continue
        try:
            ed = dt.datetime.strptime(d.get_text(strip=True), "%B %d, %Y").date()
        except ValueError:
            continue
        if ed > max_date and a.get("href") not in existing_event_urls:
            new_events.append((ed, a.get_text(strip=True), a.get("href")))
    new_events.sort()

    ev_rows, det_rows, res_rows, stat_rows, fdet_rows, tott_rows = [], [], [], [], [], []
    seen_new_fighters: set[str] = set()
    for ed, name, ev_url in new_events:
        time.sleep(sleep)
        meta, links = parse_event_page(get(session, ev_url).text)
        meta["URL"] = ev_url
        ev_rows.append({k: meta.get(k, "") for k in EVENT_COLS})
        for fl in links:
            time.sleep(sleep)
            parsed = parse_fight_page(get(session, fl).text, meta["EVENT"])
            if not parsed:
                continue
            res = parsed["result"]
            res["URL"] = fl
            res_rows.append({k: res.get(k, "") for k in RESULT_COLS})
            det_rows.append({"EVENT": meta["EVENT"], "BOUT": res["BOUT"], "URL": fl})
            stat_rows.extend(parsed["stats"])
            for fname, furl in parsed["fighters"]:
                if not furl or furl in existing_fighter_urls or furl in seen_new_fighters:
                    continue
                seen_new_fighters.add(furl)
                time.sleep(sleep)
                fdet, tott = parse_fighter_page(get(session, furl).text)
                fdet["URL"] = furl
                tott["URL"] = furl
                fdet_rows.append({k: fdet.get(k, "") for k in FDET_COLS})
                tott_rows.append({k: tott.get(k, "") for k in TOTT_COLS})

    out_raw.mkdir(parents=True, exist_ok=True)
    bundle = {
        "ufc_event_details.csv": _append(old["events"], ev_rows, EVENT_COLS, ["URL"]),
        "ufc_fight_details.csv": _append(old["details"], det_rows, DETAIL_COLS, ["URL"]),
        "ufc_fight_results.csv": _append(old["results"], res_rows, RESULT_COLS, ["URL"]),
        "ufc_fight_stats.csv": _append(old["stats"], stat_rows, STAT_COLS,
                                       ["EVENT", "BOUT", "ROUND", "FIGHTER"]),
        "ufc_fighter_details.csv": _append(old["fighters"], fdet_rows, FDET_COLS, ["URL"]),
        "ufc_fighter_tott.csv": _append(old["tott"], tott_rows, TOTT_COLS, ["URL"]),
    }
    for fn, df in bundle.items():
        df.to_csv(out_raw / fn, index=False)

    return {
        "new_events": [name for _, name, _ in new_events],
        "events_total": len(bundle["ufc_event_details.csv"]),
        "results_added": len(res_rows),
        "stat_rows_added": len(stat_rows),
        "new_fighters": len(fdet_rows),
        "out_raw": str(out_raw),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old-raw", required=True, help="Existing raw bundle to extend.")
    parser.add_argument("--out-raw", required=True, help="Destination for the new bundle.")
    parser.add_argument("--sleep", type=float, default=0.3, help="Delay between requests.")
    args = parser.parse_args()
    summary = scrape_new_events(Path(args.old_raw), Path(args.out_raw), sleep=args.sleep)
    print(f"new events: {len(summary['new_events'])}")
    for name in summary["new_events"]:
        print(f"  + {name}")
    print(f"results added: {summary['results_added']}  stat rows: {summary['stat_rows_added']}  "
          f"new fighters: {summary['new_fighters']}")
    print(f"wrote -> {summary['out_raw']}")


if __name__ == "__main__":
    main()
