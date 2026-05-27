# Dashboard — Chart Catalog & Expansion Guide

This document does two things:

1. **Catalog** every view in `analysis/notebook.ipynb` — what it shows, how it's
   encoded, and how it's ordered.
2. **Expansion guide** — the conventions, the step-by-step recipe for adding a
   new view, and a backlog of ready-to-use *prompts* for building more insight
   charts.

The notebook is **generated** from `analysis/build_notebook.py`. Never hand-edit
`notebook.ipynb`; edit the builder and run `python analysis/build_notebook.py`.

---

## 1. Architecture in one screen

- **Two control layers at the top:**
  - **Control Room** — changes the *view* (Rank by, Form, Weight class, Roster,
    Show top, Min UFC bouts, Prime window). Every dependent section re-renders
    *instantly* via a `subscribe(name, fn, keys)` / `broadcast(key)` registry.
  - **Model Tuning** — changes the *model* (12 knobs). **Apply & recompute**
    reruns the full rating engine (~8–9 min, CPU-bound) into a throwaway
    local-temp snapshot, rebinds the in-memory frames, and calls `redraw_all()`.
    **Reset** restores the baseline instantly.
- **Rendering pattern (do not deviate):** charts are live `plotly.graph_objects.FigureWidget`s
  updated in place via `show_fig(fw, fig)`; tables/markdown are `ipywidgets.HTML`
  set via `.value`. We never use `Output` + `fig.show()` — it fails to refresh in
  the VS Code notebook host and hangs under headless `nbconvert`.
- **Chart functions** live in `analysis/viz.py` and return `go.Figure`. The
  notebook builds the figure, then syncs it into the section's FigureWidget.
- **Data** is read from `data/snapshots/<date>/*.parquet` (build-time artifacts);
  the notebook is otherwise read-only over them.

### Rating vocabulary (drives most views)
- **Rank by** (lens): `Wins` → `Finishes` → `Clean` → `Strength` → `Complete` → `Legacy`.
  Internally these map to rating streams `canonical / method / method_integrity /
  method_performance / method_integrity_performance / whr`.
- **Form** (window): `Now` (current μ), `Peak` (best 5-yr run), `Prime` (sustained
  N-yr run sized by the Prime sliders).
- Column resolution lives in `selected_rating_col()` / `select_public_rating_column()`.

---

## 2. Chart catalog

Order is top-to-bottom in the notebook. "Controls" = which top-level knobs drive it.

### The Rankings (Leaderboard) — table
- **Shows:** the pound-for-pound board for the current lens/window, split Men/Women.
- **Columns:** rank chip · Fighter · Rating · vs Wins (context delta, green/red) ·
  Division · Last (date) · Fights.
- **Order:** rating descending, top `Show top` per roster after `Min UFC bouts` filter.
- **Controls:** Rank by, Form, Prime sliders, Roster, Weight class, Show top, Min UFC bouts.

### Career Arcs (Trajectory) — multi-line chart
- **Shows:** selected fighters' ratings over time; shaded band = model confidence.
- **Encoding:** x = date, y = rating; one line per fighter; dots = bouts colored by
  finish method.
- **Order:** chronological; legend by selection order.
- **Controls:** Rank by (rating stream), local fighter multi-select.

### Risers & Fallers (Movers) — horizontal bar / diverging chart
- **Shows:** biggest rank changes vs the previous snapshot for the selected lens.
- **Encoding:** bar length = rank delta; up = gained rank, down = lost.
- **Order:** by absolute rank movement, top `Show top` of the top-50.
- **Controls:** Rank by, Form, Prime sliders, Min UFC bouts, Show top.

### Win Streaks — table + single-fighter timeline
- **Table shows:** longest unbeaten runs; columns rank · Fighter · Streak ·
  Division · Span · Avg opp · Titles · Finishes · Status (Active/how it ended).
- **Order:** by **Sort** (length / toughest schedule / most title wins), filtered
  by Weight class + Roster + Min wins, top `Show top`.
- **Timeline:** pick a row or type a fighter → their rating arc with the streak
  window shaded gold (markers = win/loss/draw).
- **Controls:** Weight class, Roster, Show top; local Sort + Min wins + picker.

### Résumé vs Rating (Placement) — scatter + division-share bar
- **Scatter shows:** "real deal vs hot start." x = Rated bouts (résumé depth),
  y = rating, dot **size ∝ rank** (bigger = higher ranked), **color = division**;
  top fighters labeled. Top-right = elite rating on a deep résumé.
- **Bar shows:** how the current top-100 splits across weight classes.
- **Order:** scatter is top-`Show top` by rating; bar is count per division desc.
- **Controls:** Rank by, Form, Prime sliders, Show top, Min UFC bouts.

### Weight Classes (Divisions) — timeline + year bar + contenders table
- **Timeline:** each selected division's top-tier average rating over time;
  toggle **Score** (absolute) vs **Index** (shape only, re-based).
- **Year bar:** the single-year pecking order across selected divisions.
- **Table:** current top-8 per selected division.
- **Order:** timeline chronological; bar by rating desc within the chosen year.
- **Controls:** Rank by, Form, Prime sliders, Show top; local division multi-select,
  year, Score/Index.

### Tale of the Tape (Compare) — prob bar + résumé cards + profile/odds charts
- **Shows:** head-to-head — model win probability bar, **closeness** (1 = coin-flip,
  0 = blowout), side-by-side résumé cards, each fighter's rating profile bars and
  market-implied win probability over time.
- **Order:** n/a (two-fighter view).
- **Controls:** local Fighter A / Fighter B.

### What Moved a Fighter's Rating (Rating Story) — waterfall + table
- **Shows:** which fights helped/hurt a fighter; the **Clean** (tainted-win) and
  **Strength** (opposition) layers. A summary line totals Clean / Strength / Net.
- **Encoding:** waterfall bars right = gain, left = loss; table columns Date ·
  Opponent · Clean · Strength · Net (signed, green/red).
- **Order:** biggest swing fights first, top `Rows`.
- **Controls:** local Fighter + Rows.

### Under the Hood (Adjustments) — two audit tables
- **Factors table:** Layer · Factor · Direction (Boost/Penalty) · Uses (bar) · Typical %.
- **Biggest fights table:** Date · Fighter · Opponent · Net % (signed color) · Why · Layer.
- **Order:** factors by frequency; fights by absolute effect, top `Rows`.
- **Controls:** local Layer / Effect / Fighter / Rows.

### Era Check — heat map
- **Shows:** weight-class × year top-tier strength, **normalized within each year**
  (100 = the deepest division that year; lower = how far behind the era's best).
- **Encoding:** rows = division, cols = year, color = strength index 80–100.
- **Order:** read each column (year) to rank divisions for that season.
- **Controls:** Show top; local division multi-select + year range.

---

## 3. Conventions (match these in any new view)

- **Visual identity:** import `THEME` and the registered `ufc_dark` plotly template
  from `analysis.viz`. Use the existing helpers: `chart_widget()`, `show_fig()`,
  `html_box()`, `table_html()`, `note()`, `msg()`, `heading()`, `_rank_chip()`,
  `_BASE_TABLE_STYLES`.
- **Reactivity:** build the figure fresh in a `draw_*()` function; never call
  `.show()`. Sync with `show_fig(fw, fig)`. Tables → `widget.value = table_html(styler)`.
- **Wiring:** `subscribe("name", draw_fn, {keys})` for Control-Room-driven views;
  also `register_section("name", draw_fn)` (subscribe does this for you) so a model
  recompute refreshes it. Wire local widgets with `_observe(widget, lambda *_: draw())`
  — **never** `widget.unobserve_all()` (it strips ipywidgets' internal options sync).
- **Language is MMA-first.** No model jargon in anything a human reads: say
  "weight class" not "division-stream", "rated bouts" not "rating_periods", "how a
  fight ended" not "method_score". Every chart gets a `note()` caption a fan can read.
- **Ordering is explicit and stated** in the caption (e.g., "ranked by … , top N").
- **Empty states:** show `msg("…")`, never a blank widget or a traceback.
- **Test it:** add assertions to `tests/test_notebook_dashboard.py` (the harness
  execs every cell with `NB_STRICT=1`, then drives controls and checks the new
  FigureWidget has traces / HTML has content).

---

## 4. Recipe — add a new view

1. **Data/compute** → add a function to `analysis/viz.py` returning a `go.Figure`
   (or a DataFrame for a table). Apply the `ufc_dark` template, set `title`,
   `xaxis_title`, `yaxis_title`, and a readable `hovertemplate`. Add a smoke
   assertion in `tests/test_viz_smoke.py`.
2. **Section cell** → add a new `SECTION = r"""..."""` string in `build_notebook.py`:
   - create `fw = chart_widget()` and/or `tbl = html_box()`;
   - define `def draw_x(): ... show_fig(fw, build_fig(...))` reading the global
     frames (`rc`, `ratings_histories`, `fights`, …) and the relevant controls;
   - `display(...)` the controls, the widget(s), and a `note()` caption;
   - call `draw_x()` once, wire local widgets with `_observe`, and
     `subscribe("x", draw_x, {keys})`.
3. **Register** the cell in `CELLS` with an `md("## Title\n\n<fan-readable intro>")`.
4. **Rebuild + test:** `python analysis/build_notebook.py` then
   `python -m pytest tests/test_notebook_dashboard.py tests/test_viz_smoke.py -q`.

---

## 5. Expansion backlog — prompts for new insight charts

Each item is a self-contained prompt. Data sources in `data/snapshots/<date>/`:
`canonical_fights`, `canonical_rounds`, `canonical_fighters`, `ratings_current`
(+ all `mu_*`, `five_year_peak_*`, `sustained_peak_*` columns), the per-stream
`ratings_history*` tables, `sleeve_attribution`, `integrity_appearances`,
`performance_appearances`, `division_resume`, `fighter_dominance`,
`fight_dominance`, `odds_lines`, `fightmatrix_rankings`,
`datalab_*` (scorecards, processed stats, fighter details), `calibration_residuals`,
`ped_confirmed_bouts`, `missed_weight_bouts`, `crossorg_fights`.

### A. Finishing & fight-outcome insight
- **Finish-rate by weight class & era.** Stacked/100% area of KO-TKO vs Submission
  vs Decision share per weight class over time. Order divisions by current finish
  rate. Data: `canonical_fights.method_class` + division + date. Control: Weight class.
- **Round-by-round finish distribution.** Where fights end (R1–R5) by weight class
  and method. Data: `canonical_rounds` / `canonical_fights` end round. Heat map,
  rows = division, cols = round.
- **Fastest finishers / "danger index".** Fighters ranked by finish rate weighted by
  opponent quality and earliness of the finish. Bar, top-N, ordered desc.

### B. Judging & scorecard insight (uses datalab scorecards)
- **Controversial decisions.** Decisions where the model's pre-fight win prob
  disagreed most with the result, or split/majority cards with wide judge spread.
  Table ordered by disagreement; link to closeness from `h2h_prediction`.
- **Judge/round agreement.** Distribution of 10-9 vs 10-8 rounds, unanimous vs
  split share by era. Data: `datalab_scorecards`. Bars over time.

### C. Betting market vs model (uses odds_lines)
- **Calibration curve.** Bucket fights by model win-prob; plot model prob vs actual
  win rate vs market-implied prob. Line/scatter with a 45° reference. Data:
  `odds_lines` + `calibration_residuals`. Shows where the model/market are sharp.
- **Biggest upsets the model "saw".** Fights where a heavy underdog (by market) won
  AND the model rated them close. Table ordered by market underdog odds.
- **Favorite vs underdog win rate by division/era.** Already partially in
  `favorite_underdog_performance_table`; surface it as a chart.

### D. Age, physical & style profile (uses canonical_fighters)
- **Age curve.** Average rating (or win rate) vs fighter age at fight time, per
  weight class. Line with a confidence band; mark the peak-age. Data: fight dates
  + `canonical_fighters.dob`.
- **Reach / height / stance advantage.** Win rate as a function of reach
  differential; southpaw-vs-orthodox win rate. Bars / binned line.
- **Title-reign timelines.** Gantt-style chart of championship reigns per division
  (who held the belt when, number of defenses). Data: title-fight flags in
  `canonical_fights`. Order by division then date.

### E. Career-shape & longevity
- **Peak vs longevity quadrant.** x = career length (years active), y = peak rating;
  dot size = title wins; color = division. Identifies short-peak vs long-prime
  careers. Data: `ratings_history` span + `sustained_peak_*` + `division_resume`.
- **Time-at-#1 / time in top-5.** For each fighter, count rating periods spent ranked
  top-1/top-5 in their division. Bar, ordered desc.
- **Decline detector.** Fighters whose current μ is furthest below their 5-yr peak
  (fading) vs those at/above peak (ascending). Two ranked lists.

### F. Division / era structure
- **Division depth (gap chart).** For a weight class, the rating gap between #1 and
  #5/#10/#15 over time — a tight gap = a deep, competitive division. Line per
  threshold. (Replaces the cut "crowdedness/entropy" idea with a fan-readable one.)
- **Cross-era bridge map.** Which fighters bridge eras (fought across many years) and
  how the engine uses them to calibrate. Data: `crossorg_fights` + long careers.
- **Champion lineage / who-beat-whom graph.** Directed graph of title-fight results
  within a division.

### G. Model-tuning sensitivity (ties into Model Tuning)
- **Tornado / sensitivity chart.** For a chosen fighter, how much their rating moves
  as each knob is swept ± one step (precomputed at apply-time). Horizontal bars
  ordered by absolute sensitivity. Makes the tuning panel's effect legible without
  a full rerun per knob.
- **Before/after diff view.** After a recompute, the top-N fighters who moved the
  most vs the baseline model (the panel shows a top-5 teaser today; make it a full
  ranked diff table with signed deltas).

### Acceptance criteria for any new chart
- Reads as MMA, has a title + axis labels + a one-line `note()` caption.
- Stated, sensible ordering; graceful empty state via `msg()`.
- Renders into a `FigureWidget`/`HTML` widget and is wired into the registry so both
  Control-Room toggles and a model recompute refresh it.
- Covered by a smoke assertion in the tests; `build_notebook.py` regenerated.
