# Model overhaul 2026-05-15 — running log

## What changed in this pass (code)

1. **Method tiers widened** (`ratings/constants.py`, `loaders/ufcstats_loader.py`,
   `ratings/performance_adjustment.py`):
   - Finish (KO/TKO, Sub) = 1.00
   - 5-round dominant unanimous (every judge cards 50-45 or 49-46) = 0.97
   - Unanimous (otherwise) = 0.95
   - Majority / Split = 0.90 (collapsed — both are 3-judge ambiguous)
   - DQ = 0.85
   The 5-round dominant tier is derived in `decision_quality_score` from
   judge cards (each judge's margin ≥ 3 on a 5-round bout, i.e. lost at
   most one round).

2. **Integrity penalty moved to the score layer** (`quality_score_winner`
   in `ratings/performance_adjustment.py` + WHR `_build_appearances` reads
   `quality_score_winner`). A PED-confirmed win now produces S_j ≈ 0.55
   for the flagged winner on the Glicko-2 method/method+integrity and the
   WHR sleeve streams — not just a sleeve update-weight damp. DQ wins
   floor at 0.75, missed-weight wins at 0.70. The legacy sleeve weight
   factors are retained on the audit table.

3. **Glicko-2 integrity stream switched to `score_mode=quality_method`**
   (`ratings/rate_snapshot.py`) so the score-layer integrity damp reaches
   the integrity stream. (Was previously `score_mode=method` which reads
   the un-damped base METHOD_SCORES.)

4. **Opponent-strength dominance bumped** (`ratings/constants.py`):
   - `SUSTAINED_PEAK_OPP_MAX_WEIGHT` 2.0 → 2.6
   - `PERIOD_TITLE_FIGHT_WEIGHT_MULT` 1.25 → 1.40
   So a title-fight win against an elite opponent now weighs much more in
   the peak window than a non-title win against a mid-tier opponent.

5. **Tests** (130 pass, including 8 new/rewritten ones for the new band
   and integrity score damp).

## What this produced on the 2026-05-13 snapshot

WHR + Integrity + Performance (10-Year headline) top 5:
1. Jon Jones — 2019.28
2. Georges St-Pierre — 2009.95
3. Amanda Nunes — 1988.93
4. Anderson Silva — 1962.38
5. Demetrious Johnson — 1954.04

## Honest finding: the model is now ready, but the data is not

The score-layer integrity damp works (verified by `pytest`), but the
`ped_confirmed` flag is essentially empty in this snapshot:

- `ped_confirmed_fights > 0` for **1 fighter total** (Gleison Tibau).
- Jones (USADA turinabol findings around UFC 200, UFC 214, UFC 232) — 0
  flagged fights.
- Silva (drostanolone, UFC 183 result overturned) — 0 flagged fights.

The detector `loaders/ped_flags.py` only fires on Greco's `details_text`
when the literal phrase "failed drug test" or "illegal inhaler use" is
present. Greco's free-text for affected bouts uses other wording
("overturned to No Contest", "USADA violation", date-stamped sanctions
on the fighter's profile rather than the bout, etc.), so the regex
misses the cases that matter most.

So #3 of the user's request (PED penalty heavy enough that it sits
"barely above a loss") is implemented at the rating layer, but the
*upstream data labelling* is the blocker.

## Next steps before the GSP/Silva/Jones ordering shifts

Two options, in priority order:

A. **Curate a vetted PED-bout list** as a side-table the integrity loader
   merges in. Anti-doping reportage is well-documented enough to build a
   short list of (fighter, event_name) tuples for the high-profile cases:
   - Jones: UFC 200 cancellation, UFC 214 win overturned, UFC 232 (low
     pulsing levels — not overturned but flagged), UFC 285 etc.
   - Silva: UFC 183 vs Diaz (overturned), UFC 234 NSAC suspension.
   - BJ Penn UFC 137, Frank Mir, Brock Lesnar UFC 200 overturn, Sean
     Sherk, Vitor Belfort, etc.
   This is the right approach — it's auditable and grows over time.

B. **Broaden the regex** to include "overturned", "USADA", "NSAC",
   "anti-doping", "performance-enhancing", "no contest". Risk: false
   positives for unrelated NCs (eye pokes, accidental fouls overturning
   results). Not recommended without follow-up curation.

## Recommendation

The model is now correct under the assumption that the PED labels are
correct. The next session should: build a curated PED-bout side-table
under `data/external/integrity/` and wire `build_integrity_flags` to
union it with the Greco regex output. Once the labels are in, the
GSP/Silva/Jones ordering will move as you wanted because the score-layer
damp + heavier opp-strength weighting are already in place.

## 2026-05-15 — curated PED labels (seed pass)

Wired the curation infrastructure end-to-end. Scope this session was
**wire infra first, curate incrementally** (per user direction): build
the loader + tests + a small well-sourced seed CSV, leaving deep
curation for follow-up.

### Code

- `loaders/integrity_flags.py`: added `_load_curated_ped_bouts()` and
  `_apply_curated_ped_flags()`. `build_integrity_flags` now takes
  `curated_ped_csv` kwarg, defaulting to
  `data/external/integrity/ped_bouts.csv`. Curated rows are unioned
  with the regex hits; on overlap, curated wins (carries the citation).
  Unresolved `(event_date, event_name)` and unresolved fighter names are
  WARNINGs, not crashes — curation bugs live in the CSV, not the code.
- `tests/test_integrity_flags.py`: +5 tests (empty file, hit, missing
  event, missing fighter, regex-vs-curated precedence). Full suite
  **135/135 pass**.
- `data/external/integrity/ped_bouts.csv`: 4 seed rows.

### Curated side-table breakdown

Total rows: **4**. (One pre-existing regex hit on Tibau remains, so 5
PED-flagged bouts in the rated set.)

| sanctioning_body | rows |
|---|---|
| CSAC | 1 (Sherk UFC 73) |
| NSAC | 3 (Belfort 2013 TRT-era wins) |

| finding_type | rows |
|---|---|
| in_competition_positive_no_overturn | 1 |
| out_of_competition_positive_window  | 3 |

### Top-flagged fighters (rated set)

| fighter | ped_confirmed_fights |
|---|---|
| Vitor Belfort | 3 |
| Sean Sherk    | 1 |
| Gleison Tibau | 1 (regex, pre-existing) |

### Before / after on the 10-year headline (mu_whr_integrity_performance)

| fighter | before | after | Δ |
|---|---|---|---|
| Jon Jones              | 2019.28 | 2018.57 | −0.71 |
| Georges St-Pierre      | 2009.95 | 2010.08 | +0.13 |
| Amanda Nunes           | 1988.93 | 1988.94 | +0.01 |
| Anderson Silva         | 1962.38 | 1961.71 | −0.67 |
| Demetrious Johnson     | 1954.04 | 1954.06 | +0.02 |
| Islam Makhachev        | 1944.26 | 1944.27 | +0.01 |
| Alexander Volkanovski  | 1938.17 | 1938.17 |  0.00 |
| Israel Adesanya        | 1898.69 | 1898.71 | +0.02 |
| Sean Sherk             | 1726.91 | 1724.30 | −2.61 |
| Vitor Belfort          | 1671.27 | 1643.39 | −27.88 |

Belfort moves the most (≈ −28 mu), as expected — 3 of his TRT-era wins
got damped. Sherk moves slightly. The big names (Jones, Silva) barely
move because their **marquee PED bouts (UFC 214, UFC 183, UFC 200) are
not in `canonical_fights.parquet`** — they were already overturned to
No Contest by their commissions and the Greco loader excludes NC fights
with `exclusion_reason = method_overturned`. The score-layer damp can
only operate on bouts in the rated set, so curating those (event,
fighter) rows produces no effect by construction.

### Curation gaps left for follow-up

- **Jon Jones turinabol (UFC 214)** — excluded as NC, not in rated set.
  Curation can't reach it without changing the loader's NC-exclusion
  rule (out of scope for the integrity damp).
- **Anderson Silva drostanolone (UFC 183)** — same story; excluded as
  method_overturned.
- **Brock Lesnar clomiphene (UFC 200 vs Hunt)** — same; excluded as NC.
- **TJ Dillashaw EPO (UFC on ESPN+ 1)** — Dillashaw LOST that fight;
  the score-layer damp only fires on the winner side, so no flag to
  add on his prior wins without a primary source tying USADA's finding
  retroactively to a specific earlier bout.
- **Chael Sonnen / Nate Marquardt / Sean Sherk-window / Bigfoot Silva
  multi-test history** — pre-USADA-era; only the specific bouts whose
  result stood AND where the winner had a sanction tied to that bout
  are eligible. Sherk-Franca UFC 73 is the cleanest such case and is
  included.
- **Yoel Romero (ibutamoren), Lyoto Machida (DHEA), Cris Cyborg
  (stanozolol)** — checked: Romero's sanction was tied to a 2015 sample
  not retroactively covering UFC 221; Machida's 2016 finding was tied
  to a fight he LOST; Cyborg's 2011 stanozolol was Strikeforce-era, no
  UFC bouts during the sanction window.
- **Post-USADA era (DFSI 2024+)** — not yet researched. Snapshot
  extends to 2026-05-09; this is the most under-curated window.

### Recommended next session

Curate the long-tail of in-competition positives where the win stood
(pre-USADA NSAC/CSAC era plus any DFSI post-2024 cases), since those
*can* land in the rated set. The marquee USADA-era overturned-to-NC
cases are unreachable by curation alone — they would require the
project to decide whether to *include* those NC bouts as ordinary
fights with the integrity damp applied, instead of excluding them
outright. That is a project-level decision separate from this task.
