# Notebook Chart Plan

> **Update 2026-06-25 (dashboard cleanup):** three of the boards below were
> removed per user review — **#1 Model Accuracy** (calibration curve, "means
> nothing"), **#6 Since Last Snapshot** ("useless"), and **#7 Ring Rust**. The
> `viz.py` helpers (`calibration_residuals_chart`, `snapshot_movers_chart`,
> `inactivity_table`) are kept and still unit-tested, just no longer wired into
> the notebook. Reworked in the same pass: **Most Dominant** (y-axis labels no
> longer clipped), **Legacy vs Prime** (name labels dropped, richer hover),
> **Risers & Fallers** (now a top-N diverging bar, not a 500-dot smear, and it
> no longer blanks under Peak/Prime form), **Title Lineage** (single belt-baton
> timeline with real reigns + defense counts), and the **Market vs Model**
> board (odds-impact chart now reads the real `perf_factor_odds` signal; the
> beat/missed-the-line chart is now per-fighter via a dropdown).
>
> **Status: ✅ IMPLEMENTED 2026-06-23.** All 12 ideas below were built and wired
> into `analysis/notebook.ipynb` (now 23 code + 22 markdown cells). New builders
> live in `analysis/viz.py`; new sections subscribe to the Control Room like the
> rest of the dashboard. Covered by `tests/test_chart_additions.py` and the
> `tests/test_notebook_dashboard.py` exec test (full suite: 169 pass). This file
> is kept as the design rationale / map of where each chart lives.

Forward-looking plan for charts to add to `analysis/notebook.ipynb`, written
against the **2026-06-23** snapshot. Every idea below is backed by data that is
already produced in `data/snapshots/<date>/` — no new engine work is required
unless noted.

## Design constraints (so additions match the existing dashboard)

- **Consulting style:** one clear title, short labels, focused color, a single
  takeaway, minimal chart noise. Accent (amber) is reserved for the #1 / hero
  mark only.
- **Reactivity:** charts are `FigureWidget`s mutated in place via `show_fig`;
  tables are `widgets.HTML`. Never use `Output` + `fig.show()` (it hangs under
  `nbconvert` and won't refresh in the VS Code host).
- **Control Room wiring:** a section calls `subscribe(name, draw_fn, keys)` with
  the global keys it depends on (`lens`, `time`, `prime_years`, `prime_min`,
  `division`, `gender`, `top_n`, `min_fights`), or `register_section` if it only
  has local controls.
- **Theme:** pull colors/fonts from `analysis.viz.THEME`; charts inherit the
  `ufc_dark` Plotly template automatically.

## Status legend

- 🟢 **Ready** — a `viz.py` helper already exists; only a notebook cell + wiring
  is needed.
- 🟡 **Small build** — one new `viz.py` function over existing columns.
- 🔵 **Larger build** — new aggregation logic + a new function.

---

## Tier 1 — quick wins (helper already exists, just wire a cell)

### 1. 🟢 "How accurate is the model?" — calibration reliability curve
- **Theme / placement:** *Under the Hood* (right after the sleeve audit), or a
  new **Model Accuracy** section.
- **Why it's first:** `calibration_residuals_chart` is *already imported* in the
  notebook's data-load cell (`build_notebook.py` line ~77) but **never
  displayed** — a clear oversight. The artifact `calibration_residuals.parquet`
  (172 rows) is built every run.
- **Shows:** predicted win-probability bin (x) vs empirical win rate (y) with the
  45° "perfectly calibrated" reference line; point size = `n`; a Brier-score
  caption. Segment dropdown over `segment_type` (overall / by division / by era).
- **Data:** `calibration_residuals` cols `segment_type, segment_value, prob_bin,
  predicted_mean, empirical_win_rate, residual, brier, n`.
- **Takeaway:** "When the model says 70%, the favorite wins ~70% of the time."
  Credibility anchor for every other board.
- **Controls:** local segment dropdown; no Control Room deps.

### 2. 🟢 Division parity — who's deep, who's top-heavy
- **Theme / placement:** inside the **Weight Classes** block (after the era heat
  map), sharing its year-range slider.
- **Shows:** `division_entropy_chart` — normalized entropy / density per division
  for the selected year(s): a flat top (many fighters near the top rating) = a
  deep, competitive division; a spike = one dominant champ over a thin field.
- **Data:** `division_entropy` cols `year, division, fighters_in_division,
  top_mu_mean, top_mu_std, top_mu_range, density_per_100_mu, entropy_normalized`.
- **Takeaway:** "Lightweight is a shark tank; the belt means more in a thin
  division." Pairs naturally with the existing strength timeline.
- **Controls:** subscribe to `top_n`; reuse the section's `divx_year_range`.

### 3. 🟢 Market vs Model — biggest disagreements & favorite/underdog hit rate
- **Theme / placement:** new **Market vs Model** section (the odds layer is
  currently only visible per-fighter inside *Tale of the Tape*).
- **Shows:** two ready helpers —
  `favorite_underdog_performance_chart` (do model-favored fighters actually win?)
  and `odds_impact_chart` / `odds_adjustment_distribution_chart` (where market
  odds pushed a rating). Lead banner from `odds_coverage_summary` (6,567 covered
  fights, ~78% since 2010).
- **Data:** `odds_lines` (market_favorite/underdog, no-vig probs) +
  `performance_appearances.market_residual`.
- **Takeaway:** "The model and Vegas agree ~X% of the time; here's where the
  engine sees value the market missed."
- **Controls:** subscribe to `division`, `gender`.

## Tier 2 — one new viz function over existing columns

### 4. 🟡 Striking fingerprint — target & position mix
- **Theme / placement:** extend **Tale of the Tape** (per-fighter), or a new
  **Fighting Styles** section.
- **Shows:** for the selected fighter, a normalized stacked bar / radar of where
  their significant strikes land (head / body / leg) and from where (distance /
  clinch / ground), plus control-time share. Side-by-side for the two compared
  fighters reuses the existing A/B layout.
- **Data:** `canonical_rounds` (40,124 rows; `head/body/leg_landed`,
  `distance/clinch/ground_landed`, `ctrl_seconds`) — **the richest, least-used
  artifact in the project.**
- **New helper:** `striking_profile_chart(rounds, fights, fighter)` aggregating
  career round rows. (`striker_grappler_scatter` already exists for the scatter
  variant and could be revived alongside it.)
- **Takeaway:** "Volkanovski is a distance head-hunter; Khabib lives in top
  control." Turns raw strike tables into one readable style signature.

### 5. 🟡 Dominance leaderboard — winning *and* dominating
- **Theme / placement:** *The Rankings* (a complementary board) or *Résumé vs
  Rating*.
- **Shows:** top fighters by `mean_dominance` (strike differential + control +
  sub attempts, z-scored) with a min-wins gate; or a rating-vs-dominance scatter
  to separate "dominant finishers" from "decision grinders."
- **Data:** `fighter_dominance` (`fighter, wins, mean_dominance`) + `rc`.
- **New helper:** `dominance_leaderboard_chart(fighter_dominance, rc, n, min_wins)`.
- **Takeaway:** "Highest-rated isn't always most dominant — here's who actually
  steamrolls people."

### 6. 🟡 What changed this snapshot — movers since last update
- **Theme / placement:** top of **Risers & Fallers** (the notebook already loads
  `PREV`, the previous snapshot, but nothing surfaces a since-last-update view).
- **Shows:** biggest rating gainers/losers vs the prior snapshot, with the new
  fights that caused the move (e.g. the just-added Topuria–Gaethje and
  Pereira–Gane title results). A diverging horizontal bar.
- **Data:** `rc` vs `PREV["ratings_current"]` on the selected rating column;
  fight context from the 5 newly scraped events.
- **New helper:** `snapshot_movers_chart(rc, prev_rc, rating_col, n)`.
- **Takeaway:** "What the latest card actually changed" — the natural home for
  freshly scraped data, and a strong landing chart after each refresh.

### 7. 🟡 Inactivity ledger — who's fading on the clock
- **Theme / placement:** *The Rankings* (a caption/table) or *Career Arcs*.
- **Shows:** rated fighters ranked by `months_inactive` with the
  `activity_mu_penalty` already applied, i.e. "ring rust" cost in rating points.
- **Data:** `ratings_current` (`months_inactive`, `activity_mu_penalty`,
  `mu_*_activity_adjusted`).
- **New helper:** `inactivity_table(rc, n)` (table, not a chart).
- **Takeaway:** "These top names haven't fought in 18+ months — the board
  discounts them by N points until they return."

### 8. 🟡 Integrity ledger — PED / DQ / missed-weight impact
- **Theme / placement:** *Under the Hood* (the integrity layer lost its dedicated
  view in the 2026-05-28 refactor; `integrity_factor_audit_table` was removed).
- **Shows:** fights where the integrity sleeve fired, the rating it cost, and a
  per-fighter rollup. `rc` carries `ped_confirmed_fights, dq_wins,
  missed_weight_wins` counts for a summary strip.
- **Data:** `integrity_appearances` (`integrity_factor_ped/dq/missed_weight,
  integrity_weight`) + `sleeve_attribution.integrity_delta`.
- **New helper:** `integrity_ledger_table(integrity_appearances, sleeve_attribution, rc)`.
- **Takeaway:** "Where the clean-record adjustment bites, and by how much."
- **Note:** also fixes the stale `tests/test_viz_smoke.py` import that references
  the removed `integrity_factor_audit_table` / `ped_impact_chart`.

---

## Tier 3 — larger / exploratory

### 9. 🔵 Legacy vs Prime divergence — smoother vs windowed
- **Shows:** scatter of `sustained_peak_headline_mu_whr` (Legacy) vs the windowed
  `..._method_integrity_performance` prime, labelling fighters the two methods
  most disagree on (era-bridge artifacts vs genuine longevity).
- **Data:** `ratings_current` (both peak families already present).
- **Takeaway:** "Where the era-comparable smoother and the windowed prime tell
  different stories" — a methodology talking-point chart.

### 10. 🔵 Finish-rate / method mix by era & division
- **Shows:** small-multiples or stacked area of KO / Sub / Decision share over
  time, optionally per division (are fights ending faster or going to the cards
  more?).
- **Data:** `canonical_fights` (`method_class`, `event_date`, `weight_class`).
- **New helper:** `method_mix_timeline_chart(fights, divisions, year_range)`;
  subscribe to `division`, reuse the Weight Classes year range.

### 11. 🔵 Title lineage / reign map
- **Shows:** per division, a timeline of title wins/defenses (belt changing
  hands) using the championship flags and title-ladder data.
- **Data:** `performance_appearances` (`is_championship_bout`,
  `fighter_entered_as_champion`) + `division_resume` (`division_title_wins,
  division_title_defenses, division_last_title_win_date`).
- **Takeaway:** "Who held each belt and for how long" — a natural companion to
  *Division Leaders*.

---

## Suggested rollout order

1. **Tier 1 (1–3)** first: all three are ~a cell each because the `viz.py` helpers
   already exist; #1 (calibration) is essentially a bug-fix since it's already
   imported. Biggest credibility + coverage gain for least code.
2. **#6 (snapshot movers)** next: highest storytelling value for a data refresh,
   and it uses the already-loaded `PREV` frame.
3. **#4 (striking fingerprint)** to finally exploit the 40k-row `canonical_rounds`
   artifact.
4. Remaining Tier 2/3 as appetite allows.

Each new section should ship with a one-line `note()` caption (what the chart
means) and, where it reads a rating, subscribe to the relevant Control Room keys
so it re-ranks with the rest of the dashboard.
