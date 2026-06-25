"""Network-free tests for the live UFCStats scraper (loaders/ufcstats_scrape.py).

These lock the proof-of-work solver, the history-preserving append, and the HTML
parsers against compact fixtures. No request is made; ``make_session`` /
``scrape_new_events`` are exercised only against live data, not here.
"""
import hashlib

import pandas as pd

from loaders.ufcstats_scrape import (
    _append,
    is_challenge,
    parse_event_page,
    parse_fight_page,
    parse_fighter_page,
    solve_pow,
)

CHALLENGE_HTML = """<!doctype html><html><body><p>Checking your browser...</p>
<script>var nonce="abc123",target=new Array(2+1).join('0');</script></body></html>"""

EVENT_HTML = """<html><body>
<h2 class="b-content__title">UFC Test: A vs. B</h2>
<ul>
  <li class="b-list__box-list-item">Date: June 20, 2026</li>
  <li class="b-list__box-list-item">Location: Las Vegas, Nevada, USA</li>
</ul>
<table><tbody>
  <tr class="b-fight-details__table-row" data-link="http://ufcstats.com/fight-details/f1"></tr>
  <tr class="b-fight-details__table-row" data-link="http://ufcstats.com/fight-details/f2"></tr>
</tbody></table>
</body></html>"""


def _pp(a, b):
    return f"<td><p>{a}</p><p>{b}</p></td>"


def _round_row(vals_a, vals_b):
    cells = "".join(_pp(a, b) for a, b in zip(vals_a, vals_b))
    return f"<tr>{cells}</tr>"


# totals per-round: Fighter,KD,SIG.STR.,SIG%,TOTAL,TD,TD%,SUB,REV,CTRL
TOT_A = ["Jon Jones", "1", "10 of 20", "50%", "15 of 30", "2 of 3", "66%", "0", "0", "3:00"]
TOT_B = ["Foe Bar", "0", "5 of 15", "33%", "8 of 20", "0 of 1", "0%", "1", "0", "1:00"]
# sig per-round: Fighter,Sig,Sig%,HEAD,BODY,LEG,DISTANCE,CLINCH,GROUND
SIG_A = ["Jon Jones", "10 of 20", "50%", "6 of 12", "2 of 4", "2 of 4", "8 of 16", "1 of 2", "1 of 2"]
SIG_B = ["Foe Bar", "5 of 15", "33%", "3 of 10", "1 of 3", "1 of 2", "5 of 15", "0 of 0", "0 of 0"]

FIGHT_HTML = f"""<html><body>
<i class="b-fight-details__fight-title">UFC Light Heavyweight Title Bout</i>
<div class="b-fight-details__person">
  <i class="b-fight-details__person-status">W</i>
  <h3 class="b-fight-details__person-name"><a href="http://ufcstats.com/fighter-details/a1">Jon Jones</a></h3>
</div>
<div class="b-fight-details__person">
  <i class="b-fight-details__person-status">L</i>
  <h3 class="b-fight-details__person-name"><a href="http://ufcstats.com/fighter-details/b1">Foe Bar</a></h3>
</div>
<i class="b-fight-details__text-item_first">Method: KO/TKO</i>
<i class="b-fight-details__text-item">Round: 1</i>
<i class="b-fight-details__text-item">Time: 3:21</i>
<i class="b-fight-details__text-item">Time format: 5 Rnd (5-5-5-5-5)</i>
<i class="b-fight-details__text-item">Referee: Herb Dean</i>
<p class="b-fight-details__text">Details: Punches to Head At Distance</p>
<table><tbody><tr><td>overall</td></tr></tbody></table>
<table><tbody>{_round_row(TOT_A, TOT_B)}</tbody></table>
<table><tbody><tr><td>overall sig</td></tr></tbody></table>
<table><tbody>{_round_row(SIG_A, SIG_B)}</tbody></table>
</body></html>"""

FIGHTER_HTML = """<html><body>
<span class="b-content__title-highlight">Jon Jones</span>
<p class="b-content__Nickname">Bones</p>
<ul>
  <li class="b-list__box-list-item">Height: 6' 4"</li>
  <li class="b-list__box-list-item">Weight: 248 lbs.</li>
  <li class="b-list__box-list-item">Reach: 84"</li>
  <li class="b-list__box-list-item">STANCE: Orthodox</li>
  <li class="b-list__box-list-item">DOB: Jul 19, 1987</li>
</ul>
</body></html>"""


def test_is_challenge_detects_wall():
    assert is_challenge(CHALLENGE_HTML)
    assert not is_challenge("<html><body>real page</body></html>")


def test_solve_pow_finds_valid_nonce():
    n = solve_pow("abc123", 2)
    assert hashlib.sha256(f"abc123:{n}".encode()).hexdigest().startswith("00")
    # smallest solution: nothing below n satisfies it
    assert all(not hashlib.sha256(f"abc123:{i}".encode()).hexdigest().startswith("00")
               for i in range(n))


def test_parse_event_page():
    meta, links = parse_event_page(EVENT_HTML)
    assert meta["EVENT"] == "UFC Test: A vs. B"
    assert meta["DATE"] == "June 20, 2026"
    assert meta["LOCATION"] == "Las Vegas, Nevada, USA"
    assert links == ["http://ufcstats.com/fight-details/f1",
                     "http://ufcstats.com/fight-details/f2"]


def test_parse_fight_page_result_and_stats():
    parsed = parse_fight_page(FIGHT_HTML, "UFC Test: A vs. B")
    res = parsed["result"]
    assert res["BOUT"] == "Jon Jones vs. Foe Bar"
    assert res["OUTCOME"] == "W/L"
    assert res["WEIGHTCLASS"] == "UFC Light Heavyweight Title Bout"
    assert res["METHOD"] == "KO/TKO"
    assert res["ROUND"] == "1"
    assert res["TIME"] == "3:21"
    assert res["TIME FORMAT"] == "5 Rnd (5-5-5-5-5)"
    assert res["REFEREE"] == "Herb Dean"
    assert res["DETAILS"] == "Punches to Head At Distance"

    stats = parsed["stats"]
    assert len(stats) == 2  # one round, two fighters
    a_row = next(r for r in stats if r["FIGHTER"] == "Jon Jones")
    assert a_row["ROUND"] == "Round 1"
    assert a_row["KD"] == "1"
    assert a_row["SIG.STR."] == "10 of 20"
    assert a_row["CTRL"] == "3:00"
    assert a_row["HEAD"] == "6 of 12"
    assert a_row["GROUND"] == "1 of 2"
    b_row = next(r for r in stats if r["FIGHTER"] == "Foe Bar")
    assert b_row["TD"] == "0 of 1"
    assert b_row["SUB.ATT"] == "1"
    assert parsed["fighters"] == [
        ("Jon Jones", "http://ufcstats.com/fighter-details/a1"),
        ("Foe Bar", "http://ufcstats.com/fighter-details/b1"),
    ]


def test_parse_fighter_page():
    fdet, tott = parse_fighter_page(FIGHTER_HTML)
    assert fdet == {"FIRST": "Jon", "LAST": "Jones", "NICKNAME": "Bones"}
    assert tott["FIGHTER"] == "Jon Jones"
    assert tott["HEIGHT"] == '6\' 4"'
    assert tott["WEIGHT"] == "248 lbs."
    assert tott["REACH"] == '84"'
    assert tott["STANCE"] == "Orthodox"
    assert tott["DOB"] == "Jul 19, 1987"


def test_append_preserves_history_and_dedupes():
    old = pd.DataFrame({"URL": ["u1", "u2"], "EVENT": ["E1", "E2"]})
    new_rows = [
        {"URL": "u2", "EVENT": "E2-dup"},   # already present -> dropped
        {"URL": "u3", "EVENT": "E3"},       # genuinely new -> kept
        {"URL": "u3", "EVENT": "E3-again"}, # duplicate of a new row -> dropped
    ]
    out = _append(old, new_rows, ["URL", "EVENT"], ["URL"])
    assert list(out["URL"]) == ["u1", "u2", "u3"]
    # historical rows are untouched
    assert out.iloc[1]["EVENT"] == "E2"
    assert out.iloc[2]["EVENT"] == "E3"
