"""Every number the README's narrative paragraphs quote, computed from a release snapshot.

Usage: ``python analysis/readme_figures.py [data/snapshots/<date>]`` prints them; the default is the
published release. Add ``--write-readme`` to update the narrative paragraphs.
``tests/test_readme_figures.py`` fails when the README text and these values part.

Legend
  S     snapshot folder              c   ratings_current, one row per fighter
  P     the two careers the README compares (Jones, St-Pierre)
  T, K, Q  title, skill and résumé points (ratings.legacy_resume.legacy_points)
  r     contender wins priced by the résumé, on the era-adjusted history the board reads
  e     Prime elite level (prime_elite_board.elite_level);  d  its Jones - St-Pierre edge
  E     men's contender line by year (ratings.symon_score.year_reference over annual means)
  F     generated figures            p   README path
"""
from __future__ import annotations

import sys
import argparse
import re
import textwrap
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from check_release import PUBLISHED_SNAPSHOT
from loaders.combined_fights import load_combined_fights
from ratings.era import era_rated
from ratings.legacy_resume import contender_resume_rows, legacy_points
from ratings.opponent_quality import CONTENDER_LINE_MU
from ratings.fights import rated_rows
from ratings.scope import DEFAULT_PUBLISHED_SCOPE
from ratings.symon_score import DEFAULT_CAREER_REFERENCE, year_reference

P = ("Jon Jones", "Georges St-Pierre")
ERA_YEARS = (2007, 2023)


def figures(S: Path = PUBLISHED_SNAPSHOT) -> dict[str, float | str]:
    S = Path(S)
    c = pd.read_parquet(S / "ratings_current.parquet")
    T, K, Q = legacy_points(c["public_legacy_title_score"], c["public_legacy_skill_score"],
                            c["public_legacy_resume_score"])
    c = c.assign(T=T, K=K, Q=Q).set_index("fighter")
    a, b = (c.loc[p] for p in P)
    out: dict[str, float | str] = {
        "score_a": a["public_legacy_score"], "score_b": b["public_legacy_score"],
        "ratio": a["public_legacy_score"] / b["public_legacy_score"] - 1.0,
        "title_a": a["T"], "title_b": b["T"], "resume_a": a["Q"], "resume_b": b["Q"],
        "skill_a": a["K"], "skill_b": b["K"],
    }

    h = pd.read_parquet(S / "ratings_history_whr.parquet")
    f, _ = load_combined_fights(S, scope=DEFAULT_PUBLISHED_SCOPE, label="readme")
    r = contender_resume_rows(rated_rows(f), era_rated(h))
    r = r.assign(above=r["opponent_mu"] - CONTENDER_LINE_MU).sort_values("above", ascending=False)
    ra, rb = r[r["fighter"].eq(P[0])], r[r["fighter"].eq(P[1])]
    for i in range(2):
        out[f"elite_{i + 1}_name"], out[f"elite_{i + 1}_above"] = ra["opponent"].iloc[i], ra["above"].iloc[i]
    out["best_b_name"], out["best_b_above"] = rb["opponent"].iloc[0], rb["above"].iloc[0]

    pr = pd.read_parquet(S / "prime_elite_board.parquet").set_index("fighter")["elite_level"]
    d = pr[P[0]] - pr[P[1]]
    out.update(prime_a=pr[P[0]], prime_b=pr[P[1]], prime_edge=d, prime_win=1.0 / (1.0 + 10.0 ** (-d / 400.0)))

    g = c["gender"].reindex(h["fighter"]).to_numpy()
    m = h[g != "F"].assign(year=pd.to_datetime(h["event_date"]).dt.year)
    E = year_reference(m.groupby(["fighter", "year"])["mu_whr"].mean().rename("annual_mean").reset_index(),
                       DEFAULT_CAREER_REFERENCE)
    y0, y1 = ERA_YEARS
    out.update(era_lo=E[y0], era_hi=E[y1], era_gap=E[y1] - E[y0])
    return out


def write_readme(F: dict[str, float | str], p: Path) -> None:
    """Update the two narrative paragraphs, requiring exactly one match for each."""
    def n(k: str) -> str:
        return f"{round(F[k]):,}"

    t = p.read_text(encoding="utf-8")
    era = (
        "All-time and Prime read every rating against its own year's contender line. The "
        f"model's scale drifts upward over time: on this fit the 60th-best man stood at {n('era_lo')} "
        f"in 2007 and {n('era_hi')} in 2023, so without this era adjustment a 2023 win would "
        f"be priced on a scale about {5 * round(F['era_gap'] / 5)} points higher than a 2007 win. "
        "Current, whose fighters are all contemporaries, reads the unadjusted ratings."
    )
    points = (
        "**The score is a points total, not a ratio.** "
        f"Jon Jones's {n('score_a')} against Georges St-Pierre's {n('score_b')} does not mean Jones was "
        f"{F['ratio']:.0%} better. It means his three parts add up to more points: title {n('title_a')} "
        f"against {n('title_b')}, résumé {n('resume_a')} against {n('resume_b')}, skill "
        f"{n('skill_a')} against {n('skill_b')}. Most of the résumé gap is two elite wins: "
        f"{F['elite_1_name']} at {n('elite_1_above')} points above the line and {F['elite_2_name']} at "
        f"{n('elite_2_above')}, where St-Pierre's best was {F['best_b_name']} at {n('best_b_above')}. "
        f"For who was better at their best, read Prime: {n('prime_a')} against {n('prime_b')}, an "
        f"{n('prime_edge')}-point edge, which the rating turns into about a {F['prime_win']:.0%} chance of winning."
    )
    for start, value in (
        ("All-time and Prime read every rating", era),
        ("**The score is a points total, not a ratio.**", points),
    ):
        pat = re.escape(start) + r".*?(?=\n\n)"
        found = list(re.finditer(pat, t, flags=re.DOTALL))
        if len(found) != 1:
            raise ValueError(f"expected one README paragraph starting {start!r}; found {len(found)}")
        # Preserve existing line breaks when the data has not changed.
        if " ".join(found[0].group().split()) != value:
            m = found[0]
            t = t[:m.start()] + textwrap.fill(value, width=79) + t[m.end():]
    p.write_text(t, encoding="utf-8")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("snapshot", type=Path, nargs="?", default=PUBLISHED_SNAPSHOT)
    ap.add_argument("--write-readme", action="store_true")
    args = ap.parse_args()
    F = figures(args.snapshot)
    if args.write_readme:
        write_readme(F, Path(__file__).resolve().parents[1] / "README.md")
    for k, v in F.items():
        print(f"{k:16s} {v:.4f}" if isinstance(v, float) else f"{k:16s} {v}")
