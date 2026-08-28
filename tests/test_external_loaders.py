
import pytest

from loaders.datalab_loader import DEFAULT_DATALAB_DIR, load_datalab_dataset
from loaders.fightmatrix_loader import parse_rankings_html
from loaders.fightmatrix_profiles import parse_profile_html
from loaders.sherdog_loader import org_from_event


def test_datalab_local_checkout_loads_all_bouts():
    if not DEFAULT_DATALAB_DIR.exists():
        pytest.skip(f"UFC-DataLab checkout not present: {DEFAULT_DATALAB_DIR}")

    df = load_datalab_dataset(DEFAULT_DATALAB_DIR, "datalab_bouts_all")

    assert len(df) > 1_000
    assert {"red_fighter_name", "blue_fighter_name", "event_date", "winner"}.issubset(df.columns)
    assert df["event_date"].notna().any()


def test_org_classifier_recognizes_ufc_case_insensitively():
    assert org_from_event("UFC Fight Night: Whittaker vs. Till") == "UFC"
    assert org_from_event("Pride FC 32") == "PRIDE"


def test_fightmatrix_rankings_parser_extracts_profile_links():
    html = """
    <table class="tblRank">
      <tr><th>Rank</th><th>Fighter</th><th>Record</th><th>Points</th></tr>
      <tr>
        <td colspan="4" style="display:none"></td>
      </tr>
      <tr onmouseover="LoadCustomDataWithRecs('stat','Ilia Topuria|Topuria Team|4/04/2015|4-0-0|10-0-0|6/28/2025|76.5%|.667|88.2%|30|||','rec','W|W|W|W|W|')">
        <td>1</td>
        <td><img src="/images/flag/ES.png"/><a href="/fighter-profile/Ilia%20Topuria/149195/">Ilia Topuria (29)</a></td>
        <td>17-0-0</td>
        <td>2965</td>
      </tr>
    </table>
    """

    df = parse_rankings_html(html, "lightweight")

    assert df.loc[0, "rank"] == 1
    assert df.loc[0, "fighter"] == "Ilia Topuria"
    assert df.loc[0, "age"] == 29
    assert df.loc[0, "profile_url"].endswith("/fighter-profile/Ilia%20Topuria/149195/")
    assert df.loc[0, "nationality_code"] == "ES"
    assert df.loc[0, "association"] == "Topuria Team"
    assert df.loc[0, "big_league_record"] == "10-0-0"
    assert df.loc[0, "quality_performance_pct"] == pytest.approx(76.5)
    assert df.loc[0, "opponent_540_metric"] == pytest.approx(0.667)
    assert df.loc[0, "win_finish_pct"] == pytest.approx(88.2)
    assert df.loc[0, "combat_age"] == pytest.approx(30)
    assert df.loc[0, "last_five_results"] == "W|W|W|W|W"


def test_fightmatrix_all_time_parser_uses_same_stable_schema():
    html = """
    <table class="tblRank">
      <tr><th>Rank</th><th>Fighter</th><th>Record</th><th>Points</th></tr>
      <tr>
        <td>1</td>
        <td><a href="/fighter-profile/Georges%20St.%20Pierre/3500/">Georges St. Pierre</a></td>
        <td>26-2-0</td>
        <td>38570</td>
      </tr>
    </table>
    """

    df = parse_rankings_html(html, "all-time-absolute")

    assert df.loc[0, "division"] == "all-time-absolute"
    assert df.loc[0, "fighter"] == "Georges St. Pierre"
    assert df.loc[0, "rank"] == 1
    assert df.loc[0, "points"] == 38570


def test_fightmatrix_profile_parser_extracts_metadata_and_complete_bout():
    html = """
    <h1>Georges St. Pierre</h1>
    <div>Issue Date: 8/09/2026 (Official Release: #1036)</div>
    <table class="tblRank">
      <tr><td>
        <a href="https://www.sherdog.com/fighter/Georges-St-Pierre-3500">profile at Sherdog</a>
        Birth Date: 1981-05-19 Association: Tristar Gym
        Pro Debut Date: 2002-01-25 Pro Record: 26-2-0
      </td></tr>
      <tr><td>Win Finish %: 53.8% Quality Perf. %: 89.3%</td></tr>
      <tr><td>UFC Record: 20-2-0 Octagon Time: 5:42:35 Title Bouts: 13-2-0
        Longest Win Streak: 13 UFC Debut: 2004-01-31 Last UFC Fight: 2017-11-04</td></tr>
    </table>
    <table class="tblRank">
      <tr><td>&nbsp;</td><td>Opponent</td><td>Outcome</td></tr>
      <tr>
        <td rowspan="2"><b>W</b></td>
        <td><a href="/fighter-profile/Michael%20Bisping/22158/">Michael Bisping</a>
          <em>#1 Middleweight</em></td>
        <td>Technical Submission (Rear Naked Choke)<br/>Round 3</td>
      </tr>
      <tr><td colspan="2"><img src="/images/flag/US.png"/>
        <a href="/event/UFC%20217/186968/">UFC 217 - Bisping vs. St. Pierre</a>
        <em>Saturday, November 4th 2017</em></td></tr>
    </table>
    """

    profile, bouts = parse_profile_html(
        html,
        "https://www.fightmatrix.com/fighter-profile/Georges%20St.%20Pierre/9489/",
    )

    assert profile["profile_id"] == "9489"
    assert profile["fighter"] == "Georges St. Pierre"
    assert profile["association"] == "Tristar Gym"
    assert profile["pro_record"] == "26-2-0"
    assert profile["win_finish_pct"] == pytest.approx(53.8)
    assert profile["quality_performance_pct"] == pytest.approx(89.3)
    assert str(profile["pro_debut_date"].date()) == "2002-01-25"
    assert len(bouts) == 1
    bout = bouts.iloc[0]
    assert bout["opponent"] == "Michael Bisping"
    assert bout["result"] == "win"
    assert bout["method_class"] == "Submission"
    assert bout["end_round"] == 3
    assert bout["opponent_prefight_rank"] == 1
    assert bout["opponent_prefight_division"] == "Middleweight"
    assert bout["event_id"] == "186968"
    assert str(bout["event_date"].date()) == "2017-11-04"
    assert bout["org"] == "UFC"
    assert bout["event_country_code"] == "US"

