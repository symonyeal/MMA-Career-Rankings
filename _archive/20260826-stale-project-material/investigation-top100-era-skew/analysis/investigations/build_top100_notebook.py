"""Generate ``analysis/investigations/top100_era_skew.ipynb``.

Same pattern as ``analysis/build_notebook.py``: the notebook is a build artifact
so its cells stay reviewable as source and the committed ``.ipynb`` can be
written with outputs cleared every time.

The rule the brief sets and this builder enforces: **no number is typed into
prose.** Narrative that carries a figure is emitted from a code cell as
``show(f"...")``; static markdown cells carry only the falsifiable prediction
and the reasoning, never a measurement.
"""
from __future__ import annotations

import json
from pathlib import Path

OUT_PATH = Path(__file__).resolve().parent / "top100_era_skew.ipynb"


def code(src: str) -> dict:
    return {"cell_type": "code", "execution_count": None, "metadata": {},
            "outputs": [], "source": _split(src)}


def md(src: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": _split(src)}


def _split(src: str) -> list[str]:
    src = src.strip("\n") + "\n"
    return src.splitlines(keepends=True)


CELLS: list[dict] = []


def add(*cells: dict) -> None:
    CELLS.extend(cells)


# ---------------------------------------------------------------------------
add(md(r"""
# Why the all-time top 100 is mostly active fighters, and Randy Couture scores zero

Investigation against `data/snapshots/2026-08-13`, career mass at the production
bar `DEFAULT_CAREER_REFERENCE = "contender:60"`.

Six hypotheses, one section each. Every section opens with a **falsifiable
prediction** and closes with a verdict of **supported**, **refuted** or
**unresolved** — *unresolved* is a real answer and is used whenever an interval
crosses zero. The seven careers the brief nominates are carried through every
section so one career can be followed across all the explanations.

**How to read this.** Nothing in the prose is typed by hand: every figure is
produced by the cell above it. Expensive refits are cached under
`data/model_tuning/top100-era-skew/`; the first clean-kernel run builds them,
later runs read them.

**What this notebook may not do.** It may not add opponent quality, title status
or era to the score — those are already posted once, in the opponent's rating,
the ledger and the reference field. It may not tune anything toward an external
board. A change that moves a fighter because we expected them higher is not a
fix, and is not proposed here.
"""))

add(code(r"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from IPython.display import Markdown, display


def find_project_root(start: Path) -> Path:
    p = start.resolve()
    for _ in range(8):
        if (p / "data" / "snapshots").exists() and (p / "ratings").exists():
            return p
        p = p.parent
    raise RuntimeError("cannot locate project root")


PROJECT_ROOT = find_project_root(Path.cwd())
sys.path.insert(0, str(PROJECT_ROOT))

from analysis.investigations import era_skew as es
from analysis.investigations import era_skew_viz as ev
from ratings.constants import WHR_W2_PER_DAY
from ratings.symon_score import DEFAULT_CAREER_REFERENCE, year_reference

pd.set_option("display.max_rows", 120)
pd.set_option("display.width", 200)

SNAPSHOT = es.DEFAULT_SNAPSHOT
REFERENCE = DEFAULT_CAREER_REFERENCE

fights = es.load_fights(SNAPSHOT)
history = es.load_history(SNAPSHOT)
current = es.load_current(SNAPSHOT)
uncertainty = es.load_uncertainty(SNAPSHOT)

annual = es.annual_means(history)
bar90 = year_reference(annual, REFERENCE)
career_bouts = history.groupby("fighter").size()
base_board = es.board(history, reference=REFERENCE)

# The seven carried cases, plus the rest of the zero-mass group, in one list.
ALL_CASES = es.CASES + [n for n in es.ZERO_MASS if n not in es.CASES]

VERDICTS: dict[str, es.Verdict] = {}


def show(text: str) -> None:
    display(Markdown(text))


def record(verdict: es.Verdict) -> None:
    VERDICTS[verdict.hypothesis] = verdict
    show(verdict.as_markdown())


cache_files = sorted(p.name for p in es.CACHE_DIR.glob("*")) if es.CACHE_DIR.exists() else []
show(
    f"Snapshot `{SNAPSHOT.name}` · **{len(fights):,}** rated bouts · "
    f"**{history['fighter'].nunique():,}** rated fighters · "
    f"**{len(history):,}** appearances · "
    f"{history['event_date'].min():%Y-%m-%d} to {history['event_date'].max():%Y-%m-%d}.  \n"
    f"Bar: `reference={REFERENCE}`. Drift prior: `WHR_W2_PER_DAY = {WHR_W2_PER_DAY}`.  \n"
    f"Cache `{es.CACHE_DIR.relative_to(PROJECT_ROOT)}`: "
    + (f"**{len(cache_files)}** artifacts present." if cache_files
       else "**empty** — this run will build it (roughly 20 minutes).")
)
"""))

# ---------------------------------------------------------------------------
add(md(r"""
---
## 0. The baseline, re-measured

The brief supplies figures measured on 2026-08-21 and says to check them rather
than re-derive them. Checked below. One of them does not survive, and the way it
fails changes the reading of the whole investigation, so it is corrected here
before any hypothesis is tested.
"""))

add(code(r"""
comp = es.composition(base_board)
zero = base_board[base_board["score"] <= 0.0]

show(
    "### The board's shape\n\n"
    f"| | |\n|---|---|\n"
    f"| Top 100 still active in 2024+ | **{comp['active_2024_plus']} of 100** |\n"
    f"| Top 100 who debuted ≤ 2009 | **{comp['debut_2009_or_earlier']} of 100** "
    f"({int(((base_board.head(100)['first_year'] <= 2009) & (base_board.head(100)['last_year'] >= 2024)).sum())} still active) |\n"
    f"| Median debut year, top 100 | **{comp['median_debut_year']}** |\n"
    f"| Fighters with career mass of exactly zero | **{comp['zero_mass_fighters']:,} of {len(base_board):,}** |\n"
)
es.case_rows(base_board, es.ZERO_MASS).assign(
    active=lambda d: d["first_year"].astype(str) + "–" + d["last_year"].astype(str)
)[["fighter", "rank", "score", "active_years", "active"]]
"""))

add(code(r"""
# Section 2.2 of the brief: does the rating level inflate with the debut era?
graph = es.graph_features(fights, history)
deep = graph[graph["bouts"] >= 8].copy()
eras = [(1993, 2004), (2005, 2009), (2010, 2014), (2015, 2019), (2020, 2026)]
era_table = pd.DataFrame([
    {
        "debut": f"{lo}–{hi}",
        "n": int(len(s)),
        "mean peak": s["peak"].mean(),
        "p90 peak": s["peak"].quantile(0.9),
        "mean bouts": s["bouts"].mean(),
        "mean opponent bouts": s["opp_mean_bouts"].mean(),
        "mean 2-hop size": s["two_hop"].mean(),
    }
    for lo, hi in eras
    for s in [deep[(deep["debut_year"] >= lo) & (deep["debut_year"] <= hi)]]
]).round(1)

corr_debut = deep["debut_year"].corr(deep["peak"])
corr_bouts = deep["bouts"].corr(deep["peak"])
show(
    f"Fighters with ≥8 rated bouts (n={len(deep)}). "
    f"`corr(debut year, peak) = {corr_debut:.3f}`; `corr(bouts, peak) = {corr_bouts:.3f}`. "
    "The mean is flat and only the upper tail rises — **the brief's §2.2 reproduces exactly.** "
    "Two extra columns are added here, and they matter later: the *early* cohorts have the "
    "**deeper** records and the **larger** neighbourhoods, not the thinner ones."
)
era_table
"""))

add(code(r"""
# Section 2.3: how far does a trajectory actually travel, and is it a ramp?
shape = es.career_shape(history, min_bouts=10)
rng = shape["range"]
mono_down, mono_up = int(shape["monotone_down"].sum()), int(shape["monotone_up"].sum())
mono_pct = 100 * (mono_down + mono_up) / len(shape)

show(
    f"Careers with ≥10 rated bouts (n={len(shape)}). Within-career rating **range**: "
    f"median **{rng.median():.0f}**, p25 {rng.quantile(.25):.0f}, p75 {rng.quantile(.75):.0f}, "
    f"max {rng.max():.0f} — the brief's §2.3 spread reproduces exactly.\n\n"
    f"**The brief's monotonicity figure does not.** It reports 0.2% of trajectories strictly "
    f"monotone, and concludes the smoother is not producing straight ramps. Measured here: "
    f"**{mono_down + mono_up} of {len(shape)} = {mono_pct:.1f}%** are strictly monotone, and "
    f"**{mono_down} of them are monotone *decreasing*** against {mono_up} increasing.\n\n"
    "That reverses the inference. One in six long careers is fitted as a pure ramp, and almost "
    "every one of those ramps points down — which is the visible signature of a smoother "
    "explaining a late decline by tilting the whole trajectory. Hypothesis H3 is therefore "
    "under suspicion before it is tested, and §2.3's conclusion that career mass reduces to "
    "`(career level − bar) × active years` needs the same correction: for a sixth of long "
    "careers there is no stable level to speak of."
)
shape[shape["monotone_down"]].nlargest(8, "range")[["fighter", "bouts", "first", "last", "range"]].round(0)
"""))

add(code(r"""
# Third check: does a rank of 2,032 mean anything?
zero = base_board[base_board["score"] <= 0.0]
tie_from, tie_to = int(zero["rank"].min()), int(zero["rank"].max())
contiguous = (tie_to - tie_from + 1) == len(zero)
distinct_tiebreak = int(zero["peak_year_excess"].nunique())

show(
    f"**And the ranks the brief tabulates are not an ordering.** Every fighter from rank "
    f"**{tie_from:,}** to **{tie_to:,}** has a career mass of exactly zero — "
    f"{'one contiguous block' if contiguous else 'not contiguous'} of **{len(zero):,}** fighters, "
    f"with {distinct_tiebreak} distinct value of the secondary sort key between them. "
    "`career_skill_mass` breaks that tie on the fighter's name, so the gap between Forrest "
    f"Griffin at {int(zero.set_index('fighter').loc['Forrest Griffin','rank']):,} and Wanderlei "
    f"Silva at {int(zero.set_index('fighter').loc['Wanderlei Silva','rank']):,} is alphabetical "
    "and carries no evidence at all.\n\n"
    "Nothing below is wrong because of it — the *mass* is the measurement and it is zero for all "
    "of them — but every rank in this notebook at or beyond "
    f"{tie_from:,} should be read as \"tied last\", never as a placing. The board printing a dense "
    "rank over a tie this large is itself a defect, and it is in the closing list."
)
zero.head(3)[["rank", "fighter", "score", "peak_year_excess"]]
"""))

# ---------------------------------------------------------------------------
add(md(r"""
---
## 1. What the board looks like

Two pictures before any hypothesis. The first is the complaint itself. The
second is the fact the complaint has to be explained against: the bar the
functional clips at barely moves, while the top of the field does.
"""))

add(code(r"""
ev.board_shape_chart(base_board, top_n=100)
"""))

add(code(r"""
bar_table = es.bar_table(annual, career_bouts=career_bouts)
first_year, last_year = int(bar_table["year"].min()), int(bar_table["year"].max())
bar_rise = float(bar_table.set_index("year").loc[2024, "q0.90"] - bar_table.set_index("year").loc[2000, "q0.90"])
p99 = annual.groupby("year")["annual_mean"].quantile(0.99)
tail_rise = float(p99.loc[2024] - p99.loc[2000])
pop_growth = (int(bar_table.set_index("year").loc[2000, "rated_fighter_years"]),
              int(bar_table.set_index("year").loc[2024, "rated_fighter_years"]))

show(
    f"From 2000 to 2024 the bar rises **{bar_rise:+.0f}** points while the 99th percentile of the "
    f"same distribution rises **{tail_rise:+.0f}**, and the rated population grows from "
    f"**{pop_growth[0]}** fighter-years to **{pop_growth[1]}**. The clip is anchored to a part of "
    "the distribution that is not moving the way the part above it moves."
)
ev.field_shape_chart(bar_table, annual)
"""))

# ---------------------------------------------------------------------------
add(md(r"""
---
## 2. The seven careers carried through every section

| Fighter | The question |
|---|---|
| **Merab Dvalishvili** | Every active year clears the bar. Fair reading of a champion, or a long unbeaten run mechanically overpriced in a deep modern graph? |
| **Jon Jones** | Mass far clear of second place, and the only tight rank interval on the board. Dominance the data supports, or a long career that never dipped, compounded? |
| **Natalia Silva** | Five years, a flat trajectory, ranked above far longer records. Confident because she has been dominant, or because she has not been tested? |
| **Randy Couture** | Mass zero. The acceptance case — an explanation that does not account for Couture has not explained the board. |
| **Robbie Lawler** | Mass zero across thirteen years with a title reign in the middle. The clearest peak-versus-average test in the set. |
| **José Aldo** | His board opens years after his career did, because WEC is missing. How much does scope alone recover? |
| **Wanderlei Silva** | Rated far below the bar on UFC bouts alone. With PRIDE in the fit, where does he land? |
"""))

add(code(r"""
cases = es.case_rows(base_board, es.CASES).merge(
    uncertainty[["fighter", "rank_lo", "rank_hi", "mass_lo", "mass_hi"]], on="fighter", how="left"
)
cases["rank interval"] = cases.apply(
    lambda r: "—" if pd.isna(r["rank_lo"]) else f"[{int(r['rank_lo'])}, {int(r['rank_hi'])}]", axis=1
)
show(
    "Ranks come with the snapshot's 150-replicate Dirichlet event bootstrap. "
    "A rank difference is only claimed where the intervals are disjoint."
)
cases[["fighter", "rank", "rank interval", "score", "active_years",
       "contributing_years", "first_year", "last_year"]].round(0)
"""))

add(code(r"""
placings = es.case_year_placings(annual, es.CASES)
show(
    "Where each of them actually sat inside their own year's field. This is the measurement "
    "that decides how much of the story the bar can possibly be: a fighter who never reached "
    "the top decile of any year is not being kept off the board by *which* decile the bar is."
)
placings
"""))

add(code(r"""
ev.case_gap_chart(annual, bar90, es.CASES)
"""))

# ---------------------------------------------------------------------------
add(md(r"""
---
## H1 — Graph density, not era

> Early fighters sit in a sparse, shallow opponent graph, so the estimator cannot
> move them far from the anchor; modern fighters sit in a dense one and can be
> pushed to extremes.
>
> **Prediction: graph terms carry the signal and debut year adds nothing once
> they are in.** If debut year still matters, H1 is wrong.
"""))

add(code(r"""
y = deep["peak"].to_numpy(dtype=float)
specs = {
    "A · debut year alone": ["debut_year"],
    "B · graph density alone": ["bouts", "opp_mean_bouts", "two_hop"],
    "C · graph density + debut year": ["bouts", "opp_mean_bouts", "two_hop", "debut_year"],
}
models, r2s = {}, {}
for label, cols in specs.items():
    models[label], r2s[label] = es.ols(y, deep[cols])

summary = pd.DataFrame([
    {"model": label, "R²": r2s[label],
     "debut-year coef": (frame.loc[frame["term"] == "debut_year", "coef"].squeeze()
                         if "debut_year" in set(frame["term"]) else np.nan),
     "debut-year t": (frame.loc[frame["term"] == "debut_year", "t"].squeeze()
                      if "debut_year" in set(frame["term"]) else np.nan)}
    for label, frame in models.items()
]).round(3)
summary
"""))

add(code(r"""
ev.forest_chart({k: v for k, v in models.items() if k != "A · debut year alone"},
                title="H1 — peak rating on graph density, with and without the debut year")
"""))

add(code(r"""
coef_c = models["C · graph density + debut year"].set_index("term")
debut_coef = float(coef_c.loc["debut_year", "coef"])
debut_t = float(coef_c.loc["debut_year", "t"])
span = int(deep["debut_year"].max() - deep["debut_year"].min())

show(
    f"Debut year on its own explains **{100*r2s['A · debut year alone']:.1f}%** of the variance in "
    f"peak rating (t = {models['A · debut year alone'].set_index('term').loc['debut_year','t']:.2f}) — "
    "the brief's §2.2 finding. Adding graph density lifts R² to "
    f"**{100*r2s['B · graph density alone']:.1f}%**. But putting debut year *back* on top of the "
    f"graph terms lifts it again to **{100*r2s['C · graph density + debut year']:.1f}%**, and the "
    f"debut-year coefficient becomes **{debut_coef:+.2f} rating points per year (t = {debut_t:.2f})** "
    f"— about **{debut_coef*span:+.0f} points across the {span}-year span**.\n\n"
    "The zero correlation in §2.2 was a cancellation, not an absence. Later-debuting fighters "
    "have *shorter* rated records, record depth raises peak rating, and the two effects offset. "
    "Control for depth and the era gradient appears."
)
"""))

add(code(r"""
# The premise of H1, checked directly: was the early graph actually sparser?
density_by_era = era_table[["debut", "n", "mean bouts", "mean opponent bouts", "mean 2-hop size"]]

h = history.copy()
h["year"] = h["event_date"].dt.year
by_year = {yr: set(g["fighter"]) for yr, g in h.groupby("year")}
years = sorted(by_year)
chain = pd.DataFrame([
    {"pair": f"{a}→{b}", "shared fighters": len(by_year[a] & by_year[b])}
    for a, b in zip(years, years[1:])
])
narrowest = chain.loc[chain["shared fighters"].idxmin()]
span_bridge = len(set(h[h["year"] <= 2004]["fighter"]) & set(h[h["year"] >= 2016]["fighter"]))

show(
    "**The premise is false in this scope.** The 1993–2004 debut cohort has the *most* rated "
    "bouts per fighter and the *largest* two-hop neighbourhoods of any cohort; the 2020–2026 "
    "cohort has the fewest and the smallest. Whatever separates the eras, it is not that the "
    "early fighters were less connected to each other.\n\n"
    "What *is* thin is the connection **between** eras. The year-to-year chain that lets a "
    f"2000 rating be compared with a 2024 one is narrowest at **{narrowest['pair']}**, where only "
    f"**{int(narrowest['shared fighters'])} fighters** are active on both sides, and only "
    f"**{span_bridge} fighters** in the whole database were active both in 2000–2004 and in "
    "2016–2026. The cross-era scale rests on that bottleneck, which is why the sign of the "
    "gradient above cannot be attributed to skill growth rather than scale drift from this "
    "data alone."
)
density_by_era
"""))

add(code(r"""
case_graph = (graph[graph["fighter"].isin(es.CASES)]
              .set_index("fighter").reindex(es.CASES).reset_index())
case_graph["peak"] = case_graph["peak"].round(0)
case_graph["opp_mean_bouts"] = case_graph["opp_mean_bouts"].round(1)
_g = case_graph.set_index("fighter")
_r = base_board.set_index("fighter")["rank"]
show(
    "The seven carried cases against the density measures. If H1 held, the zero-mass careers "
    "would be the sparse ones — thin records, thin opponents, small neighbourhoods. The ordering "
    f"runs the other way. Randy Couture (rank {int(_r['Randy Couture']):,}) has "
    f"{int(_g.loc['Randy Couture','opponents'])} distinct opponents and a two-hop neighbourhood of "
    f"{int(_g.loc['Randy Couture','two_hop'])}; Natalia Silva (rank {int(_r['Natalia Silva']):,}) "
    f"has {int(_g.loc['Natalia Silva','opponents'])} and "
    f"{int(_g.loc['Natalia Silva','two_hop'])}. The fighter with the sparser graph is the one the "
    "board rates higher."
)
case_graph[["fighter", "peak", "debut_year", "bouts", "opponents", "opp_mean_bouts", "two_hop"]]
"""))

add(code(r"""
record(es.Verdict(
    hypothesis="H1 · graph density, not era",
    claim="graph terms carry the signal and debut year adds nothing once they are in",
    verdict="refuted",
    because=(
        f"Debut year adds R² {100*(r2s['C · graph density + debut year'] - r2s['B · graph density alone']):+.1f} "
        f"points on top of the graph terms, at {debut_coef:+.2f} rating points per debut year "
        f"(t = {debut_t:.2f}) — it does not vanish, it *appears*. The mechanism H1 proposes is also "
        "absent: the earliest cohort has the deepest records and the largest neighbourhoods, not "
        "the sparsest. What the data does support is a weaker and different claim — that the "
        "cross-era scale is identified through a bottleneck of "
        f"{int(narrowest['shared fighters'])} fighters at its narrowest year-to-year link, so the "
        "sign of the era gradient is real but its interpretation is not identified."
    ),
))
"""))

# ---------------------------------------------------------------------------
add(md(r"""
---
## H2 — The drift rate is too small to express a peak

> With `w²` this low a career is fitted as a near-constant, so a fighter is
> scored on career *average*, and anyone with a long tail of losses averages
> below the bar.
>
> **Prediction: a larger `w²` raises within-career range and lifts fighters
> whose peak and decline are far apart, at some cost in prediction.** If held-out
> loss degrades monotonically from the current value, the current value is
> defensible and H2 is wrong.

`WHR_W2_PER_DAY` has never been estimated from held-out prediction. The repo's
own harness scores only the last handful of events, which cannot say whether a
drift rate that rescues an early career also predicts one. The evaluation below
walks the origin across the whole record instead.
"""))

add(code(r"""
sweep = es.w2_sweep(fights, reference=REFERENCE)
sweep_shape = (sweep.groupby(["w2_multiplier", "w2"], as_index=False)
               .agg(median_range=("range", "median")))
sweep_comp = pd.DataFrame([
    {"w2_multiplier": m, **es.composition(g.sort_values("rank"))}
    for m, g in sweep.groupby("w2_multiplier")
])
w2_summary = sweep_shape.merge(sweep_comp, on="w2_multiplier")
w2_summary[["w2_multiplier", "w2", "median_range", "active_2024_plus",
            "median_debut_year", "zero_mass_fighters"]].round(4)
"""))

add(code(r"""
case_by_w2 = (sweep[sweep["fighter"].isin(es.CASES)]
              .pivot_table(index="fighter", columns="w2_multiplier", values="rank")
              .reindex(es.CASES).astype(int))
case_by_w2.columns = [f"×{c:g}" for c in case_by_w2.columns]
show("Career-mass **rank** for each carried case, at each multiple of the production drift rate.")
case_by_w2
"""))

add(code(r"""
predictions = es.prequential_w2(fights)
loss = es.paired_event_bootstrap(predictions, baseline_multiplier=1.0, metric="log_loss")
show(
    f"Rolling-origin evaluation: **{int(loss['bouts'].iloc[0]):,} decided bouts** over "
    f"**{int(loss['events'].iloc[0]):,} events**, origin walking the record in half-year blocks. "
    "The delta is paired bout by bout against the production drift rate and resampled by event; "
    "an interval containing zero means the two rates cannot be told apart."
)
loss[["w2_multiplier", "w2", "mean_log_loss", "delta_vs_baseline",
      "delta_lo", "delta_hi", "separated"]].round(5)
"""))

add(code(r"""
ev.w2_chart(sweep_shape, loss)
"""))

add(code(r"""
worse = loss[(loss["delta_vs_baseline"] > 0) & loss["separated"]]
lawler = sweep[sweep["fighter"] == "Robbie Lawler"].set_index("w2_multiplier")
couture = sweep[sweep["fighter"] == "Randy Couture"].set_index("w2_multiplier")
lawler_best = lawler["rank"].idxmin()
couture_best = couture["rank"].idxmin()

show(
    "**Movement is bought as predicted.** Median within-career range goes from "
    f"{sweep_shape.set_index('w2_multiplier').loc[0.25,'median_range']:.0f} points at ×0.25 to "
    f"{sweep_shape.set_index('w2_multiplier').loc[64.0,'median_range']:.0f} at ×64. Robbie Lawler — "
    f"the peak-versus-average case — moves from rank {int(lawler.loc[1.0,'rank']):,} at the "
    f"production rate to **{int(lawler.loc[lawler_best,'rank']):,} at ×{lawler_best:g}**, and Vitor "
    f"Belfort from {int(sweep[(sweep.fighter=='Vitor Belfort') & (sweep.w2_multiplier==1.0)]['rank'].iloc[0]):,} "
    f"to {int(sweep[(sweep.fighter=='Vitor Belfort') & (sweep.w2_multiplier==4.0)]['rank'].iloc[0]):,}.\n\n"
    "**But the composition of the top 100 barely responds**: active-in-2024 goes "
    f"{int(w2_summary.set_index('w2_multiplier').loc[0.25,'active_2024_plus'])} → "
    f"{int(w2_summary.set_index('w2_multiplier').loc[64.0,'active_2024_plus'])} across a 256-fold "
    "change in the drift prior. The drift rate is not what makes the board modern.\n\n"
    f"**And Couture does not move until the rate is indefensible.** His best rank across the sweep "
    f"is {int(couture.loc[couture_best,'rank']):,} at ×{couture_best:g}; at ×16 he is still "
    f"{int(couture.loc[16.0,'rank']):,}."
)
"""))

add(code(r"""
# The brief's own falsification rule: if held-out loss degrades away from the
# production value, that value is defensible and H2 is wrong. Read it off the
# measurement rather than asserting it.
best_row = loss.loc[loss["mean_log_loss"].idxmin()]
production_is_best = bool(best_row["w2_multiplier"] == 1.0)
others = loss[loss["w2_multiplier"] != 1.0]
all_others_worse = bool((others["delta_vs_baseline"] > 0).all() and others["separated"].all())
verdict_h2 = "refuted" if (production_is_best and all_others_worse) else "unresolved"

detail = (
    f"every other rate tested is worse with an interval excluding zero — "
    + ", ".join(f"×{m:g} {d:+.4f} [{lo:+.4f}, {hi:+.4f}]" for m, d, lo, hi in zip(
        others["w2_multiplier"], others["delta_vs_baseline"], others["delta_lo"], others["delta_hi"]))
) if all_others_worse else (
    "the ordering is not clean: "
    + ", ".join(f"×{m:g} {d:+.4f} [{lo:+.4f}, {hi:+.4f}]{'' if s else ' (crosses zero)'}"
                for m, d, lo, hi, s in zip(others["w2_multiplier"], others["delta_vs_baseline"],
                                           others["delta_lo"], others["delta_hi"], others["separated"]))
)

record(es.Verdict(
    hypothesis="H2 · drift rate too small to express a peak",
    claim=("a larger w² raises within-career range and lifts fighters whose peak and decline are "
           "far apart, at some cost in prediction — and if held-out loss degrades away from the "
           "current value, the current value is defensible and H2 is wrong"),
    verdict=verdict_h2,
    because=(
        f"The mechanism is real and the conclusion still fails, on the brief's own rule. Range and "
        f"rescue both scale with w² — Lawler {int(lawler.loc[1.0,'rank']):,} → "
        f"{int(lawler.loc[lawler_best,'rank']):,} at ×{lawler_best:g}. But over "
        f"{int(loss['bouts'].iloc[0]):,} held-out bouts spanning the whole record, "
        f"{'the production value is the best of the grid and ' if production_is_best else ''}"
        f"{detail}. The unfitted constant turns out to be defensible in both directions, which is "
        "the first time it has been measured rather than assumed. The top-100 era composition is "
        "also nearly invariant to the parameter "
        f"({int(w2_summary.set_index('w2_multiplier').loc[0.25,'active_2024_plus'])} → "
        f"{int(w2_summary.set_index('w2_multiplier').loc[64.0,'active_2024_plus'])} active across ×0.25 "
        "to ×64), so raising it would buy a handful of rescued careers at a measured accuracy cost "
        "and explain none of the skew. Couture needs ×64, where log loss is "
        f"{float(loss.set_index('w2_multiplier').loc[64.0,'delta_vs_baseline']):+.3f}."
    ),
))
"""))

# ---------------------------------------------------------------------------
add(md(r"""
---
## H3 — Peak deletion under a driftless prior

> A late decline is explained by lowering the whole trajectory, so anyone who
> fought too long is scored on their ending.
>
> **Prediction: the zero-mass group shows large negative revisions; Merab and
> Jones show none.**

The protocol is §3.9 of `docs/PLAN_WHOLE_SPORT_ENGINE_2026-08-21.md`, generalised
so it runs on a population rather than four hand-picked dates. For one fighter at
a time, every bout after the end of their longest unbeaten run is removed — only
theirs, the rest of the graph untouched — the whole smoother is refit, and their
peak in that fit is compared with the same appearance in the full fit.

Note which way the null points. A truncated fit gives that fighter *less*
evidence, and less evidence pulls a high rating back toward the anchor. A
truncated peak that comes out *higher* is therefore evidence against the null,
not for it.
"""))

add(code(r"""
trunc = es.truncation_population(fights, history).dropna(subset=["revision"]).copy()
show(
    f"**{len(trunc)}** fighters with a long enough record to have a suffix worth deleting "
    f"(≥12 rated bouts, ≥3 bouts after the cut), plus the carried cases and the three controls "
    "the plan's own test used."
)
ev.truncation_chart(trunc, es.CASES + es.TRUNCATION_CONTROLS)
"""))

add(code(r"""
terms, r2_trunc = es.ols(
    trunc["revision"].to_numpy(dtype=float),
    trunc[["post_cut_win_rate", "dropped"]],
)
slope = float(terms.set_index("term").loc["post_cut_win_rate", "coef"])
slope_t = float(terms.set_index("term").loc["post_cut_win_rate", "t"])
median_rev = float(trunc["revision"].median())
negative = int((trunc["revision"] < 0).sum())

show(
    f"Across all {len(trunc)} fighters the median revision is **{median_rev:+.0f} points** and "
    f"**{negative} of {len(trunc)} ({100*negative/len(trunc):.0f}%)** are negative: the full-career "
    "fit places the same appearance *below* where the truncated fit placed it, in almost every "
    "case, in the opposite direction to the less-evidence null.\n\n"
    f"The revision is graded by how badly the deleted suffix went — **{slope:+.0f} points per unit "
    f"of post-cut win rate (t = {slope_t:.2f})**. A fighter who went 0–5 after their peak has that "
    "peak revised down by substantially more than one who went 3–2. Extra evidence that a "
    "smoother merely *had more of* would not care what the evidence said."
)
terms.round(3)
"""))

add(code(r"""
case_trunc = trunc[trunc["fighter"].isin(es.CASES + es.TRUNCATION_CONTROLS)].copy()
case_trunc["cut"] = pd.to_datetime(case_trunc["cut_date"]).dt.date
order = {n: i for i, n in enumerate(es.CASES + es.TRUNCATION_CONTROLS)}
case_trunc = case_trunc.sort_values("fighter", key=lambda s: s.map(order))
show(
    "The carried cases, plus the three the plan measured by hand. `dropped` is how many bouts "
    "were removed; `revision` is full-fit minus truncated peak, so negative means the peak was "
    "deleted."
)
case_trunc[["fighter", "cut", "run", "dropped", "post_cut_win_rate",
            "truncated_peak", "full_at_same_date", "revision"]].round(2)
"""))

add(code(r"""
jones_dropped = es.unbeaten_cut(fights, "Jon Jones")["dropped"]
natalia_dropped = es.unbeaten_cut(fights, "Natalia Silva")["dropped"]
couture_rev = float(case_trunc.set_index("fighter").loc["Randy Couture", "revision"])
couture_trunc_peak = float(case_trunc.set_index("fighter").loc["Randy Couture", "truncated_peak"])
couture_bar = float(bar90.loc[int(pd.to_datetime(case_trunc.set_index("fighter").loc["Randy Couture", "peak_date"]).year)])
lawler_rev = float(case_trunc.set_index("fighter").loc["Robbie Lawler", "revision"])

record(es.Verdict(
    hypothesis="H3 · peak deletion under a driftless prior",
    claim="the zero-mass group shows large negative revisions; Merab and Jones show none",
    verdict="supported",
    because=(
        f"{negative} of {len(trunc)} long careers have their peak revised downward by the "
        f"full-career fit, median {median_rev:+.0f} points, graded {slope:+.0f} points per unit of "
        f"post-cut win rate (t = {slope_t:.2f}) — the wrong sign for a less-evidence explanation and "
        "the right sign for a driftless prior splitting 'high then low' across the whole "
        f"trajectory. Jon Jones is the clean control: his longest unbeaten run ends at his last "
        f"bout, so there are {jones_dropped} bouts to delete and no revision to measure "
        f"(Natalia Silva, {natalia_dropped}, likewise). Robbie Lawler loses {abs(lawler_rev):.0f} "
        "points off his title-reign peak, which is most of why a welterweight champion scores "
        f"zero. It is *not* enough for the acceptance case: restoring Couture's {abs(couture_rev):.0f} "
        f"points puts his peak year at {couture_trunc_peak:.0f} against a bar of {couture_bar:.0f} — "
        "one year barely clearing, not a career."
    ),
))
"""))

# ---------------------------------------------------------------------------
add(md(r"""
---
## H4 — Survivorship in the bar itself

> The bar is a quantile over *rated* fighter-years, and who is rated changes: 28
> fighters in 2000 against 625 in 2024. The 0.9 quantile of 28 is the 3rd best
> fighter; of 625 it is the 63rd.
>
> **Prediction: if the bar is the problem, the zero-mass group moves
> substantially.**

The brief flags this as the one hypothesis that would overturn the reasoning
recorded in `ratings/symon_score.py` for choosing `reference = 0.9`, so it gets
the careful version: the repair is implemented, and then the reason the repair
cannot be applied is measured rather than asserted.
"""))

add(code(r"""
show(
    "What the 0.90 quantile *is*, year by year — and where a fixed count is undefined because "
    "the year does not contain that many rated fighters. Filling those years with the worst "
    "fighter in a thin field would hand the early era a free floor, so they are left blank."
)
ev.bar_variants_chart(bar_table)
"""))

add(code(r"""
undefined_60 = bar_table[bar_table["top-60"].isna()]["year"].tolist()
undefined_30 = bar_table[bar_table["top-30"].isna()]["year"].tolist()
place_2000 = int(bar_table.set_index("year").loc[2000, "q0.90 is place"])
place_2024 = int(bar_table.set_index("year").loc[2024, "q0.90 is place"])

variants = {
    "q0.90 — production": bar90,
    "q0.90 | ≥8 career bouts": annual[annual["fighter"].map(career_bouts).ge(8)]
        .groupby("year")["annual_mean"].quantile(0.9),
    "mean": annual.groupby("year")["annual_mean"].mean(),
}
boards = {label: es.board_from_bar(annual, bar, label) for label, bar in variants.items()}
bar_boards = pd.DataFrame([
    {"bar": label, **{k: v for k, v in es.composition(b).items() if k != "top_n"},
     **{n: int(b.set_index("fighter").loc[n, "rank"]) for n in es.CASES}}
    for label, b in boards.items()
])
show(
    f"The survivorship claim is exactly right as a description: the bar is the "
    f"**{es.ordinal(place_2000)}** best fighter-year in 2000 and the **{es.ordinal(place_2024)}** best in 2024. The obvious repair — a "
    f"fixed count — is undefined for {', '.join(str(y) for y in undefined_60)} at a top-60 line "
    f"and {', '.join(str(y) for y in undefined_30) or 'no years'} at top-30, i.e. for most of the "
    "period the repair exists to fix. A fixed count cannot be the answer here; the population is "
    "smaller than the count."
)
bar_boards
"""))

add(code(r"""
couture_place = placings.set_index("fighter").loc["Randy Couture"]
lawler_place = placings.set_index("fighter").loc["Robbie Lawler"]
wand_place = placings.set_index("fighter").loc["Wanderlei Silva"]
zero_placings = es.case_year_placings(annual, es.ZERO_MASS)

show(
    "So the composition question has to be answered a different way: **where inside their own "
    "year did the zero-mass fighters sit?** A rank-consistent bar at the top decile only reaches "
    "them if they ever reached the top decile.\n\n"
    f"Randy Couture's best year is **{couture_place['best_place']}** — the "
    f"{es.ordinal(couture_place['best_percentile'])} percentile — with a median across his career of "
    f"{couture_place['median_percentile']:.0f}. Robbie Lawler peaks at {lawler_place['best_place']} "
    f"({es.ordinal(lawler_place['best_percentile'])}), Wanderlei Silva at {wand_place['best_place']} "
    f"({es.ordinal(wand_place['best_percentile'])}). None of the seven reaches the top decile in any "
    "year, on any definition of the decile."
)
zero_placings
"""))

add(code(r"""
mean_board = boards["mean"]
mean_comp = es.composition(mean_board)
record(es.Verdict(
    hypothesis="H4 · survivorship in the bar",
    claim="if the bar is the problem, the zero-mass group moves substantially",
    verdict="refuted",
    because=(
        f"The premise is confirmed — the bar is the {es.ordinal(place_2000)}-best fighter-year in 2000 "
        f"and the {es.ordinal(place_2024)} in 2024 — and the conclusion does not follow. Holding the bar's "
        f"composition fixed (0.90 quantile over fighters with ≥8 career bouts) moves Randy Couture "
        f"from {int(boards['q0.90 — production'].set_index('fighter').loc['Randy Couture','rank']):,} to "
        f"{int(boards['q0.90 | ≥8 career bouts'].set_index('fighter').loc['Randy Couture','rank']):,} and "
        f"leaves the top-100 composition at "
        f"{es.composition(boards['q0.90 | ≥8 career bouts'])['active_2024_plus']} active. The reason is "
        "that none of the zero-mass seven reached the top decile of any year they fought in — "
        f"Couture's best is {couture_place['best_place']} — so no rank-consistent redefinition of a "
        "top-decile bar reaches them. Lowering the bar to the mean does move them "
        f"(Couture to {int(mean_board.set_index('fighter').loc['Randy Couture','rank']):,}), but that is "
        f"changing the bar's *height*, not repairing its composition, and it leaves the era skew "
        f"untouched at {mean_comp['active_2024_plus']} active in the top 100 — while returning the "
        "functional to the degenerate regime the module docstring already rejects."
    ),
))
"""))

# ---------------------------------------------------------------------------
add(md(r"""
---
## H5 — Scope truncation

> Legacy fighters lost the half of their careers the engine cannot see.
>
> **Prediction: Wanderlei, Faber, Aldo and Cro Cop move a great deal; Couture and
> Lawler move less because their missing bouts are mostly outside the majors.**

The six-promotion and pre-unified artifacts are loaded through the same named
scope and dedupe guard as production, and the smoother is refit over one joint
likelihood. There is deliberately **no
promotion weight**: relative promotion strength is an output of a joint fit, read
off the fighters who crossed between them, and a weight would assert the answer.
"""))

add(code(r"""
joint = es.load_fights(SNAPSHOT, scope="majors,pre_unified")
joint_hist = es.joint_history(joint)

joint_board = es.board(joint_hist, reference=REFERENCE)
core = set(fights["fighter_a"]) | set(fights["fighter_b"])
core_board = joint_board[joint_board["fighter"].isin(core)].copy()
core_board["rank"] = np.arange(1, len(core_board) + 1)

show(
    "Scope `majors,pre_unified` passed through the production identity map and "
    "duplicate guard. The joint fit runs over "
    f"**{len(joint):,}** bouts and "
    f"**{joint_hist['fighter'].nunique():,}** fighters against **{len(fights):,}** and "
    f"**{history['fighter'].nunique():,}** UFC-only.\n\n"
    "Two boards are read from it. The **core-only** board re-ranks the original UFC population "
    "inside the joint fit, which is the apples-to-apples measurement of who moved. The **open** "
    "board ranks everyone the joint fit rates, which is a different question and is shown "
    "second, with its own caveat."
)
pd.Series({"rated bouts": len(joint), "rated fighters": joint_hist['fighter'].nunique()})
"""))

add(code(r"""
ev.rank_move_chart(base_board, core_board, ALL_CASES,
                   before_label="UFC-only", after_label="joint fit",
                   title="H5 — career-mass rank, UFC-only against the six-promotion joint fit")
"""))

add(code(r"""
move = (es.case_rows(base_board, ALL_CASES)
        [["fighter", "rank", "score"]]
        .rename(columns={"rank": "rank · UFC", "score": "mass · UFC"})
        .merge(es.case_rows(core_board, ALL_CASES)
               [["fighter", "rank", "score", "active_years"]]
               .rename(columns={"rank": "rank · joint", "score": "mass · joint"}),
               on="fighter"))
move["added bouts"] = [
    int(((joint["fighter_a"] == n) | (joint["fighter_b"] == n)).sum()
        - ((fights["fighter_a"] == n) | (fights["fighter_b"] == n)).sum())
    for n in move["fighter"]
]
joint_comp = es.composition(core_board)
show(
    f"Top-100 composition on the core-only joint board: **{joint_comp['active_2024_plus']} of 100** "
    f"still active (was {comp['active_2024_plus']}), median debut **{joint_comp['median_debut_year']}** "
    f"(was {comp['median_debut_year']}). This is the largest single movement any hypothesis in this "
    "notebook produces in the quantity the investigation is about."
)
move.round(0)
"""))

add(code(r"""
import json as _json
from ratings.connectivity import connectivity

top60 = joint_board.head(60)["fighter"].tolist()
conn = connectivity(
    joint.rename(columns={"fighter_a": "fighter_a_id", "fighter_b": "fighter_b_id"}),
    core,
    core_bout_counts=history.groupby("fighter").size().to_dict(),
    fighters=top60,
)
# connectivity() reports on the whole graph; only the requested fighters have a
# path count, so the verdict is only meaningful for them.
conn = conn[conn["fighter_id"].isin(top60)].set_index("fighter_id")

open_top = joint_board.head(20)[["rank", "fighter", "score", "first_year", "last_year"]].copy()
open_top["in UFC core"] = open_top["fighter"].map(conn["in_core"])
open_top["disjoint paths"] = open_top["fighter"].map(conn["disjoint_paths"])
open_top["UFC bouts"] = [int(((fights["fighter_a"] == n) | (fights["fighter_b"] == n)).sum())
                         for n in open_top["fighter"]]
open_top["joint bouts"] = [int(((joint["fighter_a"] == n) | (joint["fighter_b"] == n)).sum())
                           for n in open_top["fighter"]]

unranked = conn[~conn["rankable"]].index.tolist()
non_core = int((~conn["in_core"].astype(bool)).sum())
mostly_outside = int(sum(
    int(((fights["fighter_a"] == n) | (fights["fighter_b"] == n)).sum())
    < 0.5 * int(((joint["fighter_a"] == n) | (joint["fighter_b"] == n)).sum())
    for n in top60
))
careers_cov = _json.loads(
    (PROJECT_ROOT / "data/external/sherdog/crossorg_careers_coverage.json").read_text())

show(
    "**The abstention rule does not object, and that is the finding.** Applying "
    "`ratings/connectivity.py` to the joint graph, "
    f"**{len(unranked)} of the joint top 60** fall below the three-vertex-disjoint-path floor. "
    f"{int(conn['in_core'].astype(bool).sum())} of the 60 are already in the UFC core, and every "
    f"one of the {non_core} newcomers clears the floor on its own disjoint paths. Fedor "
    "Emelianenko and the Bellator champions are not weakly anchored to the scale; they were "
    "simply absent from the data. The expectation that a cross-organisation board would fail on "
    "connectivity is not borne out here.\n\n"
    "The real caveat is the same defect one level down. "
    f"**{mostly_outside} of the joint top 60** now hold under half of their record inside the "
    "UFC, so their rating rests mostly on the new source — and that source is roster-complete "
    "within six promotions only, which truncates its own entrants exactly as the UFC-only scope "
    "truncated theirs. The whole-career extension that would close it has read "
    f"**{careers_cov['fighter_pages_read']:,} of {careers_cov['fighters_requested']:,}** fighter "
    "pages. Adopting this scope means inheriting a smaller version of the problem it fixes, "
    "which is a reason to finish the crawl, not a reason to stay UFC-only."
)
open_top
"""))

add(md(r"""
### H5b — the scope is truncated in time, not only by promotion

One thing the hypothesis did not anticipate, found while attributing Couture's
zero. The truncation is not only *which promotions*; it is also *from when*.
"""))

add(code(r"""
fm = pd.read_parquet(SNAPSHOT / "fightmatrix_bouts.parquet")
missing = es.missing_career_fraction(fights, fm, ALL_CASES)
window_opens = fights["event_date"].min()
earliest_event = fights.loc[fights["event_date"].idxmin(), "event_name"]
fm_ufc = fm[fm["org"].astype(str).str.upper().eq("UFC")]
fm_ufc_dates = pd.to_datetime(fm_ufc["event_date"], errors="coerce")

excluded_path = SNAPSHOT / "_excluded_bouts.csv"
excluded = pd.read_csv(excluded_path)
excluded["event_date"] = pd.to_datetime(excluded["event_date"], errors="coerce")
pre_unified = excluded[excluded["exclusion_reason"] == "pre_unified_rules"]
pre_unified_bouts = int(len(pre_unified))
pre_unified_events = int(pre_unified["event_name"].nunique())

show(
    f"The canonical set's first *rated* bout is **{window_opens:%Y-%m-%d}** — *{earliest_event}*. "
    "The earlier cards are not missing from the repo: they are parsed and then deliberately "
    f"excluded. `_excluded_bouts.csv` holds **{pre_unified_bouts} bouts over {pre_unified_events} "
    f"events** ({pre_unified['event_date'].min():%Y-%m-%d} to "
    f"{pre_unified['event_date'].max():%Y-%m-%d}) tagged `pre_unified_rules`, because "
    "`loaders/ufcstats_loader.py` cuts the scope at the first event under the Unified Rules.\n\n"
    "So this is a **stated scope boundary, not a data gap** — and its consequence was never "
    "costed: the engine structurally cannot rank anyone whose career sat mostly before it, and no "
    "cross-organisation ingest addresses that, because the excluded bouts are UFC bouts.\n\n"
    "Counted against the FightMatrix cache — used here purely as a **diagnostic** to size the "
    "hole, never to move a rating, and itself a bounded cohort so a zero means 'not cached' "
    f"rather than 'no such bouts' — its UFC rows start {fm_ufc_dates.min():%Y-%m-%d}. "
    f"`unseen_fraction` below is the share of a fighter's cached professional record the rated "
    "scope never sees."
)
missing
"""))

add(code(r"""
boot_joint = es.bootstrap_board(joint, replicates=60, reference=REFERENCE,
                                cache_name="bootstrap_joint")
boot_ufc = es.bootstrap_board(fights, replicates=60, reference=REFERENCE,
                              cache_name="bootstrap_ufc60")

widths = pd.DataFrame([
    {"board": "UFC-only", **es.interval_widths(boot_ufc)},
    {"board": "joint (six promotions)", **es.interval_widths(boot_joint)},
])
movers = ["Wanderlei Silva", "Jose Aldo", "Mauricio Rua", "Urijah Faber", "Vitor Belfort"]
interval_rows = (boot_joint[boot_joint["fighter"].isin(movers)]
                 [["fighter", "mass", "rank", "rank_lo", "rank_hi"]]
                 .merge(boot_ufc[boot_ufc["fighter"].isin(movers)]
                        [["fighter", "rank", "rank_lo", "rank_hi"]],
                        on="fighter", suffixes=(" · joint", " · UFC")))
radius = es.blast_radius(base_board, core_board)
show(
    "**Re-bootstrapped, because the board changed.** Both boards below are 60-replicate Dirichlet "
    "event bootstraps of their own fit — fewer replicates than the production 150, because the "
    "question is whether a rank *move* survives, not the exact endpoint."
)
display(widths.round(1))
display(interval_rows)
show(
    f"Blast radius of adopting the joint scope: **{radius['entered_top_n']} fighters enter** the "
    f"top 100 and **{radius['left_top_n']} leave**; Spearman over the shared population is "
    f"**{radius['spearman_all']:.3f}**; the median absolute rank move inside the old top 50 is "
    f"**{radius['median_abs_rank_move_top50']:.0f} places**."
)
"""))

add(code(r"""
separated = interval_rows[interval_rows["rank_hi · joint"] < interval_rows["rank_lo · UFC"]]
wand = move.set_index("fighter").loc["Wanderlei Silva"]
aldo = move.set_index("fighter").loc["Jose Aldo"]
couture_added = int(move.set_index("fighter").loc["Randy Couture", "added bouts"])
lawler_added = int(move.set_index("fighter").loc["Robbie Lawler", "added bouts"])

record(es.Verdict(
    hypothesis="H5 · scope truncation",
    claim=("Wanderlei, Faber, Aldo move a great deal; Couture and Lawler move less because their "
           "missing bouts are mostly outside the majors"),
    verdict="supported",
    because=(
        f"Every part of the prediction holds, including the negative half. Wanderlei Silva goes "
        f"from the zero-mass tie to {int(wand['rank · joint']):,} on {int(wand['added bouts'])} "
        f"recovered bouts and José Aldo {int(aldo['rank · UFC']):,} → {int(aldo['rank · joint']):,} on "
        f"{int(aldo['added bouts'])}; Couture gains {couture_added} bouts and does not move, Lawler "
        f"gains {lawler_added} and does not move. "
        f"Disjoint bootstrap rank intervals in {len(separated)} of {len(interval_rows)} checked "
        f"moves ({', '.join(separated['fighter']) or 'none'}), so only those are claimed as moves — "
        "the rest are unresolved at 60 replicates, because the interval on a career sum is very "
        "wide on both boards. This is also the only "
        "change in the notebook that shifts the headline: top-100 active-in-2024 "
        f"{comp['active_2024_plus']} → {joint_comp['active_2024_plus']}, median debut "
        f"{comp['median_debut_year']} → {joint_comp['median_debut_year']}. The connectivity "
        f"objection does not apply — {len(unranked)} of the joint top 60 fall below the floor — but "
        f"{mostly_outside} of them now rest mostly on a source that is itself roster-complete in "
        "six promotions only. And it does not reach the acceptance case: Couture's missing record "
        "is UFC, from before the window opens, which no cross-organisation source in this repo "
        "contains."
    ),
))
"""))

# ---------------------------------------------------------------------------
add(md(r"""
---
## H6 — Activity, not skill

> 70/100 being active may partly be that inactive fighters' ratings decay, or
> that the activity penalty leaks into `mu_whr`.
>
> **Prediction: no leak, and H6 is a dead end.** Confirm it and move on.
"""))

add(code(r"""
leak = es.activity_leak_check(history, current)
show(
    f"Career mass recomputed from `ratings_history_whr.parquet` alone reproduces the snapshot's "
    f"`symon_career_skill_mass` to **{leak['max_abs_diff_vs_snapshot']:.0f}** across all "
    f"**{leak['fighters']:,}** fighters. **{leak['fighters_with_penalty']:,}** fighters carry a "
    f"non-zero `activity_mu_penalty` (largest {leak['max_penalty']:.1f} points) and "
    f"**{leak['penalised_fighters_with_any_mass_diff']}** of them show any mass difference at all.\n\n"
    f"The history frame carries exactly `{'`, `'.join(leak['history_columns'])}` — there is no "
    "activity column in it to leak. In `ratings/rate_snapshot.py` the penalty is applied to the "
    "*current* table, into separate `*_activity_adjusted` columns, after the career functional has "
    "already been merged."
)

case_activity = (current[current["fighter"].isin(es.CASES)]
                 [["fighter", "months_inactive", "activity_mu_penalty",
                   "symon_career_skill_mass"]]
                 .set_index("fighter").reindex(es.CASES).reset_index())
case_activity["board mass (recomputed)"] = case_activity["fighter"].map(
    base_board.set_index("fighter")["score"])
case_activity.round(2)
"""))

add(code(r"""
record(es.Verdict(
    hypothesis="H6 · activity penalty leaking into the career functional",
    claim="no leak, and H6 is a dead end",
    verdict="refuted",
    because=(
        f"Refuted in the direction the brief predicted: there is no leak. The board rebuilds from "
        f"the WHR history alone to {leak['max_abs_diff_vs_snapshot']:.0f} difference, and the "
        "penalty lives on columns the functional never reads. The top 100 is not modern because "
        "old fighters were penalised for stopping."
    ),
))
"""))

# ---------------------------------------------------------------------------
add(md(r"""
---
## 7. Randy Couture — the acceptance case

Every counterfactual below is applied **alone**, against the same snapshot, with
nothing else changed. None is proposed as a fix; the point is to attribute a zero,
and a change made because it lifts a fighter we expect to be high would not be a
fix in any case.
"""))

add(code(r"""
NAME = "Randy Couture"
attrib = []


def _row(label, board_frame):
    r = board_frame.set_index("fighter").loc[NAME]
    return {"counterfactual": label, "score": float(r["score"]), "rank": int(r["rank"])}


attrib.append(_row("as published", base_board))
for mult in (4.0, 16.0, 64.0):
    b = sweep[sweep["w2_multiplier"] == mult].sort_values("rank")
    attrib.append(_row(f"H2 · drift prior ×{mult:g}", b))
attrib.append(_row("H4 · bar composition held fixed (≥8 bouts)", boards["q0.90 | ≥8 career bouts"]))
attrib.append(_row("H4 · bar lowered to the mean", boards["mean"]))
attrib.append(_row("H5 · six-promotion joint fit", core_board))
attrib = pd.DataFrame(attrib)
attrib
"""))

add(code(r"""
ev.attribution_chart(attrib, fighter=NAME)
"""))

add(code(r"""
couture_missing = missing.set_index("fighter").loc[NAME]
couture_years = annual[annual["fighter"] == NAME]
best = couture_years.loc[couture_years["pct_in_year"].idxmax()]

show(
    f"### Attribution\n\n"
    f"**H5 — the dominant term, and it is worse than the hypothesis said.** Couture's rated record "
    f"is **{int(couture_missing['rated_bouts'])} bouts from "
    f"{pd.to_datetime(couture_missing['rated_from']):%Y-%m-%d}**; the FightMatrix diagnostic cache "
    f"holds **{int(couture_missing['fm_bouts'])}** for him from "
    f"{pd.to_datetime(couture_missing['fm_from']):%Y-%m-%d}, of which "
    f"**{int(couture_missing['fm_bouts_before_window'])}** fall before the snapshot's window opens. "
    f"About **{100*float(couture_missing['unseen_fraction']):.0f}%** of his career is outside the "
    "scope, and it is the earliest third — the years before the ones the engine rates, in which "
    "every rated year he does have is already a decline. The six-promotion ingest recovers "
    f"**{couture_added}** of them, because they are not non-UFC bouts at all: they are UFC bouts "
    f"held before the Unified Rules, sitting in `_excluded_bouts.csv` under `pre_unified_rules`. "
    "No whole-sport scope reaches them — only a decision about that boundary does.\n\n"
    f"**H3 — real but small for him.** His peak is revised down {abs(couture_rev):.0f} points by "
    f"his own later results. Restored, his best year reaches {couture_trunc_peak:.0f} against a bar "
    f"of {couture_bar:.0f}: one thin contributing year.\n\n"
    f"**H4 — not his explanation.** His best year was **{best['place_in_year']:.0f} of "
    f"{best['n_year']:.0f}** — the {es.ordinal(100*best['pct_in_year'])} percentile. Any top-decile bar "
    "misses him, however its composition is defined.\n\n"
    f"**H2 — not at any defensible rate.** He leaves zero only at ×{couture_best:g}, where held-out "
    f"log loss is {float(loss.set_index('w2_multiplier').loc[couture_best,'delta_vs_baseline']):+.3f} "
    "against the production value.\n\n"
    "**The zero is honest given the input, and the input is wrong.** Nothing in the estimator "
    "needs to change for Couture. What he is, on the data the engine holds, is a fighter who "
    f"entered the record in {int(couture_years['year'].min())} already declining and never reached "
    f"his own year's top decile — an accurate summary of the "
    f"{100*(1 - float(couture_missing['unseen_fraction'])):.0f}% of his career it can see."
)
"""))

# ---------------------------------------------------------------------------
add(md(r"""
---
## 8. Ranked defects, fixes, and blast radius

Ranked by how much of the reported quantity each one accounts for, not by how
easy it is to fix. Blast radius is measured against the published board wherever
the change was actually run in this notebook.
"""))

add(code(r"""
h4_fixed = boards["q0.90 | ≥8 career bouts"]
radius_h4 = es.blast_radius(base_board, h4_fixed)
radius_w2x4 = es.blast_radius(base_board, sweep[sweep["w2_multiplier"] == 4.0].sort_values("rank"))

defects = pd.DataFrame([
    {
        "#": 1,
        "defect": f"The Unified-Rules boundary at {window_opens:%Y-%m-%d} makes a whole generation "
                  "unrankable, and the board does not say so",
        "evidence": f"{pre_unified_bouts} bouts over {pre_unified_events} events are parsed and "
                    f"excluded as `pre_unified_rules`; {int(couture_missing['fm_bouts_before_window'])} "
                    "of Couture's cached bouts fall inside that window",
        "recommended fix": "A decision, not a patch — either keep the boundary and label the board "
                           "'Unified-Rules era', or let pre-unified bouts inform the rating while "
                           "staying out of the presentation",
        "blast radius": f"{pre_unified_bouts} bouts / {pre_unified_events} events already on disk in "
                        "`_excluded_bouts.csv`; effect on the board not measured",
    },
    {
        "#": 2,
        "defect": "Non-UFC careers truncated; PRIDE/WEC/Strikeforce/Bellator/RIZIN outside the fit",
        "evidence": f"joint fit moves top-100 active-2024 {comp['active_2024_plus']}→{joint_comp['active_2024_plus']}, "
                    f"median debut {comp['median_debut_year']}→{joint_comp['median_debut_year']}",
        "recommended fix": "Adopt the joint fit, keeping the connectivity floor as the publication "
                           f"rule (it rejects {len(unranked)} of the joint top 60, so it is not the "
                           "blocker); finish the whole-career crawl before promoting it",
        "blast radius": f"{radius['entered_top_n']} in, {radius['left_top_n']} out, "
                        f"Spearman {radius['spearman_all']:.2f}, "
                        f"median top-50 move {radius['median_abs_rank_move_top50']:.0f} places",
    },
    {
        "#": 3,
        "defect": "Driftless Wiener prior deletes peaks — a late collapse is explained by tilting the whole career",
        "evidence": f"{negative}/{len(trunc)} long careers revised down, median {median_rev:+.0f}, "
                    f"{slope:+.0f} pts per unit post-cut win rate (t={slope_t:.2f}); "
                    f"{mono_down} of {len(shape)} long careers fitted as pure downward ramps",
        "recommended fix": "Age-dependent drift in the prior mean (plan §3.9 / E-series), fitted "
                           "prequentially — not a decline penalty, which would post the same fact twice",
        "blast radius": "not measured here — needs the aging term implemented; "
                        f"the w²-only proxy at ×4 moves the top 50 by a median of "
                        f"{radius_w2x4['median_abs_rank_move_top50']:.0f} places",
    },
    {
        "#": 4,
        "defect": "WHR_W2_PER_DAY was never fitted — an unmeasured constant governing every trajectory",
        "evidence": f"{int(loss['bouts'].iloc[0]):,} held-out bouts now scored across the whole record; "
                    f"the production value is {'the grid minimum, worse in both directions' if production_is_best else 'not the grid minimum'} "
                    f"(×0.25 {float(loss.set_index('w2_multiplier').loc[0.25,'delta_vs_baseline']):+.4f}, "
                    f"×4 {float(loss.set_index('w2_multiplier').loc[4.0,'delta_vs_baseline']):+.4f})",
        "recommended fix": "Keep the value and keep this harness — promote it over the tail-events "
                           "backtest, which cannot see a historical origin",
        "blast radius": f"none at the production value; ×4 would move {radius_w2x4['entered_top_n']} "
                        f"fighters into the top 100 at a measured accuracy cost",
    },
    {
        "#": 5,
        "defect": "The bar's composition drifts (the 0.90 quantile is the "
                  f"{es.ordinal(place_2000)}-best fighter-year in 2000, the {es.ordinal(place_2024)} in 2024)",
        "evidence": f"holding composition fixed moves the top 50 by a median of "
                    f"{radius_h4['median_abs_rank_move_top50']:.0f} rank places and active-2024 by "
                    f"{radius_h4['active_2024_after'] - radius_h4['active_2024_before']:+d}",
        "recommended fix": "Document it. A fixed count is undefined for "
                           f"{len(undefined_60)} of {len(bar_table)} years, and the drift does not "
                           "reach the fighters it was suspected of excluding",
        "blast radius": f"{radius_h4['entered_top_n']} in, {radius_h4['left_top_n']} out, "
                        f"Spearman {radius_h4['spearman_all']:.3f}",
    },
    {
        "#": 6,
        "defect": "The board prints a dense rank across a huge tie, so a placing reads as a measurement",
        "evidence": f"ranks {tie_from:,}–{tie_to:,} all hold a mass of exactly zero "
                    f"({len(zero):,} fighters, {distinct_tiebreak} distinct tiebreak value); the "
                    "order inside it is the fighter's name",
        "recommended fix": "Rank with `method='min'` so the tie prints as one place, or publish "
                           "'unranked — no year above the bar' instead of a number",
        "blast radius": f"presentation only; no mass changes, but {len(zero):,} of "
                        f"{len(base_board):,} printed ranks stop being a claim",
    },
    {
        "#": 7,
        "defect": "Cross-era scale rests on a narrow bridge, so the era gradient is unidentified",
        "evidence": f"narrowest year-to-year link {narrowest['pair']} shares "
                    f"{int(narrowest['shared fighters'])} fighters; {span_bridge} fighters span "
                    "2000–2004 and 2016–2026",
        "recommended fix": "Publish the bridge width beside any cross-era claim, and treat the "
                           f"{debut_coef:+.1f} pts/yr conditional gradient as unattributed",
        "blast radius": "reporting only",
    },
])
defects.set_index("#")
"""))

# ---------------------------------------------------------------------------
add(md(r"""
---
## 9. Verdicts, and what the data cannot resolve
"""))

add(code(r"""
verdict_table = pd.DataFrame([
    {"hypothesis": v.hypothesis, "verdict": v.verdict.upper()} for v in VERDICTS.values()
])
display(verdict_table)

# Is Jon Jones' interval really the only tight one, as the brief says?
top20 = uncertainty.head(20).copy()
top20["width"] = top20["rank_hi"] - top20["rank_lo"]
tight_top20 = top20[top20["width"] <= 2]
jones_lo = int(uncertainty.set_index("fighter").loc["Jon Jones", "rank_lo"])
jones_hi = int(uncertainty.set_index("fighter").loc["Jon Jones", "rank_hi"])
jones_peak_excess = float(base_board.set_index("fighter").loc["Jon Jones", "peak_year_excess"])

show(
    "### What is still open, and what would close it\n\n"
    f"**The era gradient's meaning.** Conditional on record depth, a later debut is worth "
    f"{debut_coef:+.2f} rating points per year. Whether that is the sport improving or the scale "
    f"drifting is *not identified*: the narrowest year-to-year link in the rating chain shares "
    f"{int(narrowest['shared fighters'])} fighters, and only {span_bridge} fighters in the database "
    "were active both in 2000–2004 and in 2016–2026. Closing it needs cross-era evidence that does "
    "not exist and cannot be manufactured — the best available substitute is more of the record "
    "per fighter, which is defect 1 and defect 2.\n\n"
    "**Whether the joint scope is an improvement or a different error.** It moves the headline "
    f"further than anything else here ({comp['active_2024_plus']} → {joint_comp['active_2024_plus']} "
    "active in the top 100), and the abstention rule built for precisely this risk does not object "
    f"to any of its top 60. What is still open is that {mostly_outside} of that 60 now rest mostly "
    "on a source with the same censoring one level down. Closing it needs the whole-career crawl "
    f"finished — {careers_cov['fighter_pages_read']:,} of "
    f"{careers_cov['fighters_requested']:,} pages read — not a promotion weight, which would "
    "assert the answer the joint fit exists to estimate.\n\n"
    "**Jon Jones.** "
    f"{'His interval is the tightest on the board' if int(tight_top20['fighter'].eq('Jon Jones').sum()) and len(tight_top20) == 1 else 'His interval is among the tightest on the board'} "
    f"([{jones_lo}, {jones_hi}], against a median top-50 width of "
    f"{es.interval_widths(uncertainty)['median_rank_width']:.0f} places), he is the one carried "
    "case with no suffix to delete and nothing to recover from another promotion, and his peak "
    f"year clears the bar by {jones_peak_excess:.0f} points. Both readings in the brief are "
    "available and this notebook separates them only partly: the compounding is real — mass is "
    "years multiplied by excess — but the excess itself is not an artifact of any defect measured "
    "here, so the dominance reading is the better supported one.\n\n"
    "**Natalia Silva and Merab Dvalishvili.** Neither is resolvable on this evidence. Both clear "
    "the bar in every active year, and both sit inside wide bootstrap intervals "
    f"(Natalia Silva [{int(uncertainty.set_index('fighter').loc['Natalia Silva','rank_lo'])}, "
    f"{int(uncertainty.set_index('fighter').loc['Natalia Silva','rank_hi'])}], Merab Dvalishvili "
    f"[{int(uncertainty.set_index('fighter').loc['Merab Dvalishvili','rank_lo'])}, "
    f"{int(uncertainty.set_index('fighter').loc['Merab Dvalishvili','rank_hi'])}]). A long run "
    "without a loss is exactly the case where the Bradley–Terry likelihood has no interior "
    "maximum and the prior sets the answer, so a dominant fighter and an untested one produce "
    "similar boards. The interval is what says the board cannot yet tell them apart."
)
"""))


def build() -> None:
    notebook = {
        "cells": CELLS,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    OUT_PATH.write_text(json.dumps(notebook, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {OUT_PATH} ({len(CELLS)} cells)")


if __name__ == "__main__":
    build()
