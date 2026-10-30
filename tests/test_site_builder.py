"""Site frames retain drawing values and map missing data to JSON null."""

import numpy as np
import pandas as pd

from analysis.build_site import ASSETS, ROOT, lineage_rows, mover_rows, plain, version, year_top_rows


def test_plain_maps_missing_values_to_null_and_rounds_to_integers():
    assert plain([np.nan, pd.NaT, pd.Timestamp("2020-01-02"), np.float64(2.6)], 0) == [None, None, "2020-01-02", 3]


def test_chart_frames_keep_only_the_values_the_site_draws():
    year = pd.DataFrame([["LW", 1500.123, "1. Jon Jones · LW"]], columns=["division", "rating", "label"])
    movers = pd.DataFrame([["Jon Jones", 12.345, "vs opponent", 3]],
                          columns=["fighter", "total_delta", "hover_lines", "n_fights"])
    reign = pd.DataFrame([[
        "Champion", "Challenger", "2000-01-01", 2, 3.456, 86_400_000, "Champion (2D)"
    ]], columns=["fighter", "opponent", "start", "defences", "years", "bar_length", "label"])
    assert year_top_rows(year) == [["LW", [1500.12], ["1. Jon Jones · LW"]]]
    assert mover_rows(movers) == [[12.35], ["Jon Jones"], [["vs opponent", "3"]]]
    assert lineage_rows(reign) == [[
        "Champion", "Challenger", "2000-01-01", 2, 3.46, 86_400_000, "Champion (2D)"
    ]]


def test_index_points_at_current_assets():
    """A stale ?v= stamp lets a browser pair the page with a cached older asset; re-stamp with --stamp."""
    site = ROOT / "site"
    h = (site / "index.html").read_text(encoding="utf-8")
    assert all(f'"{a}?v={version(site / a)}"' in h for a in ASSETS)
