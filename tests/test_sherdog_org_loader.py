"""Event-driven cross-org ingestion: parsing, org authority, and crawl resilience."""
from __future__ import annotations

import pandas as pd
import pytest

from loaders import sherdog_org_loader as sol
from loaders.page_cache import open_cache

EVENT_HTML = """
<html><body>
<div class="event_detail">
  <h1><span itemprop="name">Pride 32 - The Real Deal</span></h1>
  <span itemprop="location">Thomas &amp; Mack Center, Las Vegas</span>
</div>
<meta itemprop="startDate" content="2006-10-21T00:00:00+00:00"/>
<a href="/organizations/Pride-Fighting-Championships-3">Pride</a>
<div class="fight_card">
  <div class="fighter left_side">
    <a href="/fighter/Fedor-Emelianenko-1500"></a>
    <h3><a href="/fighter/Fedor-Emelianenko-1500"><span itemprop="name">Fedor Emelianenko</span></a></h3>
    <span class="final_result win">win</span>
  </div>
  <div class="versus">
    <b>MAIN EVENT</b><span class="title_fight">TITLE FIGHT</span>
    <span class="weight_class">Heavyweight</span>
  </div>
  <div class="fighter right_side">
    <a href="/fighter/Mark-Coleman-136"></a>
    <h3><a href="/fighter/Mark-Coleman-136"><span itemprop="name">Mark Coleman</span></a></h3>
    <span class="final_result loss">loss</span>
  </div>
</div>
<table class="fight_card_resume"><tr>
  <td><em>Match</em><br/>8</td>
  <td><em>Method</em><br/>Submission (Armbar)</td>
  <td><em>Referee</em><br/><a href="/referee/Yuji-Shimada-25">Yuji Shimada</a></td>
  <td><em>Round</em><br/>2</td>
  <td><em>Time</em><br/>1:15</td>
</tr></table>
<table class="new_table result">
  <tr><th>Match</th><th></th><th>Fighters</th><th></th><th>Method</th><th>R</th><th>Time</th></tr>
  <tr>
    <td>7</td>
    <td><div class="fighter_list left"><div class="fighter_result_data">
      <a href="/fighter/Mauricio-Rua-5707"><span itemprop="name">Mauricio Rua</span></a>
      <span class="final_result win">win</span></div></div></td>
    <td class="text_center"><span class="weight_class">Light Heavyweight</span></td>
    <td><div class="fighter_list right"><div class="fighter_result_data">
      <a href="/fighter/Kevin-Randleman-162"><span itemprop="name">Kevin Randleman</span></a>
      <span class="final_result loss">loss</span></div></div></td>
    <td class="winby"><b>Submission (Kneebar)</b><a href="/referee/Daisuke-Noguchi-1450">Daisuke Noguchi</a></td>
    <td>1</td>
    <td>2:34</td>
  </tr>
</table>
</body></html>
"""


def test_event_parses_main_card_and_undercard():
    event, bouts = sol.parse_event(EVENT_HTML, "/events/Pride-32-The-Real-Deal-4088")
    assert event["org"] == "PRIDE"
    assert event["event_date"] == "2006-10-21"
    assert event["event_id"] == "4088"
    assert len(bouts) == 2

    main = bouts[0]
    assert main["is_main_event"] and main["is_title_fight"]
    assert (main["fighter_a_id"], main["fighter_b_id"]) == ("1500", "136")
    assert main["weight_class"] == "Heavyweight"
    assert main["end_round"] == 2
    assert main["end_time_seconds"] == 75

    under = bouts[1]
    assert not under["is_main_event"] and not under["is_title_fight"]
    assert under["fighter_a"] == "Mauricio Rua"
    assert under["method_raw"] == "Submission (Kneebar)"
    assert under["referee"] == "Daisuke Noguchi"
    assert under["end_time_seconds"] == 154


def test_the_org_link_not_the_slug_decides_the_promotion():
    """An org page lists sidebar events from other promotions; the link rejects them."""
    foreign = EVENT_HTML.replace(
        '<a href="/organizations/Pride-Fighting-Championships-3">Pride</a>',
        '<a href="/organizations/Some-Regional-99999">Regional</a>',
    )
    event, bouts = sol.parse_event(foreign, "/events/Pride-Looking-Slug-1")
    assert event is None and bouts == []

    event, bouts = sol.parse_event(
        foreign,
        "/events/Pride-Looking-Slug-1",
        allow_unlisted_organization=True,
    )
    assert event["org_id"] == 99999
    assert event["org"] == "Regional"
    assert len(bouts) == 2


def test_a_reset_connection_skips_the_page_instead_of_killing_the_crawl(monkeypatch, tmp_path):
    """One unreachable page must not discard hours of completed crawling."""
    org_html = '<a href="/events/Pride-32-The-Real-Deal-4088">e</a>'

    def fake_fetch(session, path, cache_dir, kind, key, *, refresh=False):
        if kind == "orgs":
            return org_html if key == "3" else ""
        if kind == "events":
            raise sol.FetchFailed(path)
        return ""

    monkeypatch.setattr(sol, "fetch", fake_fetch)
    monkeypatch.setattr(sol, "_session", lambda: object())

    bouts, events = sol.crawl(
        orgs=(sol.MAJOR_ORGS[0],), cache_dir=tmp_path, progress=False
    )
    assert bouts.empty and events.empty
    assert events.attrs["unreachable"] == ["/events/Pride-32-The-Real-Deal-4088"]


def test_fetch_returns_none_on_404_and_raises_on_repeated_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(sol.time, "sleep", lambda _s: None)  # skip the real backoff

    class Resp:
        def __init__(self, code):
            self.status_code = code
            self.text = "x"

        def raise_for_status(self):
            raise AssertionError("should not be reached")

    class Session:
        def __init__(self, code):
            self.code = code

        def get(self, url, timeout):
            return Resp(self.code)

    assert sol.fetch(Session(404), "/x", tmp_path, "events", "1") is None
    with pytest.raises(sol.FetchFailed):
        sol.fetch(Session(503), "/x", tmp_path, "events", "2")


def test_cached_pages_rebuild_without_network(tmp_path):
    open_cache(tmp_path).put("events", "4088", EVENT_HTML)

    bouts, events = sol.parse_cached_events(tmp_path)
    assert len(events) == 1
    assert len(bouts) == 2
    assert set(bouts["org"]) == {"PRIDE"}


def test_duplicate_bouts_across_events_are_deduped():
    bouts, _ = sol._frames(
        [{"event_id": "1", "fighter_a_id": "a", "fighter_b_id": "b", "x": 1},
         {"event_id": "1", "fighter_a_id": "a", "fighter_b_id": "b", "x": 2}],
        [{"event_href": "/events/x-1"}],
    )
    assert len(bouts) == 1
    assert isinstance(bouts, pd.DataFrame)


CAREER_HTML = """
<html><body><table>
<tr><th>Result</th><th>Fighter</th><th>Event</th><th>Method/Referee</th><th>R</th><th>Time</th></tr>
<tr>
  <td>win</td>
  <td><a href="/fighter/Ricardo-Arona-284">Ricardo Arona</a></td>
  <td><a href="/events/Rings-King-of-Kings-2000-Block-B-91">Rings - King of Kings 2000 Block B</a> Dec / 22 / 2000</td>
  <td>Decision (Unanimous) <a href="/referee/X-1">Some Ref</a> VIEW PLAY-BY-PLAY</td>
  <td>2</td><td>5:00</td>
</tr>
<tr>
  <td>loss</td>
  <td><a href="/fighter/Tsuyoshi-Kosaka-137">Tsuyoshi Kosaka</a></td>
  <td><a href="/events/Rings-King-of-Kings-2000-Block-B-91">Rings - King of Kings 2000 Block B</a> Dec / 22 / 2000</td>
  <td>TKO (Cut)</td>
  <td>1</td><td>1:17</td>
</tr>
<tr><td>NR</td><td>Someone</td><td>Upcoming</td><td></td><td></td><td></td></tr>
</table></body></html>
"""


def test_fighter_career_keeps_opponent_ids_and_dates():
    rows = sol.parse_fighter_career(CAREER_HTML, "1500")
    assert len(rows) == 2  # the scheduled "NR" row is not a result
    win, loss = rows
    assert win["fighter_a_id"] == "1500" and win["fighter_b_id"] == "284"
    assert win["fighter_a_outcome"] == "win" and win["fighter_b_outcome"] == "loss"
    assert win["event_date"] == "2000-12-22"
    assert win["event_id"] == "91"
    assert win["end_time_seconds"] == 300
    assert "VIEW PLAY-BY-PLAY" not in win["method_raw"]
    assert "Some Ref" not in win["method_raw"]
    assert win["referee"] == "Some Ref"
    assert loss["fighter_a_outcome"] == "loss" and loss["fighter_b_outcome"] == "win"
    # No promotion label is needed: there is no org weight for one to feed.
    assert win["org"] is None and win["source"] == "fighter_page"


def test_merge_prefers_the_event_card_and_dedupes_the_mirror_row():
    """The same bout appears on both fighters' pages and on the card."""
    event = pd.DataFrame([{
        "event_id": "91", "fighter_a_id": "284", "fighter_b_id": "1500",
        "weight_class": "Heavyweight", "source": "event",
    }])
    careers = pd.DataFrame([
        {"event_id": "91", "fighter_a_id": "1500", "fighter_b_id": "284",
         "weight_class": None, "source": "fighter_page"},
        {"event_id": "91", "fighter_a_id": "284", "fighter_b_id": "1500",
         "weight_class": None, "source": "fighter_page"},
        {"event_id": "77", "fighter_a_id": "1500", "fighter_b_id": "999",
         "weight_class": None, "source": "fighter_page"},
        {"event_id": "77", "fighter_a_id": "999", "fighter_b_id": "1500",
         "weight_class": None, "source": "fighter_page"},
    ])
    merged = sol.merge_careers(event, careers)
    assert len(merged) == 2
    covered = merged[merged["event_id"].eq("91")].iloc[0]
    assert covered["source"] == "event" and covered["weight_class"] == "Heavyweight"
    assert merged["event_id"].tolist().count("77") == 1


def test_the_slug_prefilter_matches_a_promotions_former_name():
    """Bellator's 2009-2012 events are slugged from its pre-rebrand name.

    A prefix-anchored prefilter lost all of them and the crawl still converged,
    looking complete from 2013. The org id never changed, so nothing downstream
    could have caught it.
    """
    assert sol.SLUG_HINTS.search("/events/BFC-Bellator-Fighting-Championships-1-9708")
    assert sol.SLUG_HINTS.search("/events/Bellator-290-Bader-vs-Fedor-2-95557")
    assert sol.SLUG_HINTS.search("/events/Pride-32-The-Real-Deal-4088")
    assert sol.SLUG_HINTS.search("/events/World-Extreme-Cagefighting-10-1234")
    assert not sol.SLUG_HINTS.search("/events/UFC-330-Makhachev-vs-Garry-112557")
