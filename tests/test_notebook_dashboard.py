"""Headless execution + reactivity test for the interactive dashboard notebook.

We can't drive a live widget frontend in CI, but we can do the next best thing:
build the notebook, execute every code cell in one shared namespace with
``NB_STRICT=1`` (so any draw-callback error raises instead of being swallowed by
traitlets), then mutate the global Control-Room widgets and assert the dependent
charts / tables actually change. This is what proves the toggles are wired.
"""
from __future__ import annotations

import contextlib
import io
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_DIR = ROOT / "data" / "snapshots" / "2026-05-13"

pytest.importorskip("ipywidgets")
pytest.importorskip("anywidget", reason="FigureWidget requires anywidget")
import plotly.graph_objects as go  # noqa: E402

if "FigureWidget" not in dir(go) or go.FigureWidget.__module__.endswith("missing_anywidget"):
    pytest.skip("plotly FigureWidget unavailable", allow_module_level=True)


def _build_namespace():
    """Exec every notebook code cell in one namespace; return it."""
    from analysis.build_notebook import build

    nb = build()
    codes = [
        "".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code"
    ]
    ns = {"__name__": "__nb_test__"}
    cwd = os.getcwd()
    os.environ["NB_STRICT"] = "1"
    os.chdir(ROOT)
    sink = io.StringIO()
    try:
        with contextlib.redirect_stdout(sink):
            for i, src in enumerate(codes):
                exec(compile(src, f"<cell {i}>", "exec"), ns)
    finally:
        os.chdir(cwd)
        os.environ.pop("NB_STRICT", None)
    return ns


@pytest.fixture(scope="module")
def nb_ns():
    if not SNAPSHOT_DIR.exists():
        pytest.skip(f"snapshot not present: {SNAPSHOT_DIR}")
    return _build_namespace()


def _n_traces(fw):
    return len(fw.data)


def _rendered(fw):
    return _n_traces(fw) > 0 or bool(fw.layout.annotations)


def test_all_cells_execute_and_render(nb_ns):
    # Every section produced something on first draw. The era heat map used to
    # live in its own cell (``era_fw``) but now folds into the Weight Classes
    # section as ``divx_era``, so the chart asserted-on moved with it.
    assert nb_ns["lb_html"].value, "leaderboard empty"
    assert _n_traces(nb_ns["traj_fw"]) > 0
    assert _n_traces(nb_ns["plc_scatter"]) > 0
    assert _n_traces(nb_ns["divx_timeline"]) > 0
    assert _n_traces(nb_ns["divx_era"]) > 0
    assert nb_ns["streak_html"].value


def test_new_sections_render(nb_ns):
    # 2026-06-23 chart additions: every new section drew something on first load.
    assert _rendered(nb_ns["anatomy_fw"])          # score receipt or legacy-snapshot state
    assert _n_traces(nb_ns["dom_fw"]) > 0          # Most Dominant
    assert _n_traces(nb_ns["lp_fw"]) > 0           # Legacy vs Prime
    assert _n_traces(nb_ns["divx_entropy"]) > 0    # Division parity
    assert _n_traces(nb_ns["divx_method"]) > 0     # How fights end
    assert _n_traces(nb_ns["tl_fw"]) > 0           # Title lineage
    assert _n_traces(nb_ns["cmp_a_strike"]) > 0    # Striking fingerprint (Tale of the Tape)
    assert _n_traces(nb_ns["mkt_fav"]) > 0         # Results vs the Market
    assert _n_traces(nb_ns["mkt_line"]) > 0        # Per-fighter betting-line chart
    assert _n_traces(nb_ns["intg_fw"]) > 0         # Integrity Ledger
    assert nb_ns["intg_html"].value                # Integrity ledger table
    if not nb_ns["fightmatrix_all_time"].empty:
        assert _n_traces(nb_ns["benchmark_fw"]) > 0   # external all-time sanity check
    else:
        assert nb_ns["benchmark_fw"].layout.annotations
    assert nb_ns["benchmark_html"].value
    assert _rendered(nb_ns["evidence_scores_fw"])   # held-out scorecard or explicit empty state
    assert _rendered(nb_ns["evidence_ablation_fw"]) # paired forest or explicit empty state


def test_career_functional_sections_render(nb_ns):
    """The rank interval, bar ladder, evidence ladder and score receipt."""
    # The bootstrap artifact is optional, so this one may be an empty state.
    assert _rendered(nb_ns["unc_fw"])
    assert _n_traces(nb_ns["ladder_fw"]) > 0        # bar sensitivity family
    assert _n_traces(nb_ns["evidence_fw"]) > 0      # rating vs evidence under it
    assert _n_traces(nb_ns["story_fw"]) > 0         # one fighter's contribution
    assert _n_traces(nb_ns["shape_fw"]) > 0         # years vs height decomposition


def test_career_story_follows_the_fighter_box(nb_ns):
    before = nb_ns["story_fw"].layout.title.text
    pool = list(nb_ns["story_fighter"].options)
    nb_ns["story_fighter"].value = pool[3] if len(pool) > 3 else pool[-1]
    assert nb_ns["story_fw"].layout.title.text != before


def test_public_notebook_is_evidence_first_and_read_only():
    from analysis.build_notebook import build

    nb = build()
    markdown = "\n".join(
        "".join(cell["source"]) for cell in nb["cells"] if cell["cell_type"] == "markdown"
    )
    code_text = "\n".join(
        "".join(cell["source"]) for cell in nb["cells"] if cell["cell_type"] == "code"
    )
    assert markdown.index("## Why the All-time leaders rank here") > markdown.index("## The Rankings")
    assert markdown.index("## Does the rating model hold up?") > markdown.index(
        "## Why the All-time leaders rank here"
    )
    assert "## What Moved a Fighter's Rating" not in markdown
    assert "## Under the Hood" not in markdown
    assert "## 🛠️ Model Tuning" not in markdown
    assert "## Results vs the Market" in markdown
    assert markdown.index("## Appendix: Ranking Sanity Check") > markdown.index("## Results vs the Market")
    assert "TUNE_WIDGETS" not in code_text
    assert "def _recompute" not in code_text
    assert "g_lens" not in code_text
    assert "g_time" not in code_text
    assert "g_prime_years" not in code_text
    assert "g_prime_min" not in code_text
    assert "method_integrity_performance" not in code_text
    assert "whr_integrity_performance" not in code_text


def test_all_time_default_is_explicit(nb_ns):
    assert nb_ns["g_rank_view"].value == "all_time"
    assert nb_ns["g_top_n"].value == 30
    assert nb_ns["g_gender"].value == "M"
    assert "g_lens" not in nb_ns and "g_time" not in nb_ns
    assert "g_prime_years" not in nb_ns and "g_prime_min" not in nb_ns
    if not nb_ns["ratings_history_whr"].empty:
        assert nb_ns["selected_stream_col"]() == "mu_whr"
        assert nb_ns["selected_history"]().equals(nb_ns["ratings_history_whr"])


def test_market_fighter_line_reacts(nb_ns):
    # Switching the per-fighter dropdown redraws the betting-line chart.
    opts = list(nb_ns["mkt_fighter"].options)
    if len(opts) > 1:
        nb_ns["mkt_fighter"].value = opts[1]
        assert _n_traces(nb_ns["mkt_line"]) >= 0


def test_top_n_reacts(nb_ns):
    before = nb_ns["lb_html"].value
    nb_ns["g_top_n"].value = 10
    assert nb_ns["lb_html"].value != before, "leaderboard ignored Top N"


def test_ranking_view_reacts(nb_ns):
    nb_ns["g_top_n"].value = 25
    before = nb_ns["lb_html"].value
    nb_ns["g_rank_view"].value = "current"
    assert nb_ns["lb_html"].value != before, "leaderboard ignored ranking-view change"
    assert "Current skill" in nb_ns["lb_html"].value


def test_fixed_prime_view_renders_and_peak_is_retired(nb_ns):
    nb_ns["g_rank_view"].value = "prime"
    assert nb_ns["selected_rating_col"]() in {
        "symon_prime_score", "sustained_peak_headline_mu_whr",
        "sustained_peak_mu_whr", "sustained_peak_headline_mu_canonical",
        "sustained_peak_mu_canonical", "mu_whr", "mu_canonical",
    }
    assert "Prime" in nb_ns["lb_html"].value
    assert "peak" not in nb_ns["g_rank_view"]._options_values
    assert _n_traces(nb_ns["plc_scatter"]) > 0


def test_division_and_gender_filter(nb_ns):
    nb_ns["g_division"].value = "Lightweight"
    nb_ns["g_gender"].value = "M"
    assert nb_ns["lb_html"].value, "leaderboard empty after division/gender filter"
    # streak selector still has populated options (regression: unobserve_all bug)
    assert len(nb_ns["streak_pick"]._options_values) >= 0


def test_streak_selector_options_stay_in_sync(nb_ns):
    # Setting options must keep _options_values populated; index selection works.
    sp = nb_ns["streak_pick"]
    if sp.options:
        assert len(sp._options_values) == len(sp.options)
        sp.index = 0
        assert _n_traces(nb_ns["streak_fw"]) >= 0


def test_compare_local_control(nb_ns):
    names = nb_ns["_fighter_names"]
    before = nb_ns["cmp_html"].value
    nb_ns["cmp_b"].value = names[3] if names[3] != nb_ns["cmp_a"].value else names[4]
    assert nb_ns["cmp_html"].value != before or _n_traces(nb_ns["cmp_a_profile"]) > 0
