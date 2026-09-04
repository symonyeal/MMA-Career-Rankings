"""Exact event details replace inferred fields without widening the corpus."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

import build_sherdog_event_details as details


# Ultimate Japan 1 staged Sakuraba against Silveira twice: a quarter-final
# stopped in error, then the final. One card, one pair, two bouts.
REMATCH_ROW = """
<table class="new_table result"><tr><th>x</th></tr><tr>
  <td>1</td>
  <td><div class="fighter_list">
    <a href="/fighter/Bea-2"><span itemprop="name">Bea</span></a>
    <span class="final_result win">win</span></div></td>
  <td><span class="weight_class">Openweight</span></td>
  <td><div class="fighter_list">
    <a href="/fighter/Ada-1"><span itemprop="name">Ada</span></a>
    <span class="final_result loss">loss</span></div></td>
  <td><b>KO</b></td>
  <td>1</td>
  <td>1:00</td>
</tr></table>
"""


EVENT_HTML = """
<html><body>
<div class="event_detail">
  <h1><span itemprop="name">Local MMA 10</span></h1>
  <a href="/organizations/Local-MMA-99999">Local MMA</a>
</div>
<meta itemprop="startDate" content="2025-01-01T00:00:00+00:00"/>
<div class="fight_card">
  <div class="fighter left_side">
    <a href="/fighter/Ada-1"><span itemprop="name">Ada</span></a>
    <span class="final_result win">win</span>
  </div>
  <div class="versus"><span class="weight_class">Middleweight</span></div>
  <div class="fighter right_side">
    <a href="/fighter/Bea-2"><span itemprop="name">Bea</span></a>
    <span class="final_result loss">loss</span>
  </div>
</div>
<table class="fight_card_resume"><tr>
  <td><em>Match</em><br/>1</td>
  <td><em>Method</em><br/>Decision</td>
  <td><em>Round</em><br/>3</td>
  <td><em>Time</em><br/>5:00</td>
</tr></table>
</body></html>
"""


class _Cache:
    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return None

    def keys(self, kind: str) -> list[str]:
        return ["10"] if kind == "events" else []

    def get(self, kind: str, key: str) -> str | None:
        return EVENT_HTML if (kind, key) == ("events", "10") else None


def _stored_row() -> pd.DataFrame:
    """One corpus bout from a fighter page: no promotion, no weight class."""
    return pd.DataFrame([
        {
            "event_href": "/events/Local-MMA-10",
            "event_id": "10",
            "event_name": "Local MMA 10",
            "event_date": "2025-01-01",
            "event_location": None,
            "org": None,
            "org_id": None,
            "match_order": None,
            "fighter_a_id": "1",
            "fighter_a": "Ada",
            "fighter_a_href": "/fighter/Ada-1",
            "fighter_b_id": "2",
            "fighter_b": "Bea",
            "fighter_b_href": "/fighter/Bea-2",
            "fighter_a_outcome": "win",
            "fighter_b_outcome": "loss",
            "weight_class": None,
            "method_raw": "Decision",
            "referee": None,
            "end_round": 3.0,
            "end_time_seconds": 300.0,
            "is_title_fight": False,
            "is_main_event": False,
            "source": "fighter_page",
        }
    ])


def test_cached_event_evidence_replaces_missing_fields_without_adding_bouts(monkeypatch):
    stored = _stored_row()
    monkeypatch.setattr(details, "open_cache", lambda _path: _Cache())

    hydrated, report = details.hydrate(
        stored,
        cache_dir=Path("unused"),
        fetch_missing=False,
        progress=False,
    )

    assert len(hydrated) == len(stored)
    assert hydrated.loc[0, "org"] == "Local MMA"
    assert hydrated.loc[0, "weight_class"] == "Middleweight"
    assert hydrated.loc[0, "source"] == "event"
    assert report["after"]["promotion_share"] == 1.0
    assert report["after"]["weight_class_share"] == 1.0


def test_a_pair_met_twice_on_one_card_does_not_widen_the_corpus(monkeypatch):
    stored = _stored_row()

    class _RematchCache(_Cache):
        def get(self, kind: str, key: str) -> str | None:
            html = super().get(kind, key)
            return html and html.replace("</body>", REMATCH_ROW + "</body>")

    monkeypatch.setattr(details, "open_cache", lambda _path: _RematchCache())

    hydrated, _ = details.hydrate(
        stored, cache_dir=Path("unused"), fetch_missing=False, progress=False
    )

    assert len(hydrated) == len(stored)
    assert hydrated.loc[0, "weight_class"] == "Middleweight"


def test_events_that_can_move_a_tier_are_fetched_first():
    """A named promotion outranks a bigger card from an unnamed one.

    Without this the crawl spends its first hours on pages that resolve to
    tier 4 read or unread, so stopping early leaves nothing decided.
    """
    usable = pd.DataFrame([
        {"event_id": "1", "event_href": "/events/a-1",
         "event_name": "Backyard Scrap 7", "org": None},
        {"event_id": "1", "event_href": "/events/a-1",
         "event_name": "Backyard Scrap 7", "org": None},
        {"event_id": "2", "event_href": "/events/b-2",
         "event_name": "Pancrase - Impressive Tour 5", "org": None},
        {"event_id": "3", "event_href": "/events/c-3",
         "event_name": "Pancrase - Impressive Tour 6", "org": "Pancrase"},
    ])

    ranked = details._fetch_priority(usable)

    assert list(ranked["event_id"]) == ["2", "1", "3"]
    assert ranked["priority"].tolist() == [1, 0, 0]
