# Differentiator audit — 2026-08-18

Commissioned to earn or delete the engine's four differentiators over a plain
skill ladder, and to make that question affordable enough to ask again.

## Summary

The pipeline is between **22× and 64× faster** with every generated artifact
bit-identical to the committed snapshots, and the evaluation that was previously
unaffordable now runs in **13 seconds**. On that evaluation:

- The base rating's **probability scale is broken**. Scored one-step-ahead, the
  canonical Glicko-2 stream has log-loss 0.6986 against a coin flip's 0.6931 and
  Brier 0.2509 against 0.25 — worse than no model at all. This is not a new
  measurement error; the repo's own committed `calibration_residuals.parquet`
  says the same thing and has since the diagnostic was written.
- **Market-relative performance does not exist as a mechanism.** `perf_factor_odds`
  is computed, clipped, persisted and charted, but is not a term in the signal
  that produces `performance_weight`. Odds reach a rating only through a
  rank-gated upset tie-breaker that fires on **35 of 16,958** appearance rows.
  The paired effect on held-out log-loss is −1.4×10⁻⁶ [−3.2×10⁻⁶, +3.4×10⁻⁷] —
  five orders of magnitude below the method-scoring effect, and not resolved.
- **Method and dominance scoring earns its place**, and is the only mechanism
  that does: it improves held-out log-loss by 0.00083 [0.00024, 0.00141] over
  the binary stream on 3,534 paired bouts.
- **Both sleeves make prediction slightly but resolvably worse.** The integrity
  sleeve costs 0.00051 [0.00006, 0.00094]; the performance sleeve costs 0.00139
  [0.00080, 0.00197].
- Every stream is far behind the **closing-odds benchmark** (0.6135 log-loss,
  0.7145 AUC against the best stream's 0.6772 and 0.5791).
- Two mechanisms have effects an **order of magnitude larger** than any sleeve,
  and both were previously argued on other grounds: the **WHR smoother** beats
  the canonical filter by 0.01520 log-loss [0.00070, 0.02996], and
  **cross-organization history** improves held-out *UFC* prediction by 0.01871
  log-loss [0.01415, 0.02318] once a selection control is applied. The
  expanded scope is now justified on prediction for the first time.

Two data defects were found while building the harness and are reported below
rather than quietly fixed: a drawn title fight **vacates** the modelled
championship lineage, and every cross-organization row is stored winner-first.

Phases are reported in the order the evidence had to be gathered — 0, A, B, D,
E, F, then C — because the keep/delete decisions in Phase C depend on all of it.

## Phase 0 — making the question affordable

### Where the time actually went

A stage profile of `rate_snapshot.run()` on the UFC-only snapshot, before any
change (CPU seconds, 8,479 bouts):

| Stage | CPU s | share |
| --- | ---: | ---: |
| `peaks: five_year_peak` ×9 | 496.6 | 56.6% |
| `peaks: sustained_peak` ×9 | 303.5 | 34.6% |
| `division_resume_rows` | 32.7 | 3.7% |
| `run_whr` ×4 | 16.8 | 1.9% |
| `build_performance_appearances` | 13.3 | 1.5% |
| `peak_appearance_quality` | 8.7 | 1.0% |
| weighted Glicko ×3 | 4.8 | 0.5% |
| `_run_canonical_engine` | 1.3 | 0.1% |
| everything else | 0.6 | 0.1% |
| **total** | **878** | |

The headline result is that **the rating layer was never the cost**. The
Glicko-2 and WHR updaters together are 2.5% of the run. Over 91% went to the
period/peak and division-resume layer — the *board*, which the evaluation does
not need at all.

Two distinct defects produced that:

1. **Per-window pandas.** `_per_fighter_window_period` re-derived every
   per-appearance quantity inside the window loop — `_context_adjustment` alone
   built nine `Series` and a `concat` for each of a fighter's windows. Every one
   of those terms is a *row* property that does not depend on the window.
2. **An E×F term.** `prefight_ranking_context` rebuilt a full Python-sorted rank
   map of all active fighters at every event. The product of events × fighters
   is 1.9M for UFC-only, 40.6M for complete-edge and **855M** for raw — which is
   exactly the superlinearity behind "3.9 h for 65k fights against 49 min for
   18k".

### What changed

Row-wise work was hoisted out of the loops it did not belong in; the window scan
became a two-pointer over numpy slices; the rank maps became a numeric lexsort
keyed on ids assigned in sorted-name order, so the `(-mu, name)` tie-break is
preserved exactly; `iterrows` and per-event `to_dict("records")` were replaced
with array slicing. No scoring rule, constant or policy was changed.

### Cost table

CPU seconds on this machine. "Exact" means every generated artifact was compared
column-by-column against the committed snapshot and matched, NaN patterns
included.

| Work | Before | After | Speedup | Verified |
| --- | ---: | ---: | ---: | --- |
| `rate_snapshot.run()`, UFC-only (8,479 bouts) | 878 | 29.3 | **30×** | 17/17 artifacts exact |
| `rate_snapshot.run()`, complete-edge (18,394) | 2,925 | 74.5 | **39×** | 17/17 artifacts exact |
| `rate_snapshot.run()`, reliability (18,404) | 2,922 | 85.3 | **34×** | 17/17 artifacts exact |
| `rate_snapshot.run()`, raw (65,070) | 14,041 | 636 | **22×** | 17/17 artifacts exact |
| `reconcile_bouts` (80,667 perspectives) | ~720 | 11.3 | **64×** | 80,667/80,667 rows exact |
| — component: `rolling_peak` ×18 | 800.1 | 5.1 | 157× | bit-exact |
| — component: `division_resume_rows` | 33.1 | 0.17 | 195× | bit-exact |
| — component: `peak_appearance_quality` | 8.7 | 0.20 | 44× | bit-exact |
| — component: `build_performance_appearances` | 13.3 | 2.0 | 6.5× | 50/50 columns exact |
| Evaluation sweep, 9 variants × 3,534 held-out bouts (642 events) | never ran | **13** | — | — |
| Cross-org 35-point weight grid | never ran | 144 | — | — |

The last two rows are the point of the exercise. A prequential comparison of
this size was previously a multi-day proposition and so was never run; it is now
a coffee break, and the fold results are cached and resumable.

### Why the evaluation is cheap

Three structural facts, none of which required an approximation:

1. **Filters need no refit.** Glicko-2 is an online updater, so a fighter's
   rating entering a bout depends only on their earlier bouts. One chronological
   sweep therefore *already contains* every one-step-ahead out-of-sample
   prediction. Refit-per-fold is reserved for WHR, which is a whole-history
   smoother and genuinely uses look-ahead.
2. **The board is not needed.** Peaks, division resumes and every ranking
   artifact — over 91% of the pipeline — play no part in a win-probability
   forecast and are simply not computed.
3. **The weight tables are invariant.** Integrity and performance weights, bout
   reconciliation, identity resolution and organization mapping do not depend on
   any rating parameter, so they are built once per snapshot and shared across
   every variant and every grid point.

## Phase A — the yardstick

`ratings/prequential.py` extends the temporal discipline of `whr_backtest.py`
into a general rolling-origin harness. For each held-out event, predict from
information available strictly before it, then score.

- **Metrics:** log-loss, Brier, accuracy, AUC, reliability curve and expected
  calibration error, in `calibration_residuals.parquet` conventions.
- **Segments:** overall, division, era, finish vs decision, favourite vs
  underdog, cross-org vs UFC-only, and participant-completeness band.
- **Benchmarks:** closing odds with the vig removed (the hard baseline), p = 0.5
  (naive), and the current production streams. FightMatrix appears nowhere.
- **Sample sufficiency:** every row carries `n` and an `n_sufficient` flag
  against a stated floor (default 200); nothing below it is concluded from.
- **Resumability:** results are cached per `(variant, folds, parameters)`, so an
  interrupted sweep resumes and partial results compose.

### Two decisions the harness forced

**Temperature calibration.** Every variant shares a badly overconfident
probability scale, so raw log-loss mostly measures that shared defect rather
than the mechanism under test. A single temperature parameter is therefore
fitted on a *calibration fold set drawn strictly before* the evaluation folds,
and results are reported both raw and calibrated. AUC is reported alongside
because temperature cannot move it — it isolates whether a mechanism adds
*information* from whether it fixes *scale*.

**Side symmetrization.** `fighter_a` wins 63% of UFC bouts and **100%** of
cross-organization bouts, because both sources store the winner first. Log-loss,
Brier and accuracy are exactly invariant to which side is labelled "a" (verified
numerically, not assumed), so this does not bias them — but it leaves AUC
undefined on the cross-org subset. A deterministic `fight_url`-keyed flip
restores a two-class label without touching the other metrics. The naive
benchmark is p = 0.5 rather than "always fighter_a", which would score 63% on
row order alone.

## Phase B — ablations

3,534 paired held-out bouts, every event from 2010 on, both fighters with at
least 3 prior appearances. Deltas are challenger minus baseline on log-loss, so
**negative favours the challenger**; intervals are 2,000-sample paired
bootstrap. Temperature-calibrated.

| Isolates | Baseline → challenger | delta | 95% interval | verdict |
| --- | --- | ---: | --- | --- |
| method scoring | canonical → method | −0.00083 | [−0.00141, −0.00024] | method **helps** |
| method + dominance | full → binary scoring | +0.00033 | [0.00000, 0.00067] | method **helps** (marginal) |
| integrity sleeve | method → method_integrity | +0.00051 | [0.00006, 0.00094] | sleeve **hurts** |
| integrity score damp | perf → perf without damp | −0.00047 | [−0.00091, −0.00003] | damp **hurts** |
| performance sleeve | method → method_performance | +0.00139 | [0.00080, 0.00197] | sleeve **hurts** |
| market weighting | full → no odds | −1.4×10⁻⁶ | [−3.2×10⁻⁶, +3.4×10⁻⁷] | **no mechanism** |
| cross-org bridge | full → no org weight | 0 (exactly) | [0, 0] | inert on a UFC-only scope |

Overall standings (temperature-calibrated). The variants are scored on 3,534
held-out bouts; the table below is the 3,149 of those that also carry a closing
line, so the market benchmark is measured on identical fights rather than on a
more forgiving subset:

| variant | log-loss | Brier | accuracy | AUC | ECE |
| --- | ---: | ---: | ---: | ---: | ---: |
| closing odds (benchmark) | 0.6135 | 0.2127 | 0.6612 | 0.7145 | 0.0185 |
| method | 0.6772 | 0.2422 | 0.5671 | 0.5791 | 0.0366 |
| method_integrity | 0.6777 | 0.2425 | 0.5662 | 0.5772 | 0.0371 |
| canonical | 0.6780 | 0.2426 | 0.5648 | 0.5759 | 0.0367 |
| method_performance | 0.6786 | 0.2429 | 0.5623 | 0.5722 | 0.0347 |
| method_integrity_performance | 0.6786 | 0.2429 | 0.5623 | 0.5722 | 0.0347 |
| binary scoring (`abl_no_method`) | 0.6789 | 0.2431 | 0.5606 | 0.5710 | 0.0342 |
| naive p = 0.5 | 0.6931 | 0.2500 | 0.5659 | 0.5000 | 0.0659 |

Without recalibration every stream except `method` is **worse than a coin flip**
on log-loss, and every stream is worse than one on Brier.

### WHR — the smoother earns the headline, its sleeves are unresolved

WHR is the only variant class that pays a refit per fold, so it is scored on
fewer events. Two separate runs: 150 held-out events (1,003 paired bouts) for
the smoother-versus-filter question, and 40 events (265 paired bouts) for the
sleeve ablations.

**The smoother beats the filter, and it is the second-largest effect in this
report.** On 1,003 paired held-out bouts, temperature-calibrated:

| variant | log-loss | Brier | accuracy | AUC | ECE |
| --- | ---: | ---: | ---: | ---: | ---: |
| whr | **0.65650** | 0.23224 | 0.6191 | **0.65277** | 0.02698 |
| method | 0.66991 | 0.23875 | 0.5862 | 0.61500 | 0.02587 |
| canonical | 0.67170 | 0.23959 | 0.5793 | 0.61080 | 0.02177 |

| comparison | log-loss delta | accuracy delta | verdict |
| --- | --- | --- | --- |
| canonical → whr | **−0.01520 [−0.02996, −0.00070]** | **+3.99 pts [+0.40, +7.28]** | smoother **wins** |
| method → whr | −0.01340 [−0.02792, +0.00099] | +3.29 pts [−0.30, +6.88] | not resolved |

WHR was already the default headline, chosen on the argument that a smoother is
comparable across eras where a filter is not. That argument is now backed by
held-out prediction against the plain filter. Against the best filter variant it
misses resolution by a hair, so the honest claim is "the smoother beats the
canonical ladder, and is at least as good as the method stream", not "the
smoother is best".

**The WHR sleeve ablations do not resolve, and are not made to.** At 40 events
(265 paired bouts) every log-loss interval spans zero:

| Isolates | delta | 95% interval |
| --- | ---: | --- |
| WHR dominance amplification | −0.00000 | [−0.00546, +0.00487] |
| WHR integrity score damp | +0.00099 | [−0.00139, +0.00331] |
| WHR sleeves together | −0.00051 | [−0.00276, +0.00182] |
| WHR cross-org bridge | 0 (exactly) | [0, 0] — no-op on a UFC-only scope |

Point estimates lean the same way the Glicko arm did — the sleeves do nothing
useful — but this fold count cannot say so, and the harness declines to. Getting
the WHR arm to the online arm's power needs roughly 13× the folds and, because
every fold is a full smoother refit, roughly 13× the time. That is a property of
the model, not an oversight.

### Market weighting is not a small effect, it is not a mechanism

That row is not rounded to zero by accident, and the code explains it. (The
cross-org row *is* exactly zero: on a UFC-only snapshot every `org_weight` is
1.0, so the ablation is a no-op by construction and is tested in Phase D
instead.) `performance_weight`
is driven by

```python
winner_signal = method_log + opp_quality_log + upset_log + streak_log + weight_class_log
```

`perf_factor_odds` is not a term. It is computed, clipped to the sleeve
envelope, written to `performance_appearances.parquet` and plotted by
`analysis/viz.py` as though it moved ratings — the module docstring already
concedes it is "now informational". The only path from a betting line to a
rating is `_upset_odds_signal` inside `_upset_factor`, which is gated behind a
divisional rank gap of 6 or more and only bites when it exceeds the rank signal
already present. Measured on the snapshot: it changes `performance_weight` on
**35 of 16,958** appearance rows, by at most 0.0077.

This is the one mechanism where "do not delete for a small effect" does not
apply. −1.4×10⁻⁶ log-loss on a base of 0.68 is not a small effect being
dismissed; it is the numerical residue of a term that is not in the equation.

## Phase D — the cross-organization weight

`compute_fight_weights` bridges a non-UFC bout through its two participants'
UFC-anchored caliber percentiles, clipped to `[floor, cap]`, with `unknown_pct`
standing in for a fighter who never reached the UFC. A 7 × 5 grid over floor and
`unknown_pct` was scored on the depth-one complete-edge scope, 6,300 held-out
bouts, temperature-calibrated. No FightMatrix quantity was consulted.

**The floor is identified, and it points in opposite directions depending on
what you want to predict.**

| floor (at `unknown_pct` 0.30) | log-loss, cross-org bouts (n=1,127) | log-loss, UFC bouts (n=5,173) |
| ---: | ---: | ---: |
| 0.00 | 0.61514 | 0.65026 |
| 0.25 | 0.61445 | 0.65073 |
| 0.40 | 0.61253 | 0.65141 |
| **0.50 (current)** | **0.61063** | **0.65188** |
| 0.60 | 0.60851 | 0.65241 |
| 0.75 | **0.60682** | 0.65318 |
| 1.00 | 0.60730 | 0.65425 |

On cross-organization bouts the curve is monotone improving up to 0.75 and then
turns back down at 1.00 — a genuine interior optimum, not a boundary artifact —
and AUC tracks it (0.7214 at floor 0, 0.7418 at 0.75). On UFC bouts the curve is
monotone in the *opposite* direction: every point of extra cross-org weight
makes UFC forecasts slightly worse. The current 0.5 is 21st of 35 on cross-org
bouts and 18th of 35 on UFC bouts — a compromise that is optimal for neither.

**Verdict: `floor` is TUNED-BUT-CONFLICTED.** The data identifies it clearly; it
is the *objective* that is unspecified. If the product is an all-time board
spanning organizations, the evidence supports raising the floor to ~0.75. If the
product is a UFC forecaster, it supports lowering it to 0. The spread is 2.71%
of the best value on cross-org bouts and 0.63% on UFC bouts, so the cost of
choosing wrongly is real but bounded.

Worth naming plainly: raising the floor to 0.75 lifts mean cross-org weight from
0.653 to 0.785, which is also the direction that would close the Fedor gap the
expansion report left open. That report said the move "must be argued on its own
evidence rather than smuggled in under a data-completeness change". This is that
argument, and it is made on held-out prediction rather than on agreement with
any external ranking.

**Verdict: `unknown_pct` is UNIDENTIFIED.** Sweeping it across its whole range at
the current floor moves log-loss by 0.00011 on UFC bouts, 0.00216 on cross-org
bouts and 0.00048 overall — under a fifth of a percent everywhere, and at floor
0.75 it moves the result by 0.00003. Most unknown fighters are clipped up to the
floor before the parameter can bite. The current 0.30 is a **defensible prior,
not a tuned result**, and should be described that way.

## Phase E — the expanded scope

The previous decision was argued on rank correlation against FightMatrix. That
framing is retired here. The question asked instead: holding the held-out bouts
fixed to **UFC bouts only**, does a model that has seen a fighter's non-UFC
record forecast their next UFC fight better than one that has not?

Two arms were built from the same depth-one complete-edge snapshot, differing
only in whether `crossorg_fights.parquet` was admitted, and scored on the
identical 3,534 held-out UFC bouts.

| arm | log-loss | Brier | accuracy | AUC |
| --- | ---: | ---: | ---: | ---: |
| with cross-org :: method | **0.66355** | 0.23557 | 0.5908 | **0.64049** |
| with cross-org :: canonical | 0.66496 | 0.23626 | 0.5857 | 0.63491 |
| with cross-org :: method_integrity_performance | 0.66527 | 0.23643 | 0.5846 | 0.63293 |
| UFC-only :: method | 0.67753 | 0.24235 | 0.5671 | 0.59787 |
| UFC-only :: canonical | 0.67822 | 0.24269 | 0.5648 | 0.59474 |
| UFC-only :: method_integrity_performance | 0.67867 | 0.24292 | 0.5623 | 0.59224 |

Paired, every variant favours the cross-org arm and every interval clears zero:
log-loss −0.01326 to −0.01398, accuracy +2.09 to +2.38 points. **These effects
are an order of magnitude larger than any sleeve ablation in Phase B.**

### The selection control, which matters

The 302 seed profiles were drawn from FightMatrix rankings, so *having*
cross-organization history is itself correlated with being good. Measured
directly: in the 1,082 held-out bouts where exactly one fighter has cross-org
coverage, **that fighter wins 60.9% of the time**. Presence is a quality signal,
and a naive reading of the table above would partly be reading that signal.

Restricting to bouts where **both** fighters are covered holds presence constant
and isolates the *content* of the extra history:

| coverage | n | paired log-loss delta | accuracy delta |
| --- | ---: | --- | --- |
| both fighters covered | 2,189 | **−0.01871 [−0.02318, −0.01415]** | +2.47 pts [+0.64, +4.25] |
| one fighter covered | 1,082 | −0.00651 [−0.01217, −0.00106] | +1.94 pts, not resolved |
| neither covered | 263 | −0.00538, not resolved | not resolved |

The benefit **survives the control and is larger inside it**. Cross-organization
history earns its place on prediction, not on cohort membership.

**Verdict: the expanded scope is now justified on out-of-sample performance**,
which is the first time any such argument has been available. Two honest limits
remain: the "both covered" population is itself a ranked-cohort neighbourhood,
so this establishes the benefit *within* that population rather than for the
whole roster; and the `neither` row shows a small unresolved drift, which is the
whole rating field moving when new edges are admitted, not a per-fighter effect.

## Phase F — depth two

The brief gates depth two on Phase E showing predictive value, or on the need to
create the partial-completeness middle that Phase E requires to separate
policies. **Both gates are now met.** Depth-one cross-org history improves
held-out UFC prediction with the effect surviving a selection control, and
`complete_edge` and `reliability` remain indistinguishable (9,915 vs 9,925
admitted edges) precisely because completeness at depth one is bimodal — 4,226
of 4,337 profiles reconcile exactly and everything past the boundary scores
zero, leaving the geometric mean nothing to interpolate.

**Recommended, not executed.** 26,944 identities are queued with stop reason
`maximum_depth`; at the existing one-request-per-second pacing that is roughly
7.5 hours of sustained traffic against a third-party site, which should be a
deliberately authorized run rather than a side effect of an audit. The crawler,
queue, pacing and stopping rules need no changes.

It should be framed as **building the partial-completeness middle**, not as
chasing accuracy. Depth-two fighters will inherit the incompleteness depth-one
fighters now carry, and the ranked-cohort selection shape propagates with them;
what the run buys is a population where `reliability` and `complete_edge` can
finally be told apart.

## Phase C — what to keep, what to cut

| Mechanism | Verdict | Basis |
| --- | --- | --- |
| Market-relative performance | **DELETED** | No mechanism: not a term in the signal; 35/16,958 rows; paired effect −1.4×10⁻⁶, interval spans zero |
| Method + dominance scoring | **KEPT on accuracy** | −0.00083 log-loss [−0.00141, −0.00024] over binary scoring, resolved |
| Participant-caliber cross-org bridge | **KEPT on accuracy, and re-tune the floor** | −0.0187 log-loss [−0.0232, −0.0142] on the presence-controlled subset — the largest effect measured |
| Integrity sleeve (rating stream) | **KEPT as an explicit judgement, demoted from the headline** | Costs 0.00051 log-loss [0.00006, 0.00094]; re-expressed as a direct board discount |
| Performance sleeve (rating stream) | **KEPT under protest, flagged for removal** | Costs 0.00139 log-loss [0.00080, 0.00197] — resolved, but 0.2% of the base value |
| WHR smoother as the headline | **KEPT on accuracy** | −0.01520 log-loss [−0.02996, −0.00070] and +3.99 accuracy points over the canonical filter |
| WHR sleeves | **UNRESOLVED — do not defend on accuracy** | Every interval spans zero at 40 folds; needs ~13× the folds to settle |

### Streams that produced nothing anyone read

`whr_integrity` and `whr_performance` were each a full WHR pass plus two
period-score passes on every rebuild, and no board, chart, table, export or test
consumed either — they were produced and dropped. Removed 2026-08-19. The
public "All-time" lens reads `whr_integrity_performance` and the headline reads
base `whr`; both are kept, so no published board moved. This is the compounding
benefit the brief predicted: cutting a stream removes its share of every future
rating run, and the UFC-only rebuild fell from 29.3 s to 28.3 s on top of the
30× already gained.

### What was deleted, completely

The odds-to-rating path is gone in one change: `_MoneylineAnchors`, `_odds_factor`,
`_upset_odds_signal`, the `perf_factor_odds` column and its schema entry, the
four `PERF_ODDS_*` / `PERF_UPSET_ODDS_*` constants, `viz.odds_impact_chart`, the
`mkt_impact` notebook panel in both the generator and `analysis/notebook.ipynb`,
the two tests that asserted on them, and the `CHART_PLAN.md` and `README.md`
claims. No flag, no dead branch, no deprecated column.

**Closing odds themselves stay**, and are now put to better use: they are the
hard benchmark the engine is scored against in `ratings/prequential.py`. The
mechanism was deleted; the data was promoted.

Measured effect of the deletion on a full rebuild of the 2026-08-13 snapshot:

| artifact | change |
| --- | --- |
| `canonical`, `method`, `whr`, `*_integrity` streams | **unchanged** — they never used odds |
| `performance_appearances.performance_weight` | 35 rows, max 0.00765 |
| `performance_appearances.perf_factor_upset` | 19 rows, max 0.0135 |
| `ratings_current.mu_method_performance` | 1,575 fighters, max 0.652 mu |
| `ratings_current.rank_method_performance` | **29 fighters move, by at most 2 places** |

The headline WHR board does not move. Snapshots need a rebuild to pick this up.

### Why the integrity sleeve is kept but not as a rating stream

The normative case is the strongest in the brief: an integrity-discounted board
answers "should this win count", which no forecast can score. But the sleeve as
built cannot deliver it, and the numbers say so plainly.

It fires on **27 of 8,479 bouts** — 5 PED-confirmed, 22 DQ, 1 missed weight.
`loaders/ped_flags.py` is deliberately conservative, flagging only bouts whose
official text says the result was overturned for a failed test, so the entire
PED corpus is five fights: Sherk once, Belfort three times, Tibau once.

Worse, damping 27 bouts inside a *likelihood* does not stay local. WHR re-anchors
the global mean every pass, so the perturbation propagates: measured on the
snapshot, the integrity stream **raised 325 of 401 rated fighters and lowered
76**, with the largest rise (+24.1 mu) exceeding the largest fall (−14.1 mu). A
sleeve whose docstring promises it "only penalises, never rewards" lifts four
fifths of the board.

So the mechanism is re-expressed in `ratings/boards.py` as a **direct debit on
the fighter being discounted, and on nobody else**, with `integrity_ledger()`
printing the receipt. On the same snapshot exactly 10 fighters are debited:

| fighter | undiscounted rank | discounted rank | cost | flagged results |
| --- | ---: | ---: | ---: | --- |
| Vitor Belfort | 121 | **233** | 75.0 | 3 PED |
| Sean Sherk | 67 | 80 | 25.0 | 1 PED |
| Deiveson Figueiredo | 43 | 48 | 15.0 | 1 missed weight |
| Aljamain Sterling | 25 | 28 | 10.0 | 1 DQ |
| Frank Mir | 89 | 98 | 10.0 | 1 DQ |
| Diego Sanchez | 126 | 133 | 10.0 | 1 DQ |
| Matt Hamill | 215 | 235 | 10.0 | 1 DQ |
| CB Dollaway | 327 | 342 | 10.0 | 1 DQ |
| Patrick Cote | 340 | 347 | 10.0 | 1 DQ |
| Cody Brundage | 378 | 386 | 10.0 | 1 DQ |

That is a discount. The penalty scale is a **stated judgement**
(`INTEGRITY_PENALTY_SCALE`), not an estimate — nothing fitted it, because
nothing could.

### The performance sleeve, kept under protest

It resolvably *hurts* prediction (+0.00139 log-loss), which is an argument for
deletion, and it has no normative claim of the integrity sleeve's kind. It is
kept in this pass only because it is load-bearing for the published period
scores and boards in a way the market factor was not, so removing it is a board
change rather than a dead-code change and deserves its own decision. The effect
is 0.2% of the base value — the brief's "do not delete for a small effect" cuts
both ways here, and this is flagged rather than settled.

## Defects found, reported rather than fixed

### A drawn title fight vacates the modelled championship

`prefight_ranking_context` advanced the title lineage behind
`if not winner or not division or not is_championship_bout: continue`. A draw
leaves `winner` as `NaN`, and `not NaN` is `False` in Python — so a drawn title
bout falls *through* the guard and writes a champion that matches nobody,
clearing the division's lineage.

Five bouts in the UFC-only snapshot are affected, and they are exactly the
immediate rematches after a drawn title fight:

| Rematch | Fighter not flagged as champion | Preceding draw |
| --- | --- | --- |
| UFC 136 (2011-10-08) | Frankie Edgar | UFC 125, Edgar–Maynard |
| UFC 209 (2017-03-04) | Tyron Woodley | UFC 205, Woodley–Thompson |
| UFC 263 (2021-06-12) | Deiveson Figueiredo | UFC 256, Figueiredo–Moreno |
| UFC 306 (2024-09-14) | Alexa Grasso | Grasso–Shevchenko 2 |
| UFC 63 (2006-09-23) | Jens Pulver | UFC 41, Penn–Uno |

A draw retains the title in reality, so this is a defect. It was **preserved
exactly** through the performance work — correcting it inside a change whose
whole warrant is bit-identical output would have been smuggling — and is pinned
by `test_drawn_title_bout_vacates_the_modelled_lineage` so the current behaviour
cannot drift by accident. Fixing it is a one-line change to that guard plus a
snapshot rebuild, and it should be decided on its own.

### Every cross-organization row is stored winner-first

All 9,692 decided cross-org bouts in the depth-one complete-edge scope have
`fighter_a` as the winner; `fighter_a_outcome` is `W` for every one. The UFC
table has the same bias more weakly, at 63%. This does not bias log-loss, Brier
or accuracy, and it does not reach the rating engine, which is symmetric in the
two sides. It does make AUC undefined on that subset, and it makes any
"always pick fighter_a" baseline look strong for no reason. The harness
symmetrizes sides deterministically before scoring.

## What this cost, and what remains unknown

### What it cost

| Activity | CPU |
| --- | ---: |
| Stage profiling, before and after, four scopes | ~1.1 h |
| Exactness verification, four scopes × 17 artifacts | ~13 min |
| Online ablation sweep, 9 variants × 3,534 bouts, 642 events | 13 s |
| WHR ablation sweep, 7 variants × 40 folds (refit per fold) | 39 min |
| Cross-org weight grid, 35 points | 144 s |
| Scope comparison, 2 arms × 3 variants | 99 s |

Everything after the one-time verification runs in minutes. The single expensive
item left is WHR, because a whole-history smoother genuinely has to be re-fit per
fold; that is a property of the model, not of the code.

### What remains unknown

1. **The WHR *sleeve* ablations are underpowered and stay that way.** The
   smoother-versus-filter question was resolved by running 150 folds
   (−0.01520 log-loss, resolved), but at 40 folds no WHR *sleeve* effect
   resolves — every interval spans zero. Reaching the online arm's power needs
   roughly 13× the folds, and every fold is a full refit.
2. **Why the probability scale is broken is diagnosed, not fixed.**
   `predict_win_prob_from_ratings` shrinks by the *opponent's* φ only, where
   Glickman's own two-player predictive form uses the combined
   `sqrt(φ_a² + φ_b²)`. That under-shrinks and is a plausible cause of the
   overconfidence, but no fix was attempted or measured here.
3. **Whether the sleeves help the *board* is not measured and may not be
   measurable.** Everything here scores next-fight prediction. A period score is
   a different claim, and the brief is right that some of it is normative.
4. **The cross-org benefit is established inside a ranked-cohort neighbourhood**,
   not for the whole UFC roster. Depth two inherits that shape.
5. **The drawn-title-bout lineage defect is preserved, not fixed.** Five bouts
   are affected. It needs its own decision and a snapshot rebuild.
6. **`unknown_pct` cannot be settled by this data** and will not be until the
   partial-completeness middle exists.

## Reproducing

```
python build_prequential_evaluation.py data/snapshots/2026-08-13 \
    --mode all --since-year 2010 --online-only
python build_prequential_evaluation.py data/snapshots/2026-08-13 --events 40
python build_crossorg_weight_sweep.py \
    data/snapshots/2026-08-14-fightmatrix-depth-one-complete_edge
python build_scope_prequential_comparison.py \
    data/snapshots/2026-08-14-fightmatrix-depth-one-complete_edge
```

Finalized snapshots are never written to: when a snapshot carries a `*_FINALIZED`
marker the drivers redirect their artifacts to `--out-dir`.
