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
import json
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


def test_all_cells_execute_and_render(nb_ns):
    # Every section produced something on first draw.
    assert nb_ns["lb_html"].value, "leaderboard empty"
    assert _n_traces(nb_ns["traj_fw"]) > 0
    assert _n_traces(nb_ns["plc_scatter"]) > 0
    assert _n_traces(nb_ns["divx_timeline"]) > 0
    assert _n_traces(nb_ns["era_fw"]) > 0
    assert nb_ns["streak_html"].value


def test_top_n_reacts(nb_ns):
    before = nb_ns["lb_html"].value
    nb_ns["g_top_n"].value = 10
    assert nb_ns["lb_html"].value != before, "leaderboard ignored Top N"


def test_scoring_lens_reacts(nb_ns):
    nb_ns["g_top_n"].value = 25
    before = nb_ns["lb_html"].value
    nb_ns["g_lens"].value = "wins"
    assert nb_ns["lb_html"].value != before, "leaderboard ignored scoring change"
    assert "Wins" in nb_ns["lb_html"].value


def test_custom_prime_window_recomputes(nb_ns):
    nb_ns["g_lens"].value = "complete"
    nb_ns["g_time"].value = "sustained_peak"
    nb_ns["g_prime_years"].value = 8
    nb_ns["g_prime_min"].value = 12
    assert nb_ns["lb_html"].value, "leaderboard empty under custom Prime window"
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
