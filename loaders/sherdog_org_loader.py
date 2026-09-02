"""Roster-complete cross-org bout ingestion, crawled by *event* not by fighter.

``sherdog_loader`` walks outward from fighters we already rate, so its coverage
is shaped like the UFC roster: Cro Cop, Askren and Jacare come back empty while
Fedor comes back rich. That raggedness is what produced confident-looking
placements for some legends and silence for others.

This module inverts the crawl. For each major promotion we enumerate its
*events* and parse every bout on every card, so a fighter who never entered the
UFC is ingested on the same footing as one who did:

  organization page -> event pages -> every bout, with weight class,
  method, round, time, title flag and both Sherdog fighter ids.

Sherdog's organization page caps its event table at 100 rows, which is complete
for every major except Bellator. We close the gap by BFS: fighters seen in a
target-org bout have their own pages read for *earlier* target-org events, which
are then parsed like any other. The loop runs to fixpoint, so coverage is a
property of the bout graph rather than of a seed list.

Identity comes from the Sherdog numeric fighter id, not from name matching.
All HTML is cached in the shared page store under ``data/external/sherdog/`` and
never redistributed.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

# One host, one identity, one politeness floor. Both Sherdog readers write into
# the same cache directory, so a second user agent and a shorter delay here were
# drift, not a second policy.
from loaders.page_cache import PageCache, open_cache
from loaders.sherdog_loader import (  # noqa: F401  (_session is re-exported)
    BASE,
    DEFAULT_CACHE_DIR,
    POLITE_DELAY_SECONDS,
    _session,
)


@dataclass(frozen=True)
class Org:
    label: str
    slug: str
    org_id: int


# The majors: promotions whose history materially changes who the engine can
# rate. Deliberately not a long tail -- completeness per promotion beats breadth
# across 900 organization labels.
MAJOR_ORGS: tuple[Org, ...] = (
    Org("PRIDE", "Pride-Fighting-Championships-3", 3),
    Org("WEC", "World-Extreme-Cagefighting-48", 48),
    Org("Strikeforce", "Strikeforce-716", 716),
    Org("Affliction", "Affliction-1459", 1459),
    Org("Bellator", "Bellator-MMA-1960", 1960),
    Org("RIZIN", "Rizin-Fighting-Federation-10333", 10333),
)

ORG_BY_ID = {o.org_id: o for o in MAJOR_ORGS}

# Cheap prefilter before spending a request confirming an event's org link.
#
# Matches the promotion name ANYWHERE in the slug, not just at the front. An
# earlier prefix-anchored version silently lost four years of Bellator: the
# 2009-2012 events are slugged ``/events/BFC-Bellator-Fighting-Championships-1``
# from the promotion's pre-rebrand name, so they never matched, and the crawl
# converged looking complete at 234 events starting in 2013. The org id is the
# same 1960 throughout -- only the slug changed -- so nothing downstream caught
# it. A prefilter that decides what is worth fetching is a completeness risk,
# and this one has to stay loose; the event page's org link is what actually
# rejects a false positive, at the cost of one request.
SLUG_HINTS = re.compile(
    r"(pride|wec|world-extreme|strikeforce|affliction|bellator|bfc|rizin)",
    re.IGNORECASE,
)

_EVENT_ID_RE = re.compile(r"^/events/(.+)-(\d+)$")
_FIGHTER_ID_RE = re.compile(r"^/fighter/(.+)-(\d+)$")
_ORG_HREF_RE = re.compile(r"^/organizations/.+-(\d+)$")
_TIME_RE = re.compile(r"^(\d+):(\d{2})$")


# ---------------------------------------------------------------------------
# Fetch + cache


class FetchFailed(RuntimeError):
    """A page could not be retrieved after retries.

    Distinct from a 404: the page may well exist. Callers running a multi-hour
    crawl should record it and carry on rather than discarding hours of work
    because one request was reset -- this network resets connections
    intermittently, and the same URL usually succeeds on the next pass.
    """


def fetch(session, path: str, cache_dir: Path | PageCache, kind: str, key: str,
          *, refresh: bool = False) -> str | None:
    """Return page HTML, from the store when present. ``None`` on a hard 404."""
    cache = open_cache(cache_dir)
    if not refresh:
        held = cache.get(kind, key)
        if held is not None:
            return held
    url = path if path.startswith("http") else BASE + path
    for attempt in range(4):
        try:
            r = session.get(url, timeout=30)
        except Exception:
            time.sleep(2 ** attempt)
            continue
        if r.status_code == 404:
            return None
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(3 * (attempt + 1))
            continue
        r.raise_for_status()
        cache.put(kind, key, r.text)
        time.sleep(POLITE_DELAY_SECONDS)
        return r.text
    raise FetchFailed(url)


# ---------------------------------------------------------------------------
# Parsing


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


def event_key(href: str) -> str | None:
    m = _EVENT_ID_RE.match(href.split("?")[0])
    return m.group(2) if m else None


def fighter_key(href: str) -> str | None:
    m = _FIGHTER_ID_RE.match(href.split("?")[0])
    return m.group(2) if m else None


def parse_event_hrefs(html: str) -> list[str]:
    """Distinct event hrefs on an organization or fighter page, in page order."""
    s = _soup(html)
    out, seen = [], set()
    for a in s.find_all("a", href=True):
        href = a["href"].split("?")[0]
        if href.startswith("/events/") and href not in seen:
            seen.add(href)
            out.append(href)
    return out


def _seconds(text: str) -> int | None:
    m = _TIME_RE.match((text or "").strip())
    if not m:
        return None
    return int(m.group(1)) * 60 + int(m.group(2))


def _clean(node) -> str:
    if node is None:
        return ""
    return re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()


def parse_event(html: str, href: str) -> tuple[dict | None, list[dict]]:
    """Return (event metadata, bout rows) for one Sherdog event page.

    The event page's own ``/organizations/`` link is the authority on which
    promotion staged it; slug text is only ever a prefilter.
    """
    s = _soup(html)
    detail = s.select_one("div.event_detail")
    if detail is None:
        return None, []

    org_id = None
    for a in s.find_all("a", href=True):
        m = _ORG_HREF_RE.match(a["href"].split("?")[0])
        if m and int(m.group(1)) in ORG_BY_ID:
            org_id = int(m.group(1))
            break
    if org_id is None:
        return None, []

    meta_date = s.find("meta", itemprop="startDate")
    date = (meta_date.get("content") or "")[:10] if meta_date else None
    h1 = s.find("h1")
    named = h1.find("span", itemprop="name") if h1 else None
    name = _clean(named) if named else _clean(h1)
    loc = detail.select_one("span[itemprop=location]")
    event = {
        "event_href": href,
        "event_id": event_key(href),
        "event_name": name,
        "event_date": date,
        "event_location": _clean(loc) or None,
        "org_id": org_id,
        "org": ORG_BY_ID[org_id].label,
    }

    bouts: list[dict] = []
    card = s.find("div", class_="fight_card")
    if card is not None:
        bouts.append(_parse_main_event(card, s, event))
    for table in s.find_all("table", class_="new_table"):
        if "result" not in (table.get("class") or []):
            continue
        for tr in table.find_all("tr")[1:]:
            bouts.append(_parse_result_row(tr, event))
    return event, [b for b in bouts if b]


def _fighter_side(div) -> dict:
    a = div.find("a", href=_FIGHTER_ID_RE) if div else None
    res = div.find("span", class_="final_result") if div else None
    return {
        "href": a["href"] if a else None,
        "id": fighter_key(a["href"]) if a else None,
        "name": _clean(div.find("span", itemprop="name")) if div else "",
        "outcome": (_clean(res).lower() or None) if res else None,
    }


def _parse_main_event(card, s, event: dict) -> dict | None:
    left = _fighter_side(card.find("div", class_="fighter left_side"))
    right = _fighter_side(card.find("div", class_="fighter right_side"))
    if not left.get("id") or not right.get("id"):
        return None
    versus = card.find("div", class_="versus")

    resume: dict[str, str] = {}
    tbl = s.find("table", class_="fight_card_resume")
    if tbl is not None:
        for td in tbl.find_all("td"):
            em = td.find("em")
            if em is None:
                continue
            label = _clean(em).lower()
            value = _clean(td)
            if value.lower().startswith(label):
                value = value[len(label):].strip()
            resume[label] = value

    return _bout_row(
        event, left, right,
        match_order=resume.get("match"),
        weight_class=_clean(versus.find("span", class_="weight_class")) if versus else "",
        method=resume.get("method", ""),
        referee=resume.get("referee") or None,
        end_round=resume.get("round"),
        end_time=resume.get("time"),
        is_title=bool(versus and versus.find("span", class_="title_fight")),
        is_main=True,
    )


def _parse_result_row(tr, event: dict) -> dict | None:
    tds = tr.find_all("td")
    if len(tds) < 7:
        return None
    lists = tr.find_all("div", class_="fighter_list")
    if len(lists) < 2:
        return None
    left, right = _fighter_side(lists[0]), _fighter_side(lists[1])
    if not left.get("id") or not right.get("id"):
        return None

    winby = tds[4]
    bold = winby.find("b")
    method = _clean(bold) if bold else _clean(winby)
    ref = winby.find("a", href=re.compile(r"^/referee/"))
    return _bout_row(
        event, left, right,
        match_order=_clean(tds[0]),
        weight_class=_clean(tds[2].find("span", class_="weight_class")),
        method=method,
        referee=_clean(ref) if ref else None,
        end_round=_clean(tds[5]),
        end_time=_clean(tds[6]),
        is_title=False,
        is_main=False,
    )


def _int_or_none(value) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _bout_row(event, left, right, *, match_order, weight_class, method, referee,
              end_round, end_time, is_title, is_main) -> dict:
    return {
        **{k: event[k] for k in ("event_href", "event_id", "event_name",
                                 "event_date", "event_location", "org", "org_id")},
        "match_order": _int_or_none(match_order),
        "fighter_a_id": left["id"], "fighter_a": left["name"], "fighter_a_href": left["href"],
        "fighter_b_id": right["id"], "fighter_b": right["name"], "fighter_b_href": right["href"],
        "fighter_a_outcome": left["outcome"], "fighter_b_outcome": right["outcome"],
        "weight_class": weight_class or None,
        "method_raw": method or None,
        "referee": referee,
        "end_round": _int_or_none(end_round),
        "end_time_seconds": _seconds(end_time),
        "is_title_fight": bool(is_title),
        "is_main_event": bool(is_main),
    }


# ---------------------------------------------------------------------------
# Tier 2: whole careers for fighters already in the graph


_RESULTS = {"win", "loss", "draw", "nc", "no contest"}
_FIGHTER_DATE_RE = re.compile(r"([A-Z][a-z]{2})\s*/\s*(\d{1,2})\s*/\s*(\d{4})")


def parse_fighter_career(html: str, fighter_id: str) -> list[dict]:
    """Every bout on a fighter's record page, opponent identified by Sherdog id.

    Enumerating six promotions by event is roster-complete *within* those six and
    silently truncates everyone whose career ran wider: it takes Fedor's PRIDE
    and Strikeforce years and drops RINGS, which is where he was built. Rating a
    fighter on a subset of their record is the same censoring bias that made the
    old fighter-seeded cache unusable, only applied along a different axis.

    So once a fighter is in the graph at all, their whole record comes in. There
    is no organization weight for a promotion label to feed, which is why a bout
    is usable here without knowing which promotion staged it -- ``event_href``
    identifies the card, and the promotion is a reporting question, not a
    modelling one.
    """
    if not html:
        return []
    soup = _soup(html)
    table = None
    for candidate in soup.find_all("table"):
        first = candidate.find("tr")
        head = [c.get_text(strip=True) for c in first.find_all(["th", "td"])] if first else []
        if "Result" in head and any("Method" in h for h in head):
            table = candidate
            break
    if table is None:
        return []

    rows = []
    for tr in table.find_all("tr")[1:]:
        tds = tr.find_all("td")
        if len(tds) < 6:
            continue
        result = tds[0].get_text(strip=True).lower()
        if result not in _RESULTS:
            continue
        opp_link = tds[1].find("a", href=_FIGHTER_ID_RE)
        opponent_id = fighter_key(opp_link["href"]) if opp_link else None
        if not opponent_id or opponent_id == fighter_id:
            continue

        event_link = tds[2].find("a", href=re.compile(r"^/events/"))
        event_href = event_link["href"].split("?")[0] if event_link else None
        text = tds[2].get_text(" ", strip=True)
        dm = _FIGHTER_DATE_RE.search(text)
        date = None
        if dm:
            try:
                date = str(pd.Timestamp(f"{dm.group(1)} {int(dm.group(2))} {dm.group(3)}").date())
            except ValueError:
                date = None

        method = re.sub(r"\s*VIEW PLAY-BY-PLAY\s*", "",
                        tds[3].get_text(" ", strip=True), flags=re.IGNORECASE).strip()
        ref = tds[3].find("a", href=re.compile(r"^/referee/"))
        if ref is not None:
            method = method.replace(_clean(ref), "").strip()

        outcome = "nc" if result.startswith("no") else result
        rows.append({
            "event_href": event_href,
            "event_id": event_key(event_href) if event_href else None,
            "event_name": _clean(event_link) if event_link else None,
            "event_date": date,
            "event_location": None,
            "org": None,
            "org_id": None,
            "match_order": None,
            "fighter_a_id": fighter_id,
            "fighter_a": None,
            "fighter_a_href": f"/fighter/x-{fighter_id}",
            "fighter_b_id": opponent_id,
            "fighter_b": _clean(tds[1]) or None,
            "fighter_b_href": opp_link["href"],
            "fighter_a_outcome": outcome,
            "fighter_b_outcome": {"win": "loss", "loss": "win"}.get(outcome, outcome),
            "weight_class": None,
            "method_raw": method or None,
            "referee": _clean(ref) if ref is not None else None,
            "end_round": _int_or_none(tds[4].get_text(strip=True)),
            "end_time_seconds": _seconds(tds[5].get_text(strip=True)),
            "is_title_fight": False,
            "is_main_event": False,
            "source": "fighter_page",
        })
    return rows


def _pair_key(a: object, b: object) -> tuple:
    return tuple(sorted((str(a), str(b))))


def merge_careers(event_bouts: pd.DataFrame, career_bouts: pd.DataFrame) -> pd.DataFrame:
    """Union the two sources, preferring the event card where they overlap.

    The event page is the better record -- it carries weight class, the title
    flag and card order -- so a fighter-page row is kept only for a bout no card
    supplied. Dedupe is on (event, unordered fighter pair), because the two
    sources disagree about which fighter is listed first.
    """
    if event_bouts.empty:
        return career_bouts.reset_index(drop=True)
    if career_bouts.empty:
        return event_bouts.reset_index(drop=True)

    known = {
        (r.event_id, _pair_key(r.fighter_a_id, r.fighter_b_id))
        for r in event_bouts.itertuples()
    }
    keep = [
        r.Index for r in career_bouts.itertuples()
        if (r.event_id, _pair_key(r.fighter_a_id, r.fighter_b_id)) not in known
    ]
    extra = career_bouts.loc[keep]
    # A bout appears on both fighters' pages; keep one copy.
    extra = extra.assign(
        _pair=[_pair_key(a, b) for a, b in zip(extra["fighter_a_id"], extra["fighter_b_id"])]
    ).drop_duplicates(subset=["event_id", "_pair"]).drop(columns="_pair")
    return pd.concat([event_bouts, extra], ignore_index=True)


def crawl_careers(
    fighter_ids: list[str],
    *,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    session=None,
    progress: bool = True,
) -> pd.DataFrame:
    """Whole-record ingestion for fighters already in the graph.

    Their *opponents* are added as nodes but are not themselves expanded: one
    bout against an unknown is evidence about the fighter we rate, and the
    unknown abstains from the board on connectivity anyway.
    """
    session = session or _session()
    rows: list[dict] = []
    unreachable: list[str] = []
    for i, fid in enumerate(fighter_ids, 1):
        try:
            html = fetch(session, f"/fighter/x-{fid}", cache_dir, "fighters", fid)
        except FetchFailed as exc:
            unreachable.append(str(exc))
            continue
        if html is None:
            continue
        rows.extend(parse_fighter_career(html, fid))
        if progress and i % 250 == 0:
            print(f"    careers {i}/{len(fighter_ids)}  bouts={len(rows)}", flush=True)
    out = pd.DataFrame(rows)
    out.attrs["unreachable"] = unreachable
    return out


# ---------------------------------------------------------------------------
# Crawl to fixpoint


# Sherdog's organization page renders at most this many events. An org whose
# listing lands exactly on the cap is presumed truncated, and only those orgs
# pay for fighter-page expansion.
ORG_LISTING_CAP = 100


def crawl(
    orgs: tuple[Org, ...] = MAJOR_ORGS,
    *,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    max_rounds: int = 6,
    progress: bool = True,
    session=None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Crawl every major promotion to fixpoint.

    Returns ``(bouts, events)``. Re-running is cheap: every page is cached, so
    only genuinely new events and fighters cost a request -- which is also why a
    page that will not load is skipped and recorded rather than raised: a reset
    connection three hours in must not discard three hours of crawling, and the
    next run picks the page up from where the cache left off.
    """
    session = session or _session()
    unreachable: list[str] = []

    def _get(path: str, kind: str, key: str) -> str | None:
        try:
            return fetch(session, path, cache_dir, kind, key)
        except FetchFailed as exc:
            unreachable.append(str(exc))
            if progress:
                print(f"    [skip] unreachable: {exc}", flush=True)
            return None

    events_seen: dict[str, dict] = {}
    bouts: list[dict] = []
    fighters_seen: set[str] = set()
    event_frontier: list[str] = []
    rejected: set[str] = set()
    truncated: set[int] = set()

    for org in orgs:
        html = _get(f"/organizations/{org.slug}", "orgs", str(org.org_id))
        if html is None:
            continue
        hrefs = parse_event_hrefs(html)
        event_frontier.extend(hrefs)
        capped = len(hrefs) >= ORG_LISTING_CAP
        if capped:
            truncated.add(org.org_id)
        if progress:
            print(f"  seed {org.label:<12} {len(hrefs):>4} events listed"
                  f"{'  [TRUNCATED -> will expand]' if capped else ''}", flush=True)

    for rnd in range(1, max_rounds + 1):
        new_events = [h for h in dict.fromkeys(event_frontier)
                      if h not in events_seen and h not in rejected]
        event_frontier = []
        if not new_events:
            break
        if progress:
            print(f"round {rnd}: {len(new_events)} candidate events", flush=True)

        fighter_frontier: set[str] = set()
        for i, href in enumerate(new_events, 1):
            key = event_key(href)
            if key is None:
                rejected.add(href)
                continue
            html = _get(href, "events", key)
            if html is None:
                rejected.add(href)
                continue
            event, rows = parse_event(html, href)
            if event is None:
                rejected.add(href)
                continue
            events_seen[href] = event
            bouts.extend(rows)
            if event["org_id"] in truncated:
                for r in rows:
                    for fid in (r["fighter_a_id"], r["fighter_b_id"]):
                        if fid and fid not in fighters_seen:
                            fighter_frontier.add(fid)
            if progress and i % 100 == 0:
                print(f"    events {i}/{len(new_events)}  bouts={len(bouts)}", flush=True)

        # Read each newly seen fighter's record for target-org events the
        # organization page never listed (Bellator pre-2019, mostly).
        if progress and fighter_frontier:
            print(f"round {rnd}: {len(fighter_frontier)} new fighters to expand", flush=True)
        for j, fid in enumerate(sorted(fighter_frontier), 1):
            fighters_seen.add(fid)
            html = _get(f"/fighter/x-{fid}", "fighters", fid)
            if html is None:
                continue
            for href in parse_event_hrefs(html):
                if href in events_seen or href in rejected:
                    continue
                if SLUG_HINTS.search(href):
                    event_frontier.append(href)
            if progress and j % 200 == 0:
                print(f"    fighters {j}/{len(fighter_frontier)}", flush=True)

    if unreachable and progress:
        print(f"[warn] {len(unreachable)} pages unreachable this pass; "
              f"rerun to pick them up", flush=True)
    bouts_df, events_df = _frames(bouts, list(events_seen.values()))
    events_df.attrs["unreachable"] = unreachable
    return bouts_df, events_df


def _frames(bouts: list[dict], events: list[dict]) -> tuple[pd.DataFrame, pd.DataFrame]:
    bouts_df = pd.DataFrame(bouts)
    if not bouts_df.empty:
        bouts_df = bouts_df.drop_duplicates(
            subset=["event_id", "fighter_a_id", "fighter_b_id"]
        ).reset_index(drop=True)
    return bouts_df, pd.DataFrame(events)


def parse_cached_events(
    cache_dir: Path | PageCache = DEFAULT_CACHE_DIR,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Rebuild bouts and events from cached HTML, without touching the network.

    A crawl in progress is still a usable dataset for every promotion whose
    listing was already complete, so this exists to read what has landed rather
    than waiting on the one promotion that needs expansion.
    """
    bouts: list[dict] = []
    events: list[dict] = []
    for key, html in open_cache(cache_dir).items("events"):
        event, rows = parse_event(html, f"/events/x-{key}")
        if event is None:
            continue
        events.append(event)
        bouts.extend(rows)
    return _frames(bouts, events)
