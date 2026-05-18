from pathlib import Path

import pytest

from loaders.datalab_loader import DEFAULT_DATALAB_DIR, load_datalab_dataset
from loaders.fightmatrix_loader import parse_rankings_html


def test_datalab_local_checkout_loads_all_bouts():
    if not DEFAULT_DATALAB_DIR.exists():
        pytest.skip(f"UFC-DataLab checkout not present: {DEFAULT_DATALAB_DIR}")

    df = load_datalab_dataset(DEFAULT_DATALAB_DIR, "datalab_bouts_all")

    assert len(df) > 1_000
    assert {"red_fighter_name", "blue_fighter_name", "event_date", "winner"}.issubset(df.columns)
    assert df["event_date"].notna().any()


def test_fightmatrix_rankings_parser_extracts_profile_links():
    html = """
    <table class="tblRank">
      <tr><th>Rank</th><th>Fighter</th><th>Record</th><th>Points</th></tr>
      <tr>
        <td>1</td>
        <td><a href="/fighter-profile/Ilia%20Topuria/149195/">Ilia Topuria (29)</a></td>
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

