"""Unit tests for the top-100 era-skew investigation.

The expensive parts (WHR refits, bootstraps) are not exercised here — they are
covered by ``test_whr`` and ``test_uncertainty``. What is tested is the logic
this investigation adds on top: the bar variants, the truncation cut rule, the
blast-radius arithmetic, and the promise that the committed notebook carries no
embedded output and every cell compiles.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from analysis.investigations import era_skew as es

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "analysis" / "investigations" / "top100_era_skew.ipynb"


def _history(rows) -> pd.DataFrame:
    return pd.DataFrame(
        [{"fighter": f, "event_date": pd.Timestamp(d), "event_name": e, "mu_whr": mu}
         for f, d, e, mu in rows]
    )


def test_annual_means_places_fighters_inside_their_year():
    history = _history([
        ("a", "2010-01-01", "E1", 1700.0),
        ("b", "2010-02-01", "E2", 1600.0),
        ("c", "2010-03-01", "E3", 1500.0),
    ])
    annual = es.annual_means(history)
    by_fighter = annual.set_index("fighter")
    assert list(by_fighter.loc[["a", "b", "c"], "place_in_year"]) == [1, 2, 3]
    assert by_fighter.loc["a", "n_year"] == 3
    assert by_fighter.loc["a", "pct_in_year"] == pytest.approx(1.0)


def test_board_from_bar_clips_at_zero_and_counts_contributing_years():
    history = _history([
        ("a", "2010-01-01", "E1", 1700.0),
        ("a", "2011-01-01", "E2", 1400.0),
        ("b", "2010-01-01", "E1", 1500.0),
        ("b", "2011-01-01", "E2", 1500.0),
    ])
    annual = es.annual_means(history)
    bar = pd.Series({2010: 1600.0, 2011: 1600.0})
    board = es.board_from_bar(annual, bar, "test").set_index("fighter")
    # a clears by 100 in 2010 and misses by 200 in 2011; the miss contributes 0.
    assert board.loc["a", "score"] == pytest.approx(100.0)
    assert board.loc["a", "contributing_years"] == 1
    assert board.loc["a", "active_years"] == 2
    assert board.loc["b", "score"] == pytest.approx(0.0)
    assert board.loc["a", "rank"] == 1


def test_bar_table_leaves_a_fixed_count_undefined_in_a_thin_year():
    """The repair for a growing population is undefined where it is needed."""
    rows = [("f%d" % i, "2000-01-01", "E", 1500.0 + i) for i in range(5)]
    rows += [("g%d" % i, "2020-01-01", "E", 1500.0 + i) for i in range(40)]
    annual = es.annual_means(_history(rows))
    table = es.bar_table(annual, fixed_counts=(30,)).set_index("year")
    assert np.isnan(table.loc[2000, "top-30"])
    assert not np.isnan(table.loc[2020, "top-30"])
    # The 0.90 quantile is a different place in each year.
    assert table.loc[2000, "q0.90 is place"] < table.loc[2020, "q0.90 is place"]


def _fights(rows) -> pd.DataFrame:
    return pd.DataFrame(
        [{"fighter_a": a, "fighter_b": b, "winner": w, "is_draw": False,
          "event_date": pd.Timestamp(d), "event_name": e}
         for a, b, w, d, e in rows]
    )


def test_unbeaten_cut_finds_the_longest_run_not_the_last_one():
    fights = _fights([
        ("x", "o1", "x", "2010-01-01", "E1"),
        ("x", "o2", "x", "2010-06-01", "E2"),
        ("x", "o3", "x", "2011-01-01", "E3"),
        ("x", "o4", "o4", "2011-06-01", "E4"),
        ("x", "o5", "x", "2012-01-01", "E5"),
        ("x", "o6", "o6", "2012-06-01", "E6"),
    ])
    cut = es.unbeaten_cut(fights, "x")
    assert cut["run"] == 3
    assert cut["cut_date"] == pd.Timestamp("2011-01-01")
    assert cut["dropped"] == 3
    assert cut["post_cut_wins"] == 1
    assert cut["post_cut_win_rate"] == pytest.approx(1 / 3)


def test_unbeaten_cut_of_an_unbeaten_career_drops_nothing():
    """The control case: a fighter who never lost has no suffix to delete."""
    fights = _fights([
        ("x", "o1", "x", "2010-01-01", "E1"),
        ("x", "o2", "x", "2011-01-01", "E2"),
    ])
    assert es.unbeaten_cut(fights, "x")["dropped"] == 0


def test_ols_recovers_a_planted_slope():
    rng = np.random.default_rng(0)
    x = rng.normal(size=400)
    y = 3.0 + 2.5 * x
    terms, r2 = es.ols(y, pd.DataFrame({"x": x}))
    assert terms.set_index("term").loc["x", "coef"] == pytest.approx(2.5)
    assert r2 == pytest.approx(1.0)


def test_blast_radius_counts_turnover_both_ways():
    before = pd.DataFrame({"fighter": list("abcd"), "rank": [1, 2, 3, 4],
                           "score": [4.0, 3.0, 2.0, 1.0],
                           "first_year": [2005, 2010, 2015, 2020],
                           "last_year": [2012, 2018, 2025, 2026]})
    after = pd.DataFrame({"fighter": list("cdab"), "rank": [1, 2, 3, 4],
                          "score": [4.0, 3.0, 2.0, 1.0],
                          "first_year": [2015, 2020, 2005, 2010],
                          "last_year": [2025, 2026, 2012, 2018]})
    radius = es.blast_radius(before, after, top_n=2)
    assert radius["entered_top_n"] == 2
    assert radius["left_top_n"] == 2
    assert radius["active_2024_before"] == 0
    assert radius["active_2024_after"] == 2


def test_composition_reads_the_three_headline_numbers():
    board = pd.DataFrame({
        "fighter": list("abc"),
        "score": [10.0, 5.0, 0.0],
        "rank": [1, 2, 3],
        "first_year": [2005, 2015, 2020],
        "last_year": [2012, 2025, 2026],
    })
    comp = es.composition(board, top_n=3)
    assert comp["active_2024_plus"] == 2
    assert comp["debut_2009_or_earlier"] == 1
    assert comp["median_debut_year"] == 2015
    assert comp["zero_mass_fighters"] == 1


def test_verdict_only_accepts_the_three_allowed_answers():
    for verdict in ("supported", "refuted", "unresolved"):
        assert verdict.upper() in es.Verdict("H", "c", verdict, "b").as_markdown()
    with pytest.raises(KeyError):
        es.Verdict("H", "c", "probably", "b").as_markdown()


def test_committed_notebook_has_no_outputs_and_compiles():
    if not NOTEBOOK.exists():
        pytest.skip("notebook not built")
    nb = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    code_cells = [c for c in nb["cells"] if c["cell_type"] == "code"]
    assert code_cells, "notebook has no code cells"
    for i, cell in enumerate(code_cells):
        assert not cell.get("outputs"), f"cell {i} carries embedded output"
        assert cell.get("execution_count") is None, f"cell {i} carries an execution count"
        compile("".join(cell["source"]), f"<cell {i}>", "exec")


def test_notebook_prose_cells_carry_no_measurements():
    """Static markdown may state a prediction; a figure must come from a cell."""
    if not NOTEBOOK.exists():
        pytest.skip("notebook not built")
    nb = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    # Section numbers, the snapshot date's parts, the bar parameter, and a
    # cross-reference to another document's section. Nothing else.
    allowed = {"0", "1", "2", "3", "4", "5", "6", "7", "8", "9",
               "08", "13", "21", "60", "100", "2026", "0.9", "3.9"}
    import re
    for cell in nb["cells"]:
        if cell["cell_type"] != "markdown":
            continue
        # Blockquoted lines are the brief's hypotheses, quoted verbatim; a
        # prediction is allowed to state the figure it is a prediction about.
        text = "".join(line for line in cell["source"] if not line.lstrip().startswith(">"))
        for token in re.findall(r"\d[\d,.]*", text):
            token = token.rstrip(".,")
            assert token in allowed, f"markdown cell states an unallowed figure: {token!r}"


# ---------------------------------------------------------------------------
# Chart contract: self-contained canvas, and never meaning in colour alone.


def _synthetic_annual():
    rows = []
    for year in range(2000, 2012):
        for i in range(30):
            rows.append({"fighter": f"F{i}", "event_date": pd.Timestamp(f"{year}-06-01"),
                         "event_name": "E", "mu_whr": 1500.0 + 10 * i + (year - 2000)})
    return es.annual_means(pd.DataFrame(rows))


def _figures():
    from analysis.investigations import era_skew_viz as ev

    annual = _synthetic_annual()
    bar = annual.groupby("year")["annual_mean"].quantile(0.9)
    table = es.bar_table(annual, fixed_counts=(30,))
    board = es.board_from_bar(annual, bar, "t")
    cases = board["fighter"].head(5).tolist()
    return {
        "board_shape": ev.board_shape_chart(board, top_n=10),
        "field_shape": ev.field_shape_chart(table, annual),
        "case_gap": ev.case_gap_chart(annual, bar, cases),
        "bar_variants": ev.bar_variants_chart(table),
        "rank_move": ev.rank_move_chart(board, board, cases, before_label="a",
                                        after_label="b", title="t"),
    }


def test_every_chart_paints_its_own_opaque_canvas():
    """A figure that inherits the notebook host's background is unreadable in
    whichever theme it was not designed for."""
    for name, fig in _figures().items():
        paper = fig.layout.paper_bgcolor
        plot = fig.layout.plot_bgcolor
        assert paper and not str(paper).startswith("rgba(0,0,0,0"), f"{name}: transparent paper"
        assert plot and not str(plot).startswith("rgba(0,0,0,0"), f"{name}: transparent plot area"


def test_line_series_are_separable_without_colour():
    """Every line series in a multi-series chart carries its own dash pattern
    or marker symbol, so removing hue loses nothing."""
    for name, fig in _figures().items():
        lines = [t for t in fig.data
                 if t.type == "scatter" and t.mode and "lines" in t.mode and t.showlegend is not False]
        if len(lines) < 2:
            continue
        keys = {(getattr(t.line, "dash", None), getattr(t.marker, "symbol", None))
                for t in lines}
        assert len(keys) == len(lines), f"{name}: {len(lines)} lines share {len(keys)} dash/symbol pairs"
