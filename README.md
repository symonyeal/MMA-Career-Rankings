# Symon UFC Rank Engine

An MMA ranking lab for all-time, current, and division-level UFC analysis.

The project builds a local ranked snapshot from UFCStats/Greco, enriches it
with odds and comparison sources, adds Sherdog-derived PRIDE/Strikeforce/WEC
bouts, and presents the results in a Plotly/Jupyter notebook with short,
audience-friendly labels.

## Open This First

Run the interactive notebook:

```bash
.venv/bin/jupyter lab analysis/notebook.ipynb
```

Or rebuild it after code changes:

```bash
.venv/bin/python analysis/build_notebook.py
```

The notebook auto-loads the newest snapshot under `data/snapshots/`.

## Rating Labels

This is a **retrospective** engine — an analysis of what has happened, not a
current-form snapshot or a prediction of what might happen. The time lenses are
therefore the two best-run windows only:

| Label | Use it for | What it means |
|---|---|---|
| Peak | Best 5 years | A fighter's strongest five-year run. |
| Prime | Best N years | A fighter's strongest sustained run, with year and fight-count controls. |
| Wins | Simple results | Win, loss, draw only. |
| Finishes | Result plus method | Rewards how the fight ended. |
| Clean | Integrity checked | Adjusts PED, DQ, and missed-weight wins. |
| Strength | Context checked | Adds opponent, odds, rank, title, and weight-class context. |
| Complete | Best default | Clean + Strength together, on the **Glicko-2 filter** (forward-pass estimator). |
| Legacy | Broad all-time | A **different engine** — a Whole-History Rating (WHR) Bayesian smoother that re-rates every career jointly and is calibrated across eras. |

> **Complete and Legacy are two estimators, not one plus a bonus.** Complete is
> the Glicko-2 *filter* with finish-quality scoring and a ±10% performance/integrity
> sleeve; Legacy is the WHR *smoother* on binary results, now run **with the same
> sleeve** (`whr_integrity_performance`) so the era-bridged all-time view also
> reflects opponent quality — see *Unifying the two engines* below.

Recommended audience defaults:

- **Prime + Complete** for all-time debate; adjust **Prime yr** and
  **Prime min** when you want a stricter or looser sustained-run definition.
- **Peak + Complete** for short-run dominance.
- **Prime + Legacy** when comparing old eras to modern eras.

## Unifying the two engines (Complete vs Legacy)

Complete and Legacy answer different questions with different estimators, and
their strengths are complementary rather than competing:

| Property | Complete — Glicko-2 *filter* | Legacy — WHR *smoother* |
|---|---|---|
| Information flow | Forward-only (causal) | Bidirectional (joint over the whole career) |
| Outcome signal | Continuous finish-quality + ±10% sleeve | Finish/integrity score + sleeve weight (base stream unsleeved) |
| Dominance | Score bonus on S_j (decisions) | **Two-sided likelihood-weight reward** — winner up & blown-out loser down; index is per-minute, floors finishes, adds the decision scorecard margin |
| Era comparability | Raw scale trends up (modern premium baked in) | Era-bridged **plus** an explicit data-driven modern-era premium |
| Reactivity to a single result | High | Low (smoothed) |
| Early-career noise | Persists (never revised) | Corrected retroactively |

> **Engine philosophy — era premium + dominance (2026-06-25):**
> 1. **Legacy carries an explicit, data-driven modern-era premium.** WHR re-anchors
>    its mean to zero every pass, so it is era-*flat* by construction — a smoother
>    cannot, on its own, encode "the modern field is harder." The Glicko filter's
>    per-year mean rating is the engine's own measurement of how the field has
>    strengthened (~+130 mu, 2002→2025, concave: fast early, plateauing recently);
>    that monotonized curve, scaled by `WHR_ERA_PREMIUM_STRENGTH`, is added to every
>    WHR appearance before the Prime/Peak windows. WHR streams are **exempted from
>    the windowing era-de-trend** so the premium is not re-flattened. Net: later-era
>    primes outrank equally-dominant one-era pioneers, while the 10-yr Prime window
>    still rewards multi-era longevity.
> 2. **Dominance is two-sided and finish-aware.** A lopsided bout is stronger
>    evidence in *both* directions — the winner's and the blown-out loser's WHR
>    likelihood weights are each scaled by `1 + WHR_DOMINANCE_WEIGHT_AMPLITUDE·dom_level`
>    — so dominant fighters separate from the field instead of the winner merely
>    floating up. The dominance index itself is **per-minute normalized** (a
>    60-second KO is no longer penalized for brevity), **floors finishes**
>    (`DOMINANCE_FINISH_FLOOR_Z` — a finish *is* dominance), and for decisions adds
>    the **affine-normalized judge scorecard margin** (a 50-45 sweep reads as more
>    dominant than a 48-47 squeaker).

**Key point:** the *richness* (the finish/opponent/integrity sleeve) is
**orthogonal** to the *estimator* (filter vs smoother). The sleeve is already
modular and is already applied to both engines — `method_performance` (sleeved
filter) and `whr_integrity_performance` (sleeved smoother) both exist in
`ratings_current.parquet`. So "best of both" is a wiring decision, not new math.

This is a **retrospective** engine, so both lenses are read as descriptions of
what happened — not as predictions. The two simply weight the same history
differently: Complete is sharper on finishes and recent context, Legacy is
smoother and era-comparable.

**Design (implemented 2026-06-25):**

1. ✅ **`Legacy` now points at the sleeved `whr_integrity_performance`**, so the
   era-bridged all-time view also reflects opponent quality / finish / integrity
   rather than binary records.
2. ✅ **Each engine has one job.** Complete (sleeved Glicko filter) = the
   finish-and-context-aware lens; Legacy (sleeved WHR smoother) = the smoothed,
   era-comparable lens behind the Prime & Peak boards. No predictive surfaces:
   `Now`/current-form and head-to-head win probabilities were removed.
3. ◻ **Optional consensus board (display only).** A reliability-weighted blend of
   the two, each z-scored within the snapshot and weighted by its own
   uncertainty (Glicko φ / WHR Hessian). *Not built — offered.*
4. ✅ **Display scale unified.** The WHR/Legacy columns are affine-mapped onto the
   matching Complete distribution at load (`affine_match_scale`), so switching
   lenses no longer jumps the axis. Ordering within Legacy is preserved.
5. ✅ **Backtest `WHR_W2_PER_DAY` — done; current value retained.** Harness
   `ratings/whr_backtest.py` does honest rolling-origin (no look-ahead) scoring:
   for each held-out event it re-fits WHR on prior fights only and scores
   one-step-ahead Brier/log-loss over a `(w2, var_lambda)` grid. `var_lambda` is
   the **WHR-native uncertainty shrinkage** — predictions attenuated by combined
   posterior variance `gap / sqrt(1 + λ·(var_a+var_b))` (the analog of Glicko-2's
   `g(RD)`), sourced from the smoother's own Hessian via
   `run_whr(return_variance=True)`. **Result on 2026-06-23 (172 elite bouts):**
   the whole grid is within noise (SE of mean log-loss ≈0.03 vs ~0.006 spread),
   and the nominal best (`w2=0.0016`) sat at the grid edge — so `WHR_W2_PER_DAY`
   stays at `0.0004`. The λ attenuation helped a hair (λ≈0.5–1.0 > 0) but only
   affects predictions, which the dashboard does not surface. Re-run anytime via
   `python -m ratings.whr_backtest <snapshot>`.

> Note: the ±10% sleeve change (and any future engine-constant change) only takes
> effect after a ratings **recompute** (`python -m ratings.rate_snapshot <snapshot>`
> or the notebook's *Apply & recompute*). The committed snapshots were built with
> the older ±20% sleeve until re-run.

## All-Time Top 30 — Prime · Legacy (men's pound-for-pound)

The headline board: the **Legacy** lens (era-bridged WHR smoother, sleeved) over the
**Prime** 10-year window, men's P4P, snapshot `2026-06-23`. Ratings are affine-mapped
onto the Complete scale for one axis. The **Complete #** column is each fighter's rank
under the **Complete** lens (Glicko-2 filter) — the two estimators answer different
questions, so they disagree *by design*.

| # | Fighter | Legacy | Complete # | | # | Fighter | Legacy | Complete # |
|--:|---|--:|--:|:-:|--:|---|--:|--:|
| 1 | Jon Jones | 2703 | 2 | | 16 | Merab Dvalishvili | 2366 | 49 |
| 2 | Georges St-Pierre | 2627 | 4 | | 17 | Dricus Du Plessis | 2357 | 21 |
| 3 | Islam Makhachev | 2609 | 10 | | 18 | TJ Dillashaw | 2356 | 37 |
| 4 | Alexander Volkanovski | 2574 | 5 | | 19 | Aljamain Sterling | 2353 | 24 |
| 5 | Demetrious Johnson | 2548 | 23 | | 20 | Henry Cejudo | 2339 | 27 |
| 6 | Alex Pereira | 2548 | 7 | | 21 | Alexandre Pantoja | 2339 | 59 |
| 7 | Daniel Cormier | 2525 | 3 | | 22 | BJ Penn | 2309 | 33 |
| 8 | Anderson Silva | 2515 | 1 | | 23 | Francis Ngannou | 2306 | 30 |
| 9 | Kamaru Usman | 2489 | 9 | | 24 | Randy Couture | 2289 | 45 |
| 10 | Israel Adesanya | 2476 | 6 | | 25 | Ciryl Gane | 2287 | 25 |
| 11 | Max Holloway | 2464 | 11 | | 26 | Frankie Edgar | 2282 | 16 |
| 12 | Jose Aldo | 2460 | 8 | | 27 | Petr Yan | 2280 | 35 |
| 13 | Stipe Miocic | 2445 | 12 | | 28 | Charles Oliveira | 2278 | 42 |
| 14 | Ilia Topuria | 2437 | 13 | | 29 | Cain Velasquez | 2275 | 19 |
| 15 | Khabib Nurmagomedov | 2415 | 20 | | 30 | Matt Hughes | 2274 | 55 |

### Why the two boards differ

Disagreements come from two independent sources, which can stack or cancel:

1. **Filter vs smoother (information flow).** Complete is a forward-only Glicko-2
   *filter*: it never revisits a rating, so early-career noise persists and a single
   late-career slip or a still-climbing rating sticks. Legacy is a WHR *smoother* that
   re-rates every career jointly. So the smoother **lifts fighters the filter buried**
   — Demetrious Johnson (Legacy #5 vs Complete #23), Khabib (#15 vs #20), Randy Couture
   (#24 vs #45), Matt Hughes (#30 vs #55): long, coherent careers the one-pass filter
   under-credits.
2. **Era premium + dominance (Legacy-only).** The data-driven modern-era premium and
   the two-sided, finish-aware dominance reward apply only to Legacy:
   - **Reigning, dominant, recent champions rise** above their filter rank because the
     era premium credits the modern field and the per-minute / scorecard-margin
     dominance rewards how decisively they win: **Merab Dvalishvili #16 (Complete #49)**,
     **Alexandre Pantoja #21 (#59)**, Dricus Du Plessis #17 (#21).
   - **The finish floor unlocks pure finishers.** **Francis Ngannou #23 sits above his
     Complete #30**: his quick KOs scored ~0 under the old accumulated-stats index and
     now floor as dominant.
   - **Earlier-era greats sit a touch lower in Legacy than in Complete**, where the
     reactive filter rewards their sharp finish-heavy peak immediately while the era
     premium discounts the older portion of their prime: **Anderson Silva (Complete #1,
     Legacy #8)**, Frankie Edgar (#16 / #26), Cain Velasquez (#19 / #29). They remain
     elite — they are simply measured against a harder modern field on the Legacy board.

Era-spanning greats sit at the top of **both** boards because longevity satisfies the
10-year Prime window *and* their later fights bank the modern-era premium: **Jon Jones
#1** and **Georges St-Pierre #2** are unmoved by either change.

### How the engine changes shifted the board (validation)

Tracked cohorts, Legacy rank before → after the era-premium + dominance work:

| Cohort | Before | After | Read |
|---|---|---|---|
| Pioneers (Couture, Hughes, Ortiz, Liddell, Sylvia) | #13–#31 | #24–#56 | Era-flatness corrected — one-era pioneers drop to era-appropriate ranks. |
| Francis Ngannou (pure finisher) | #33 | **#23** | Finish floor rewards the quick-KO artist the old index ignored. |
| Whittaker / Romero (finishers with losses) | #52 / #67 | #44 / #64 | Rise modestly — dominance rewards *how you win* but cannot erase losses, and two-sided dominance makes their own dominant losses cost more. |
| Multi-era greats (Jones, GSP, DJ, Silva) | #1–#4 | #1, #2, #5, #8 | Hold the top; era premium discounts only the earliest primes. |

All knobs are tunable for further iteration: `WHR_ERA_PREMIUM_STRENGTH` (era magnitude),
`DOMINANCE_FINISH_FLOOR_Z` (finish dominance), and the `WHR_DOMINANCE_*` amplitudes.

## Notebook Views

The notebook is built to work like a dashboard:

- Select **Peak** or **Prime** (the retrospective best-run windows).
- Select **Wins**, **Finishes**, **Clean**, **Strength**, or **Complete**.
- Adjust **Prime yr** and **Prime min** to define the Prime window.
- Filter leaderboards by division.
- Compare rank movement before and after cross-organization enrichment.
- Trace a fighter's career line against the selected rating view.
- Switch division charts by year, top-N depth, and selected divisions.
- View division strength over time for comparative performance.

The dashboard also includes (see `analysis/CHART_PLAN.md`):

- **Most Dominant** and **Legacy vs Prime** boards alongside the rankings.
- **Since Last Snapshot** movers and a **Ring Rust** inactivity ledger.
- **Division parity** (crowdedness) and **How fights end** in the Weight Classes block.
- **Title Lineage** reigns per division.
- **Striking fingerprint** (strike target/position mix) in the Tale of the Tape.
- **Market vs Model**, **Model Accuracy** (calibration), and an **Integrity
  Ledger** for the PED/DQ/missed-weight layer.

Charts follow a consulting-style presentation pattern: clear title, short
labels, focused color, direct takeaway, and minimal chart noise.

## Current Snapshot

Production snapshot: `data/snapshots/2026-06-23` (UFCStats data current through
the June 20, 2026 card, Kape vs. Horiguchi).

Included in the latest run:

- 748 UFC events (743 with ratable bouts).
- 8,402 rated UFC fights.
- 2,524 rated fighters.
- 6,567 fights with market odds (mdabbert) for the performance sleeve.
- UFC-DataLab and FightMatrix comparison artifacts staged in the snapshot.
- Local SQLite export at `data/ufc_rank_engine.sqlite` (31 tables, 120 indexes).

The five events added since the prior `2026-05-13` snapshot were scraped
directly from UFCStats (Allen vs. Costa, Song vs. Figueiredo, Muhammad vs.
Bonfim, UFC Freedom 250, Kape vs. Horiguchi) and appended to the Greco CSV
inputs in `data/raw/2026-06-23/`.

Cross-organization enrichment (PRIDE/Strikeforce/WEC from Sherdog, via
`build_crossorg.py`) is an optional layer on top of this canonical snapshot and
is not part of the standard `refresh.py` run.

## Rebuild Commands

Use these from the project root.

Refresh end to end with the latest UFCStats data (rebuilds the canonical
snapshot, ratings, changelog, and notebook). Point `--greco-dir` at a directory
holding the six current Greco CSVs:

```bash
python refresh.py --snapshot-date 2026-06-23 \
  --greco-dir "data/raw/2026-06-23" \
  --include-external --include-odds \
  --mdabbert-csv "../archive/ufc-master.csv"
```

Build the optional cross-org snapshot:

```bash
.venv/bin/python build_crossorg.py --base "data/snapshots/2026-06-23" --out "data/snapshots/2026-06-23-crossorg"
```

Run the ratings:

```bash
.venv/bin/python -m ratings.rate_snapshot --snapshot-dir "data/snapshots/2026-06-23"
```

Build SQLite:

```bash
.venv/bin/python build_database.py --snapshot-dir "data/snapshots/2026-06-23"
```

Run tests:

```bash
.venv/bin/python -m pytest -q
```

## Project Layout

```text
analysis/              Notebook builder and Plotly charts
build_crossorg.py      Sherdog PRIDE/Strikeforce/WEC enrichment builder
build_database.py      SQLite export builder
data/SOURCE_MATRIX.md  Source and field audit
docs/archive/          Older audits, logs, and reports
loaders/               Source loaders and identity helpers
ratings/               Rating engine, adjustments, peaks, and WHR
tests/                 Loader, engine, database, and visualization tests
```

## Source Notes

Primary UFC fight data comes from the Greco UFCStats CSV snapshot. External
comparison and context sources include UFC-DataLab, FightMatrix, mdabbert odds,
and Sherdog fighter histories for PRIDE/Strikeforce/WEC bouts.

Raw snapshots, large caches, and generated SQLite files are intentionally
ignored by Git. The code and notebook can regenerate the local outputs.

Detailed source lineage lives in `data/SOURCE_MATRIX.md`.

## Archived Material

Older audit notes, ranking exports, and development handoff logs were moved to
`docs/archive/` so the root stays presentable while preserving the project
history.
