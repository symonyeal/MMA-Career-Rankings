"""The published release rebuilds from a clean checkout.

Until 2026-10-14 the fit's inputs and the fitted ratings were gitignored, so the
published boards could be rebuilt on one machine only. A second machine had to
re-crawl the sources and came back with 43 fewer birth dates and no odds rows,
and nothing failed, because every test that needed the data skipped itself on a
fresh clone. CI runs on a fresh clone, so these tests now fail there the moment
a file the release reads is not committed.

R   : repository root
S   : the published release snapshot
X   : Sherdog extracts every new snapshot's staging reads; small, versioned beside the local page store
P   : every path a rebuild reads
r   : check_release report;  g : git check-ignore result
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from check_release import PUBLISHED_SNAPSHOT as S
from check_release import check

R = Path(__file__).resolve().parents[1]
X = [R / "data" / "external" / "sherdog" / n
     for n in ("profile_birth_dates.csv", "career_pages_incorporated.json")]


def test_published_release_has_every_input_and_fitted_artifact():
    r = check(S)

    assert r["missing"] == []
    assert r["issues"] == []


def test_sherdog_extracts_are_present():
    assert [p.name for p in X if not p.is_file()] == []


def test_nothing_the_release_reads_is_gitignored():
    if not (R / ".git").exists():
        pytest.skip("not a git checkout")
    P = sorted(p for p in S.iterdir() if p.is_file()) + X
    g = subprocess.run(["git", "check-ignore", "--no-index", *(str(p.relative_to(R)) for p in P)],
                       cwd=R, capture_output=True, text=True, check=False)
    # Exit 1 means no path matched an ignore rule; 128 is a git failure.
    assert g.returncode != 128, g.stderr
    assert g.stdout.split() == []
