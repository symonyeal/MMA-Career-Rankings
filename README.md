# Symon UFC Rank Engine

An MMA ranking lab for all-time, current, and division-level UFC analysis.

The project builds a local ranked snapshot from UFCStats/Greco, enriches it
with odds and comparison sources, adds Sherdog-derived PRIDE/Strikeforce/WEC
bouts, and presents the results in a Plotly/Jupyter notebook with short,
audience-friendly labels.

## Open This First

Run the interactive notebook:

```bash
jupyter lab analysis/notebook.ipynb
```

Or rebuild it after code changes:

```bash
python analysis/build_notebook.py
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
| Strength | Context checked | Adds opponent, rank, title, and weight-class context. |
| Skill peak | Best-window skill | Clean + Strength on the **Glicko-2 filter** (forward-pass estimator). |
| All-time | Recommended greatness view | A Whole-History Rating (WHR) smoother that re-rates every career jointly and carries an explicit era adjustment. |

> **Complete and Legacy are two estimators, not one plus a bonus.** Complete is
> the Glicko-2 *filter* with finish-quality scoring and a ±10% performance/integrity
> sleeve; Legacy is the WHR *smoother* on binary results, now run **with the same
> sleeve** (`whr_integrity_performance`) so the era-bridged all-time view also
> reflects opponent quality — see *Unifying the two engines* below.

Recommended views:

- **Prime + All-time** for all-time debate; adjust **Prime yr** and
  **Prime min** when you want a stricter or looser sustained-run definition.
- **Peak + Skill peak** for short-run dominance.
- **Wins** as the untouched binary-result baseline.

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
>    that monotonized curve, scaled to **25%** by `WHR_ERA_PREMIUM_STRENGTH`, is added to every
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
> or the notebook's *Apply & recompute*). The `2026-08-13` snapshot was fully
> recomputed with the current constants.

## Recommended All-Time Top 30 (men's P4P)

Snapshot `2026-08-13`. The public default is now **All-time + Prime**: the
sleeved Whole-History Rating smoother over each fighter's best sustained
10-year run. **Skill peak + Peak** remains available as a diagnostic, but is no
longer presented as the default GOAT list.

| # | Fighter | FightMatrix all-time | Gap |
|--:|---|--:|--:|
| 1 | Jon Jones | 2 | -1 |
| 2 | Georges St-Pierre | 1 | +1 |
| 3 | Islam Makhachev | 9 | -6 |
| 4 | Anderson Silva | 6 | -2 |
| 5 | Demetrious Johnson | 10 | -5 |
| 6 | Alexander Volkanovski | 5 | +1 |
| 7 | Daniel Cormier | 14 | -7 |
| 8 | Alex Pereira | 22 | -14 |
| 9 | Jose Aldo | 3 | +6 |
| 10 | Kamaru Usman | 12 | -2 |
| 11 | Israel Adesanya | 15 | -4 |
| 12 | Max Holloway | 8 | +4 |
| 13 | Stipe Miocic | 17 | -4 |
| 14 | Ilia Topuria | — | — |
| 15 | Khabib Nurmagomedov | 13 | +2 |
| 16 | Randy Couture | 21 | -5 |
| 17 | BJ Penn | 11 | +6 |
| 18 | Matt Hughes | 7 | +11 |
| 19 | TJ Dillashaw | — | — |
| 20 | Dricus Du Plessis | — | — |
| 21 | Merab Dvalishvili | — | — |
| 22 | Aljamain Sterling | — | — |
| 23 | Henry Cejudo | — | — |
| 24 | Alexandre Pantoja | — | — |
| 25 | Cain Velasquez | 35 | -10 |
| 26 | Frankie Edgar | 20 | +6 |
| 27 | Francis Ngannou | — | — |
| 28 | Benson Henderson | — | — |
| 29 | Conor McGregor | — | — |
| 30 | Ciryl Gane | — | — |

The gap is `engine rank - FightMatrix rank`; negative means the engine is more
favorable. The comparison is a sanity check, not a training target.
[FightMatrix](https://www.fightmatrix.com/all-time-mma-rankings/all-time-absolute/)
uses whole MMA careers, while the standard Rank Engine snapshot is UFC-only.
That source-scope difference explains part of Aldo, Penn, Hughes, and other
pre-/cross-organization gaps. Pereira at #8 remains a genuine model tension:
the title-effective eligibility rule, modern-era premium, and dominance reward
value his short, title-dense UFC run much more than the external career ranking.

The notebook now puts this comparison directly below the leaderboard so large
disagreements are visible on every lens instead of buried in methodology text.

### Public FightMatrix career-data scope

The project can now cache the public profiles linked by FightMatrix's current
division and all-time ranking tables. The bounded 2026-08-14 local copy has
302 profiles and 6,644 deduplicated professional bouts; 4,023 post-cutoff
non-UFC bouts remain after UFC/date/pair deduplication. It is intentionally not
a recursive copy of FightMatrix's proprietary database.

The raw profiles and bouts are queryable in the standard SQLite database. A
separate `2026-08-13-fightmatrix-public` snapshot and
`ufc_rank_engine_fightmatrix_public.sqlite` preserve the experimental rating
run. It is not the default board: the ranked-cohort sampling frame and missing
historical title metadata push some non-UFC careers down despite adding their
results. `fightmatrix_scope_comparison` records that effect explicitly.

The recursive experiment is a separate, resumable pipeline in
`build_fightmatrix_expanded.py`. It uses FightMatrix profile IDs as identities,
persists a breadth-first queue, reconciles reciprocal records, measures graph
closure, and applies an explicit completeness policy before producing optional
rating input. It never changes the UFC-only production snapshot. Public rank,
points, quality percentage, 540 metric, and combat-age fields are blocked from
the model-input schema by an automated leakage test.

<details>
<summary>Historical four-board analysis from the 2026-06-23 snapshot</summary>

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

</details>

## Notebook Views

The notebook is built to work like a dashboard:

- Select **Peak** or **Prime** (the retrospective best-run windows).
- Select **Wins**, **Skill peak**, or **All-time**.
- Adjust **Prime yr** and **Prime min** to define the Prime window.
- Filter leaderboards by division.
- Compare rank movement before and after cross-organization enrichment.
- Trace a fighter's career line against the selected rating view.
- Switch division charts by year, top-N depth, and selected divisions.
- View division strength over time for comparative performance.

The dashboard also includes (see `analysis/CHART_PLAN.md`):

- A **Ranking Sanity Check** against the current FightMatrix all-time table.
- **Most Dominant** and **All-time vs Prime** boards alongside the rankings.
- **Division parity** (crowdedness) and **How fights end** in the Weight Classes block.
- **Title Lineage** reigns per division.
- **Striking fingerprint** (strike target/position mix) in the Tale of the Tape.
- **Market vs Model** (the closing line as a scoring benchmark) and an
  **Integrity Ledger** for the PED/DQ/missed-weight layer.

Charts follow a consulting-style presentation pattern: clear title, short
labels, focused color, direct takeaway, and minimal chart noise.

## Current Snapshot

Production snapshot: `data/snapshots/2026-08-13` (UFCStats data current through
UFC Fight Night: Gamrot vs. Salkilld).

Included in the latest run:

- 754 UFC events (749 with ratable bouts).
- 8,479 rated UFC fights.
- 2,554 rated fighters.
- 6,562 fights with usable market odds (mdabbert). These are the *benchmark* the
  engine is scored against in `ratings/prequential.py`, not an input to any
  rating: the odds-to-weight path was removed on 2026-08-18 after measuring a
  paired effect on held-out log-loss of −1.4×10⁻⁶ [−3.2×10⁻⁶, +3.4×10⁻⁷], an interval spanning zero.
- UFC-DataLab, current FightMatrix, and FightMatrix all-time artifacts staged.
- Local SQLite export at `data/ufc_rank_engine.sqlite` (36 tables, 147 indexes),
  including public FightMatrix profile, bout and scope-comparison tables.

The six events added since `2026-06-23` were scraped directly from UFCStats:
Fiziev vs. Torres, UFC 329, Du Plessis vs. Usman, Ankalaev vs. Guskov, Medic
vs. Rodriguez, and Gamrot vs. Salkilld. They added 77 rated bouts and 20
fighters to `data/raw/2026-08-13/`.

Cross-organization enrichment (PRIDE/Strikeforce/WEC from Sherdog, via
`build_crossorg.py`) is an optional layer on top of this canonical snapshot and
is not part of the standard `refresh.py` run.

## Rebuild Commands

Use these from the project root.

Extend the last raw bundle with newly completed UFCStats events:

```bash
python -m loaders.ufcstats_scrape \
  --old-raw "data/raw/2026-06-23" \
  --out-raw "data/raw/2026-08-13"
```

Refresh end to end with the latest UFCStats data (rebuilds the canonical
snapshot, ratings, changelog, and notebook). Point `--greco-dir` at a directory
holding the six current Greco CSVs:

```bash
python refresh.py --snapshot-date 2026-08-13 \
  --greco-dir "data/raw/2026-08-13" \
  --include-external --include-odds \
  --mdabbert-csv "../../archive/ufc-master.csv"
```

Cache and stage the bounded public FightMatrix profile cohort after the ranking
artifacts exist. Cached pages are reused by default:

```bash
python build_fightmatrix_public.py \
  --snapshot-dir "data/snapshots/2026-08-13"
```

On a managed network that replaces TLS certificates, add `--insecure`
explicitly. The flag is never enabled by default.

Audit and resume the depth-one opponent expansion. The working directory is
checkpointed and may be rerun with the same command. `--insecure` is an
explicit managed-network exception and is recorded on every profile provenance
row; omit it wherever the local trust store validates FightMatrix normally.

```bash
python build_fightmatrix_expanded.py \
  --base-snapshot "data/snapshots/2026-08-13" \
  --output-dir "data/snapshots/2026-08-14-fightmatrix-expanded-v3-working" \
  --max-depth 1 --max-profiles 5000 --max-new-profiles 5000 \
  --request-budget 5000 --wall-clock-seconds 10800 \
  --sleep-seconds 1 --policy reliability
```

Rerunning that command once the queue is exhausted re-audits from cache and
issues no requests. Each experimental rating scope is then staged and rated
from the same audited working directory. A staging target must not already
exist, so one scope is one immutable directory:

```bash
# scope 3 - depth-one expanded graph, no completeness control (sensitivity only)
python build_fightmatrix_expanded.py \
  --base-snapshot "data/snapshots/2026-08-13" \
  --output-dir "data/snapshots/2026-08-14-fightmatrix-expanded-v3-working" \
  --max-depth 1 --max-new-profiles 0 --request-budget 0 --policy raw \
  --stage-rating-snapshot "data/snapshots/2026-08-14-fightmatrix-depth-one-raw" \
  --run-ratings

# scope 5 - complete-edge filtered
python build_fightmatrix_expanded.py \
  --base-snapshot "data/snapshots/2026-08-13" \
  --output-dir "data/snapshots/2026-08-14-fightmatrix-expanded-v3-working" \
  --max-depth 1 --max-new-profiles 0 --request-budget 0 --policy complete_edge \
  --stage-rating-snapshot "data/snapshots/2026-08-14-fightmatrix-depth-one-complete_edge" \
  --run-ratings

# scope 6 - reliability weighting, the recommended experimental policy
python build_fightmatrix_expanded.py \
  --base-snapshot "data/snapshots/2026-08-13" \
  --output-dir "data/snapshots/2026-08-14-fightmatrix-expanded-v3-working" \
  --max-depth 1 --max-new-profiles 0 --request-budget 0 --policy reliability \
  --stage-rating-snapshot "data/snapshots/2026-08-14-fightmatrix-depth-one-reliability" \
  --run-ratings
```

Compare every rated scope against the UFC-only baseline. Cohort size differs by
scope, so the comparison carries percentile movement and a common-reference-subset
error next to the raw ranks:

```bash
python build_fightmatrix_validation.py \
  --scope "ufc_only=data/snapshots/2026-08-13" \
  --scope "bounded_302_seed=data/snapshots/2026-08-13-fightmatrix-public" \
  --scope "depth_one_raw=data/snapshots/2026-08-14-fightmatrix-depth-one-raw" \
  --scope "depth_one_complete_edge=data/snapshots/2026-08-14-fightmatrix-depth-one-complete_edge" \
  --scope "depth_one_reliability=data/snapshots/2026-08-14-fightmatrix-depth-one-reliability" \
  --trace-scope "depth_one_raw=data/snapshots/2026-08-14-fightmatrix-depth-one-raw" \
  --trace-scope "depth_one_reliability=data/snapshots/2026-08-14-fightmatrix-depth-one-reliability" \
  --output-dir "data/snapshots/2026-08-14-fightmatrix-validation"
```

Export an experimental scope to its own SQLite file, leaving the production
database untouched:

```bash
python build_database.py \
  --snapshot-dir "data/snapshots/2026-08-14-fightmatrix-depth-one-reliability" \
  --db-path "data/ufc_rank_engine_fightmatrix_depth_one.sqlite"
```

To make a new refresh use those cross-organization results in the rating run:

```bash
python refresh.py --snapshot-date 2026-08-14 \
  --greco-dir "data/raw/2026-08-13" \
  --include-external --include-odds --include-fightmatrix-profiles
```

Build the optional cross-org snapshot:

```bash
python build_crossorg.py --base "data/snapshots/2026-08-13" --out "data/snapshots/2026-08-13-crossorg"
```

Run the ratings:

```bash
python -m ratings.rate_snapshot --snapshot-dir "data/snapshots/2026-08-13"
```

Build SQLite:

```bash
python build_database.py --snapshot-dir "data/snapshots/2026-08-13"
```

Run tests:

```bash
python -m pytest -q
```

## Project Layout

```text
analysis/              Notebook builder and Plotly charts
build_crossorg.py      Sherdog PRIDE/Strikeforce/WEC enrichment builder
build_fightmatrix_public.py  Bounded public profile/history cache and staging
build_fightmatrix_expanded.py  Resumable opponent expansion, audit, policy, staging
build_fightmatrix_validation.py  Multi-scope validation, historical panel, anomaly traces
build_source_scope_comparison.py  UFC-only versus public-cohort comparison
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
