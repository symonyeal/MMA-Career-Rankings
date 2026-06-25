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

## All-Time Top 30 — Complete vs Legacy × Prime vs Peak (men's P4P)

Men's pound-for-pound, snapshot `2026-06-23`, all four views side by side. **Prime** is
the best 10-year window, **Peak** the best 5-year window; **Complete** is the Glicko-2
filter, **Legacy** the era-bridged WHR smoother. Two knobs change across this table —
read *across a row* and you change the **engine**, read *Prime→Peak* and you change the
**time window** — so the four columns disagree by design.

| # | Complete · Prime | Legacy · Prime | Complete · Peak | Legacy · Peak |
|--:|---|---|---|---|
| 1 | Anderson Silva | Jon Jones | Anderson Silva | Islam Makhachev |
| 2 | Jon Jones | Georges St-Pierre | Alexander Volkanovski | Jon Jones |
| 3 | Daniel Cormier | Islam Makhachev | Israel Adesanya | Alex Pereira |
| 4 | Georges St-Pierre | Alexander Volkanovski | Daniel Cormier | Demetrious Johnson |
| 5 | Alexander Volkanovski | Demetrious Johnson | Kamaru Usman | Georges St-Pierre |
| 6 | Israel Adesanya | Alex Pereira | Islam Makhachev | Anderson Silva |
| 7 | Alex Pereira | Daniel Cormier | Jon Jones | Alexander Volkanovski |
| 8 | Jose Aldo | Anderson Silva | Jose Aldo | Daniel Cormier |
| 9 | Kamaru Usman | Kamaru Usman | Alex Pereira | Israel Adesanya |
| 10 | Islam Makhachev | Israel Adesanya | Georges St-Pierre | Kamaru Usman |
| 11 | Max Holloway | Max Holloway | Chris Weidman | Khabib Nurmagomedov |
| 12 | Stipe Miocic | Jose Aldo | Stipe Miocic | Ilia Topuria |
| 13 | Ilia Topuria | Stipe Miocic | Ilia Topuria | Jose Aldo |
| 14 | Chris Weidman | Ilia Topuria | Conor McGregor | Merab Dvalishvili |
| 15 | Benson Henderson | Khabib Nurmagomedov | Khabib Nurmagomedov | Stipe Miocic |
| 16 | Frankie Edgar | Merab Dvalishvili | Demetrious Johnson | Max Holloway |
| 17 | Conor McGregor | Dricus Du Plessis | Benson Henderson | Alexandre Pantoja |
| 18 | Junior Dos Santos | TJ Dillashaw | Max Holloway | Dricus Du Plessis |
| 19 | Cain Velasquez | Aljamain Sterling | Leon Edwards | Aljamain Sterling |
| 20 | Khabib Nurmagomedov | Henry Cejudo | Tyron Woodley | Henry Cejudo |
| 21 | Dricus Du Plessis | Alexandre Pantoja | Merab Dvalishvili | TJ Dillashaw |
| 22 | Justin Gaethje | BJ Penn | Cain Velasquez | Francis Ngannou |
| 23 | Demetrious Johnson | Francis Ngannou | Junior Dos Santos | Matt Hughes |
| 24 | Aljamain Sterling | Randy Couture | Aljamain Sterling | Ciryl Gane |
| 25 | Ciryl Gane | Ciryl Gane | Ciryl Gane | Benson Henderson |
| 26 | Tyron Woodley | Frankie Edgar | Jiri Prochazka | Conor McGregor |
| 27 | Henry Cejudo | Petr Yan | Justin Gaethje | Cain Velasquez |
| 28 | Robert Whittaker | Charles Oliveira | Yoel Romero | Tom Aspinall |
| 29 | Yoel Romero | Cain Velasquez | Dricus Du Plessis | Khamzat Chimaev |
| 30 | Francis Ngannou | Matt Hughes | Rich Franklin | Charles Oliveira |

*(Legacy columns are affine-mapped onto the matching Complete scale, so ranks are
directly comparable; the mapping is monotonic, so ordering is unchanged.)*

### Axis 1 — Complete vs Legacy (the *engine*)

Complete is a forward-only **filter** (reactive, never revised, no era adjustment);
Legacy is a whole-career **smoother** carrying the modern-era premium and the two-sided,
finish-aware dominance reward. That pulls fighters in opposite directions by career shape:

- **The smoother + era premium lift modern, sustained, dominant careers the filter
  under-credits.** The clearest case is **Demetrious Johnson: Complete #23 → Legacy #5**
  on Prime (#16 → #4 on Peak) — the largest elite gap on the board. Same story:
  **Makhachev #10 → #3**, **Merab Dvalishvili #49 → #16**, **Alexandre Pantoja #59 → #21**.
- **The era premium discounts earlier-era peaks the filter ranks #1.** **Anderson Silva
  is Complete #1 on *both* windows but Legacy #8 / #6** — the reactive filter loves his
  2006–2012 finish reel; the premium measures it against a harder modern field.
- **The smoother punishes a great peak followed by a bad decline — which the filter
  ignores.** **Chris Weidman: Complete #14 / #11 → Legacy #36 / #35** (the Silva-beating
  title peak the filter banks, the brutal late losses the smoother folds back in).
  **Conor McGregor (#17 / #14 → #31 / #26)** is the milder version.

### Axis 2 — Prime vs Peak (the *window*)

**Prime** (best 10-year window, ≥13 fights) rewards **longevity**; **Peak** (best 5-year
window, ≥8 fights) rewards the single best **burst**.

> Mental model: **Peak = "how high you climbed," Prime = "how long you stayed there."**

- **Short or still-young careers jump on Peak.** **Khamzat Chimaev and Tom Aspinall do
  not rank on Prime at all** (too few fights to fill a 10-year window) yet land
  **Legacy·Peak #29 and #28** on elite 5-year bursts. **Khabib** rises **Prime #15 →
  Peak #11**. The eligible field is itself larger on Peak (616 men) than Prime (350),
  because the 5-yr / 8-fight bar admits more careers.
- **Decade-long greats own Prime.** **Jon Jones is Legacy·Prime #1 but Complete·Peak #7**
  — his edge is sustained excellence across a decade, not the single most explosive 5-year
  reel (where finish-machines Silva / Volkanovski / Adesanya top *Complete·Peak*). GSP is
  the same (Prime #2, Complete·Peak #10).

**Both axes at once — Demetrious Johnson.** Complete·Prime #23, Complete·Peak #16
(window: his best 5-yr run beats his 10-yr average on the filter), Legacy·Prime #5,
Legacy·Peak #4 (engine: the smoother + era + dominance see a sustained, dominant, modern
title reign the filter structurally under-rates). The ~18-spot Complete↔Legacy gap is the
biggest among elites — exactly what the Legacy lens was built to surface.

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
