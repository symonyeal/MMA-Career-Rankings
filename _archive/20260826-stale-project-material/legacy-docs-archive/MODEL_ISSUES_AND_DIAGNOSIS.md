# Model Issues And Diagnosis

This file is the running diagnosis log for model concerns raised in chat. Each
new user-raised issue should be added here before solution design begins.

## Overall Model Goal

The goal of all engines and models in this project is not to produce a generic
"current rank" leaderboard. The goal is to measure:

1. **Career peak**: the highest level a fighter reached, taking the full career
   context into account.
2. **Sustained peak**: the fighter's best multi-year peak window, taking the
   chosen `x` years of peak form and opponent/context quality into account.

Everything else should support those two outputs. Current rating state may
exist internally because chronological rating engines need it to process fights,
estimate opponent strength at the time, and compute peak windows. But current
rank is not the headline product and should not be presented as a default
ranking category.

Status labels:

- `Open`: accepted as a model concern; no implementation chosen yet.
- `Needs data`: likely valid, but blocked by missing or incomplete source data.
- `Under review`: enough data exists for analysis, but no fix is selected.
- `Resolved`: a fix has been implemented and verified.

## Issue 1: UFC Longevity And Sample Size Are Underweighted

Status: `Open`

Raised concern:

> 7 UFC fights for Shavkat vs 13 for Khabib. UFC fights are significantly more
> important than non-UFC fights. Weights should reflect that. The longer a
> fighter has a career in UFC, the better.

Current diagnosis:

The current canonical stream is event-period Glicko-2 over UFC-only fights.
This means non-UFC fights do not directly count at all in the headline stream.
However, the model also does not explicitly reward a longer proven UFC career.
It accounts for sample size mostly through uncertainty (`phi`), not through a
resume or longevity bonus.

Example observed in the 2026-05-12 snapshot:

- Khabib Nurmagomedov: 13 UFC rating periods, `mu_canonical = 2261.3`,
  `phi_canonical = 131.2`.
- Shavkat Rakhmonov: 7 UFC rating periods, `mu_canonical = 2268.2`,
  `phi_canonical = 154.1`.

Shavkat's central estimate is slightly higher, but his uncertainty is much
higher. A conservative view such as `mu - phi` would put Khabib ahead. This
suggests the issue is not that non-UFC fights are overweighted; rather, current
headline ranking uses central `mu` without a sufficient reliability or proven
resume adjustment.

Why this matters:

An undefeated 7-fight UFC run can outrank a more proven 13-fight UFC run if the
newer fighter's opponents had high pre-fight Glicko ratings and the fighter's
higher uncertainty allows larger rating movement. For a human-facing ranking,
that may over-promote shorter UFC resumes.

Data currently available:

- UFC fight count/rating periods.
- Current and historical `mu`/`phi`.
- Event dates and inactivity.
- Title-fight flag from `weight_class`.

Data not yet modeled:

- Explicit UFC tenure bonus.
- Explicit reliability/longevity score.
- Conservative ranking column such as `mu - k * phi`.
- Resume score for number of high-level UFC wins.

## Issue 2: Win Streaks Need Opponent Ranking Context

Status: `Resolved`

Raised concern:

> Win streaks matter, but they matter significantly more against high ranked
> opponents. See if dataset includes their at-the-time UFC ranking. If unranked,
> holds no importance. The rankings are top 15 and champion or interim champion,
> so adjust that accordingly.

Current diagnosis:

The current project does not contain official at-the-time UFC ranking snapshots
for each bout. It has current FightMatrix rankings as a comparison source, but
those are current rankings/points, not historical UFC top-15 rankings at the
date of each fight. The Greco/UFCStats canonical fight table includes title
fight labels and event chronology, but not official contender ranks.

What the model currently does:

- It rewards win streaks indirectly in the performance sleeve through an
  opponent streak factor.
- It rewards opponent quality through opponent pre-fight `mu_canonical`.
- It does not know whether an opponent was UFC champion, interim champion, or
  ranked `#1-#15` on the fight date unless that status is inferable from title
  fight text.

Why this matters:

A long win streak against unranked opponents should not carry the same meaning
as a streak through ranked contenders, champions, or interim champions. The
current model can partially approximate this with opponent Glicko strength, but
it cannot reproduce official ranking-based logic without historical ranking
data.

Data currently available:

- `is_title_fight` from canonical fights.
- `weight_class` strings such as `UFC Middleweight Title Bout`.
- Opponent pre-fight Glicko rating.
- Current FightMatrix rankings only.

Data needed:

- Historical UFC ranking snapshots by date, division, rank `#1-#15`, champion,
  and interim champion.
- A fighter identity map between ranking names and canonical UFCStats names.
- Rules for how long a ranking snapshot remains valid before the next ranking
  update.

Initial diagnosis:

This should become a separate ranking-context feature or sleeve. It should not
be approximated from current rankings, because current rank would leak future
information into historical fights.

Resolution:

The performance sleeve now includes explicit rank/championship/P4P context
without using current external rankings as historical truth. For each bout,
`performance_appearances.parquet` records pre-fight model divisional rank,
pre-fight model pound-for-pound rank, inferred champion/interim-champion
status, and title-fight flags. Winners receive modest, auditable sub-factors:

- `perf_factor_rank_context` for top-15 divisional opponents or champions.
- `perf_factor_championship` for title-fight wins and wins over inferred
  champion/interim champion opponents.
- `perf_factor_p4p` for top-15 pound-for-pound opponents.

Unranked opponents remain neutral for the ranking and P4P factors. Official
historical UFC ranking snapshots are still a better future data source, but
the implemented model path no longer ignores ranking/championship/P4P context.

## Replacement Framework C: Depth, H2H, Density, Defense-Tail, And Recency Pass

Status: `Under review`

Principle:

The replacement resume framework must not let shallow-era percentiles, repeated
title-defense floor credit, uncapped head-to-head accumulation, sparse best
windows, or current-P4P inactivity dominate the result. These are class-level
mechanisms, not fighter-specific exceptions.

Formula changes implemented in `ratings/replacement_framework.py`:

- Era-depth shrinkage: each `(division, 3-year era)` cell now computes active
  fighter count `N` and `zeta = 1 - exp(-N / 50)`. Opponent `tilde_mu`,
  `rho_div`, `rho_p4p`, and fighter `tilde_B` are shrunk toward neutral `0.5`
  by this `zeta`.
- H2H control: pair cap reduced to `6`, total cap added at `55`, and non-title
  rivalries are weighted `0.5x`.
- Window density: 5-year and 10-year best-window objectives shrink `A_i` by
  fight frequency and shrink `C_i` by `0.5 + 0.5*zeta_freq`.
- Championship tails: defenses 1-3 retain polynomial kappa; defense 4 onward
  uses an exponential tail. The champion floor is now quality-aware and
  tail-diminished, so it remains a floor without bypassing diminishing returns.
- Title bonuses: title-finish and elite-capture bonuses now scale by opponent
  `q_ctx`.
- Current P4P recency: inactivity damp is flat through 9 months, soft through
  18 months, steeper through 24 months, and zero after 24 months.
- All-time pre-prime loss damping: losses before a fighter's first title fight
  if any, otherwise before first top-15 appearance, are damped.
- All-time championship adequacy: durable GOAT title credit is now capped by
  opponent-quality resume, deep-defense adequacy, and unique title-opponent
  breadth. This prevents narrow/repeated title reigns from receiving the same
  all-time credit as broad championship resumes.
- Championship repeat-opponent decay: repeated title wins over the same
  challenger now decay inside `C_i`, matching the existing repeat decay in
  `Q_i`.
- All-time title-loss handling: immediate post-reign losses are no longer
  automatically treated as post-prime, and losing as defending champion carries
  an all-time-only surcharge.

Expected effect:

The pass should lower thin-era title resumes and H2H stackers, penalize sparse
5-year windows, restore Topuria's current-P4P standing, and reduce late-bloomer
developmental loss drag without adding per-fighter rules.

Anchor verification on the 2026-05-12 snapshot after rerun:

- Tier-1 anchors passed, including Jones over Cormier by more than 50 in GOAT,
  GSP and Demetrious Johnson top-5 all-time, Cain over JDS, Islam over Usman,
  and Pereira top-10 in 5-year/all-time.
- Tier-2 passed after the championship adequacy/repeat pass: Matt Hughes
  all-time rank moved below top 15, Kamaru Usman all-time moved below top 12,
  Tim Sylvia all-time moved below top 25, Stipe 5-year moved below top 12,
  Khabib 10-year moved to top 12, Topuria current-P4P moved to top 15, and
  Charles Oliveira all-time moved to top 30.
- Still open: Cyborg requires an external-prior/cross-organization mechanism;
  no reliable pre-UFC prior was added in this pass.

## Comparison Note: Adesanya, Pereira, Du Plessis, Strickland

Status: `Under review`

Current 2026-05-12 canonical order among the four:

1. Alex Pereira: `mu_canonical = 2229.6`, `phi = 124.6`, 12 rating periods.
2. Dricus Du Plessis: `mu_canonical = 2210.3`, `phi = 125.4`, 10 rating periods.
3. Sean Strickland: `mu_canonical = 2099.3`, `phi = 107.6`, 25 rating periods.
4. Israel Adesanya: `mu_canonical = 2045.8`, `phi = 115.2`, 19 rating periods.

Diagnosis:

The current model strongly rewards recent results. Adesanya still has the best
historical sustained peak among the group, but his current canonical rating is
pulled down by recent losses to Pereira, Strickland, Du Plessis, Nassourdine
Imavov, and Joe Pyfer in the local snapshot. Pereira and Du Plessis are higher
because their recent title-fight sequences contain more wins against already
strong opponents.

This reinforces the distinction between:

- `current rating`: who the model thinks is strongest now.
- `career peak`: highest point ever reached.
- `sustained peak`: best multi-year high-level window.
- `resume ranking`: not yet implemented.

## Issue 3: Canonical Rank Overreacts To Close Split-Decision Upsets

Status: `Resolved`

Raised concern:

> Why this jump for a split decision win?

Current diagnosis:

The canonical stream is intentionally binary: win = `1.0`, draw = `0.5`,
loss = `0.0`. It does not distinguish a split decision from a dominant finish.
Therefore, a close split-decision upset over a high-rated opponent can produce a
large headline rank jump.

Example observed in the 2026-05-12 snapshot:

- Sean Strickland defeated Khamzat Chimaev by split decision on 2026-05-09.
- Before the fight, Strickland was canonical rank 56 with `mu = 2054.7`.
- After the fight, Strickland was canonical rank 32 with `mu = 2099.3`.
- Khamzat fell from canonical rank 7 with `mu = 2246.5` to rank 16 with
  `mu = 2175.2`.

The method stream partially damped this:

- Strickland moved from method rank 53 with `mu_method = 1974.7` to method rank
  40 with `mu_method = 2006.6`.
- Khamzat fell from method rank 8 with `mu_method = 2149.3` to method rank 15
  with `mu_method = 2098.8`.

Why this matters:

If the headline ranking is canonical, close decisions can look too similar to
dominant wins. The method stream behaves closer to the intended human
interpretation, but the default headline table still uses canonical central
`mu`.

Resolution:

Canonical remains intentionally binary for calibration/debug use, but it is no
longer the headline ranking surface. Default reporting now leads with
career/sustained peak columns on `method_integrity_performance`, where close
split decisions are damped by the method score before integrity/performance
context is applied.

## Issue 4: Peak Metrics Must Align With The Selected Stream

Status: `Resolved`

Raised concern:

> Why is all sleeves a separate column? It should be baked into all-time and
> sustained method.

Diagnosis:

The project had a stream-alignment mismatch. The preferred current view was
`mu_method_integrity_performance`, but all-time and 5-year peak displays were
using plain `career_peak_mu_method` and the old
`sustained_peak_mu_method` column name. That mixed
different model philosophies in one report.

Resolution:

`rate_snapshot.py` now computes career and 5-Yr Peak values for every method
sleeve stream, including:

- `career_peak_mu_method_integrity_performance`
- `five_year_peak_mu_method_integrity_performance`

The notebook stream selector now resolves peak views to the selected stream
when those columns exist, falling back to plain method only for older snapshots.

## Issue 11: WHR Sleeves — Modular Sleeve Architecture Validated (2026-05-14)

Status: `Resolved`

Raised concern:

> Considering every sleeve should be modular, can I apply the sleeves on WHR and see.

Design decision:

The Bradley-Terry log-likelihood in WHR has gradient `g = s - p` and curvature
`h = -p(1-p)` per fight. A sleeve weight `w` scales only those likelihood terms
(`g *= w`, `h_diag *= w`). The Wiener-process and anchor priors remain
unweighted — temporal coupling and global scale stay structural constraints.
This is mathematically identical to the Glicko-2 weighted-engine semantics:
"this fight contributes `w` times as much evidence." The tridiagonal structure
is preserved so the Thomas algorithm still applies.

Implementation:

- `ratings/whr.py` — `_build_appearances` reads optional `weight_a`/`weight_b`
  fight columns into `app_weight`; Newton step scales `g` and `h_diag` by
  `app_weight` before adding priors. `run_whr` accepts `out_col` parameter.
- `ratings/rate_snapshot.py` — three sleeved WHR runs wired after the base WHR
  using `_attach_appearance_weights` (already generic). Streams:
  `whr_integrity`, `whr_performance`, `whr_integrity_performance`.
- `ratings/constants.py` — `WHR_SLEEVE_STREAMS` tuple added.
- `_attach_activity_adjusted_mu` made dynamic (finds all `mu_*` columns instead
  of hardcoded list).

Key empirical finding (2026-05-14 snapshot):

WHR is substantially more resistant to sleeves than Glicko-2. Largest sustained-
peak delta under WHR I+P vs WHR base: Alex Pereira +19.2 mu. Under sleeved
Glicko-2, the same sleeves move fighters by hundreds of mu units.

This is expected: WHR's joint global estimation propagates a fight's weight
adjustment through the entire career arc via the coordinate-ascent smoother.
A dominant KO of a champion lifts the surrounding time period's rating slightly
rather than stamping a large multiplier at a single event. The ranking order
within the top 30 is nearly identical across all four WHR variants — Jones →
GSP → Silva top-3 on all streams — confirming the consensus is robust. The
sleeves refine margins; they do not destabilize the leaderboard.

Practical interpretation:

- WHR base: era-fair, finish-agnostic. Best for "who dominated their era."
- WHR I+P: era-fair + finishing/quality reward. Modest additional signal.
- Method I+P (Glicko-2): finish-heavy, strongest performance amplification.
- WHR I+P is now the second headline alongside WHR base; Method I+P kept as
  comparison. `RANKINGS_SUMMARY.md` surfaces all four streams.

## Issue 5: Current Rank Is Not A Project Goal

Status: `Resolved`

Raised concerns:

> What are Current All-Sleeves Rank and Current All-Sleeves mu? There is only
> supposed to be the all-time and sustained peak.

> Why is there a current rank? There should not be anything like that in the
> whole model.

> The overall goal for all engines and models is to measure their career peak,
> taking everything in context, and sustained peak, taking the x years of peak.

Current diagnosis:

The engine still computes current ratings for each stream, including
`mu_method_integrity_performance`, because current form is useful for model
debugging and prediction. However, the user-facing default ranking philosophy
has shifted to two historical views only:

- all-time/career peak, using all sleeves;
- sustained peak, using all sleeves once the 10-year metric is implemented.

The previous response mixed in current all-sleeves rank out of habit from the
project's older current-rating tables. That creates confusion because it
implies a third primary ranking surface. Going forward, default summaries
should omit current rank entirely unless explicitly requested.

Stronger diagnosis:

Current `mu` is a state variable required by Glicko-style chronological updates.
It should not be treated as a model objective. The model objective is contextual
career peak and contextual sustained peak.

Expected default reporting columns:

- `career_peak_mu_method_integrity_performance`
- rank of `career_peak_mu_method_integrity_performance`
- `sustained_peak_mu_method_integrity_performance`
- `five_year_peak_mu_method_integrity_performance` as a shorter-window diagnostic

Optional/debug-only columns:

- `mu_method_integrity_performance`
- rank of `mu_method_integrity_performance`

Resolution:

The engine still persists current `mu` values because chronological Glicko
updates need current state and the debug notebook still needs prediction
inputs. Default reports and notebook controls now lead with historical
career/sustained peak views, especially
`career_peak_mu_method_integrity_performance` and
`sustained_peak_mu_method_integrity_performance`. Current `mu` is labeled as
debug state where exposed.

## Issue 6: Sustained Peak Should Be 10 Years; 5-Year Window Must Be Renamed

Status: `Resolved`

Raised concern:

> Sustained peak should be 10 years. Rename column for 5 years to 5-Yr Peak.

Current diagnosis:

The existing rolling-window metric is a 5-year opponent-weighted window. Calling
that value "sustained peak" is misleading now that the intended sustained peak
definition is a longer 10-year greatness window.

Immediate naming correction:

- Existing 5-year rolling metric should be labeled and stored as
  `five_year_peak_mu_<stream>`.
- User-facing label should be `5-Yr Peak`.

Implementation note:

- The 5-year metric has been renamed in generated snapshot columns and
  notebook display labels as `five_year_peak_mu_<stream>` / `5-Yr Peak`.
- The internal helper keeps a legacy `sustained_peak` alias only for backward
  compatibility; new model/reporting language should call this `5-Yr Peak`.

Future model requirement:

- Implement a true 10-year sustained peak metric.
- Reserve `sustained_peak_mu_<stream>` for that 10-year metric once built.
- Default historical reports should show career peak and sustained peak, with
  5-Yr Peak available as a shorter-window diagnostic.

Resolution:

`sustained_peak_mu_<stream>` is now emitted for every stream as a true 10-year
opponent-weighted rolling peak. `five_year_peak_mu_<stream>` remains available
and labeled as `5-Yr Peak`, but it is no longer the sustained-peak column.

## Issue 9: Peak Logic Must Be Principled With The Rating Sleeve

Status: `Resolved`

Raised concern:

> Peak logic should follow the others too. Entire project should be internally
> principally consistent.

Resolution:

Peak metrics now use actual bout opponents and the same opponent-quality
vocabulary as the performance sleeve:

1. **Career Peak** is the best 2-year window with at least 3 UFC fights,
   scored from the top 3 opponent-quality appearances.
2. **Sustained Peak** is the best 10-year window with at least 13 UFC fights,
   scored from the top 13 opponent-quality appearances. More than 13 fights
   in a window helps only when the additional fights are strong enough to
   enter that top-13 set.
3. **5-Yr Peak** is the shorter diagnostic window with at least 9 UFC fights,
   scored from the top 9 opponent-quality appearances.
4. Opponent quality is shared between `ratings.peaks` and the performance
   sleeve: pre-fight canonical mu, divisional rank, championship context, and
   P4P context are deduplicated into a monotonic quality signal.
5. The performance sleeve's redundant dominance/finish-speed/five-round
   triplet has been folded into `perf_factor_decisiveness`, and loser-side
   post-layoff losses now receive `perf_factor_activity_loss`.

## Issue 8: Performance Sleeve Saturated The Cap On 13.7% Of Wins

Status: `Resolved`

Raised concern:

> Suspect fighters (Jiri Prochazka, Shavkat Rakhmonov, Chris Weidman, Jacare
> Souza, Werdum, Yoel Romero, Brian Ortega, Junior Dos Santos) rank too high.
> Cap is being hit too often.

Current diagnosis (2026-05-12 snapshot):

* 13.7% of winner appearances saturate the `SLEEVE_FACTOR_MAX = 1.20` cap.
* The mean overshoot (`raw_product - 1.20`) among capped rows is +0.10; the
  max overshoot is +0.58. The clamp was hiding large headroom differences:
  Chris Weidman's mean overshoot was +0.19 (his wins routinely produced raw
  multipliers of 1.39+ that all clipped to 1.20).
* Suspect fighters cap on 50-67% of their wins:
  Romero 66.7%, Prochazka 66.7%, Ortega 62.5%, Werdum 58.3%, Weidman 50.0%.
* Dominance fires on 99.7% of winner rows (every KO/sub gets 1.06; even
  decision sweeps trip ~1.04), so the formula starts every win at a non-trivial
  baseline before any context applies.
* Rank-context / championship-context / P4P-context fired together on 121
  fights, producing a context-only product up to 1.236 by itself — the same
  opponent-quality information was triple-counted.
* The continuous "underdog" component inside `_opponent_strength_factor` fired
  on every plus-money winner regardless of rank gap; a #4 beating #3 with
  +110 odds was reading the same as a true upset.
* For losers the performance sleeve was inactive (weight = 1.0). GSP's loss
  to Matt Serra at UFC 69 — a textbook champion-collapse anchor event — had
  performance_weight = 1.0 because the engine only computed the factors on
  Matt Serra's winner-side row and never propagated them to GSP's loser row.

User-supplied calibration anchors:

* Strickland def. Adesanya (UFC 293) is the winner-side anchor: weight ≈ 1.20.
  Adesanya's loss is the symmetric loser-side anchor: weight ≈ 0.80.
* Matt Serra def. GSP (UFC 69) is a second-class anchor pair: Serra ≈ 1.20,
  GSP ≈ 0.80.
* Very few other fights should reach either extreme.

User-supplied upset definition:

* An upset is "someone outside top 6 beating the champion, or No 11 beating
  No 3 or something similar". A #3-vs-#4 fight is NOT an upset and must not
  trigger the upset bonus.

Resolution:

Performance sleeve rebuilt in `ratings/performance_adjustment.py`:

1. **Deduplicated opponent-quality combination.** Opponent-mu strength,
   division-rank context, championship context, and P4P context all measure
   "how elite was the opponent". Only the strongest single signal contributes
   to the per-fight log-signal `S`; the individual `perf_factor_*` columns
   are retained for audit transparency.
2. **Rank-gated upset factor (new).** `perf_factor_upset` fires only when
   `winner_rank - opponent_rank >= 6` (champion counts as rank 0, unranked
   as rank 16). A #3 vs #4 matchup has gap 1 and gets no upset bonus; an
   unranked challenger beating the champion gets full upset amplification.
   Moneyline odds can confirm the upset for fights with sparse rank data,
   but only when the rank gate is already open.
3. **Tanh-smoothed combination.** `S` is the additive sum of contributing
   log-deltas. `performance_weight_winner = 1 + 0.20·tanh(S/PERF_TANH_SCALE)`
   and `performance_weight_loser = 1 - 0.20·tanh(S/PERF_TANH_SCALE)`. The
   tanh asymptote replaces the hard 1.20 clamp, so extremes saturate softly
   and the same per-fight signal amplifies the winner's gain and damps the
   loser's hit symmetrically. With `PERF_TANH_SCALE = 0.20`, `S ≈ 0.40`
   maps to weight ≈ 1.193 and `S ≈ 0.60` maps to ≈ 1.199 — the cap is
   reserved for the truly extreme confluences.
4. **Loser-side performance sleeve.** Losers now carry the symmetric mirror
   weight (`1 - 0.20·tanh(S/scale)`) instead of the prior 1.0. The
   weight-class-down-loss amplifier remains a structural override (loss
   detracts more) and is not composed with the tanh damp.
5. **Audit columns added:** `perf_factor_upset`, `perf_upset_rank_gap`,
   `perf_signal_S`, `perf_winner_signal_S`.

Verification — measured on the 2026-05-12 snapshot before the rebuild and
recomputed after the rebuild (see `_diagnostics/saturation_diagnostic.py`).

## Issue 7: Weight-Class Movement Should Matter

Status: `Resolved`

Raised concern:

> Jumping weight classes is another factor, if you go up and win, it should add
> something, if you go down and lose, it should detract something.

Resolution:

The performance sleeve now includes `perf_factor_weight_class`. Each fighter's
previous standard UFC division is captured before the event, compared with the
current bout division, and persisted in `performance_appearances.parquet`.
Moving up and winning receives a modest winner-side boost. Moving down and
losing receives a modest loser-side update increase so the loss detracts more.
Unknown, catchweight, open-weight, first UFC appearances, same-division bouts,
upward losses, and downward wins are neutral.

## Issue 10: Readjusted Period Score Does Not Match The Stated Intent

Status: `Under review` (corrections shipped in `ratings/peaks.py`; new lists
pending review)

Raised concern:

> I readjusted the model so Kamaru Usman and Weidman were not throwing the
> ranking off, and Jones, GSP, and Johnson were topping the ranks. Evaluate
> what is going on there.

Evaluation on the reconciled 2026-05-14 / `2026-05-13` snapshot:

The readjusted period-score model in `ratings/peaks.py` (heavy
`PERIOD_LOSS_PENALTY = 55`, large title/champion/top-5 context bonuses, the
retired 2-year career peak) **partially** works. The GOAT cohort does sit at
the top: Anderson Silva #1, Daniel Cormier #2, Jon Jones #3 in
`sustained_peak_headline_mu_method_integrity_performance`. But the stated
intent is not met:

- **Kamaru Usman #7, Chris Weidman #9** — still inside the sustained-peak top
  10.
- **Georges St-Pierre #15**, **Demetrious Johnson outside the top 30** — not
  topping the ranks.

Diagnosis — three structural causes:

1. **Elite wins outweigh losses ~9:1 inside the window mean.** The period
   score is a weighted mean where each appearance's weight is
   `opp_weight + 0.25` (`PERIOD_BASE_APPEARANCE_WEIGHT`). A title win over a
   champion gets `opp_weight ≈ 2.0` → weight ≈ 2.25; a loss to a non-elite
   opponent gets `opp_weight ≈ 0` → weight ≈ 0.25. So `PERIOD_LOSS_PENALTY`
   enters the mean at roughly one-ninth the leverage of a marquee win. On top
   of that, title/champion/top-5 win bonuses (`+55 / +35 / +25`) are added
   directly to that fight's `mu` before weighting. A cluster of title wins
   drags the window mean up far more than losses drag it down — which is
   exactly why Usman's and Weidman's title runs keep them top-10 despite their
   later losses.
2. **The 10-year window dilutes layoff/comeback careers.** GSP's best 10-year
   window is forced to span either his early Matt Serra loss or his
   2013–2017 layoff, so his sustained peak (#15) sits well below his 5-year
   peak (#9). The window length penalises career *shape*, not greatness.
3. **Shallow divisions are structurally suppressed.** `opp_weight` is driven
   by opponent canonical `mu` and divisional rank. Flyweight opponents carry
   lower canonical `mu` than heavyweight/welterweight opponents, so Demetrious
   Johnson's dominant title reign produces a low window mean and he falls out
   of the top 30 entirely.

Root cause — dead code:

`ratings/replacement_framework.py` (the largest ratings module, ~57 KB) was
built specifically to solve causes 2 and 3: era-depth shrinkage
(`zeta = 1 - exp(-N/50)`), division/era opponent-quality normalisation,
championship-adequacy caps, stake-scaled loss penalties. Its own header and
the "Replacement Framework C" section of this file describe anchor checks
("GSP and Demetrious Johnson top-5 all-time", "Jones over Cormier by 50+").
But `replacement_framework.py` is **imported by nothing** — not
`rate_snapshot.py`, not `refresh.py`, not `analysis/viz.py`, not any test. The
live engine emits period scores from `ratings/peaks.py` only. The docs
describe a model that does not run.

Resolution (2026-05-14) — two passes:

**Pass A (interim).** The corrections were first ported into `ratings/peaks.py`
as hand-picked gentle constants (flat `ERA_NORM_STRENGTH = 0.5`, power-law
opponent weight, flat loss base weight). The user flagged these as both too
volatile and too arbitrary.

**Pass B (current) — literature-grounded re-parameterization.** Every
hand-picked sensitivity constant was replaced with a data-derived,
reliability-weighted quantity. Literature basis: Berry, Reese & Larkey (1999)
on era bridges; Efron-Morris / James-Stein empirical Bayes; Coulom (2008)
Whole-History Rating.

- **Era / division normalization** (`_era_division_normalized_mu`) is now
  empirical-Bayes. Each year's mean shift is James-Stein shrunk by
  `tau2/(tau2+sampling_var)` (`tau2` estimated from the data) and gated by the
  year's *bridge fraction* — the share of that year's fighters who also fought
  another year (BRL: era effects are only identifiable through bridges). Each
  division's mean/std is shrunk the same way. The realized strength
  (`ERA_NORM_MAX_STRENGTH * eb_factor * bridge_factor`) is strictly milder than
  the old flat 0.5 and mildest where data is thin. Addresses causes 1, 3, 6.
- **Opponent-quality weight** is now a logistic (Bradley-Terry-shaped) mapping,
  replacing the ad-hoc power law. Title bouts keep a `1.25` weight multiplier.
  Opponent quality is the first-priority signal; method of victory stays minor.
- **Information-weighted results** (cause 2): a win is weighted by opponent
  quality, a loss by opponent *weakness* on top of a real floor — losing to a
  weak opponent is more damning than losing to a champion.
- **Empirical-Bayes score shrinkage** (`_shrink_period_scores`): the final
  window score is James-Stein shrunk toward the pooled mean by its sampling
  reliability — mild for well-sampled windows.
- **Activity** raw fight-count bonus reduced (cause 4); **5-Yr gate** 9 -> 8
  (cause 4); sustained gate stays at 13 UFC fights per the project owner.

**WHR smoother** (`ratings/whr.py`, new) addresses the root cause directly:
Glicko-2 is a *filter*, so era inflation is structural. WHR is a Bayesian
*smoother* (Coulom 2008) that estimates every fighter's whole history jointly,
making ratings comparable across eras at the rating layer rather than via a
post-hoc patch. It runs as a sidecar `whr` stream.

**Pass C — consensus validation outcome (2026-05-14).** Validation against
MMA consensus showed the windowed Glicko-2 streams still mis-ranked even after
Pass B: Benson Henderson #8, Chris Weidman #11 (on a 12-8 record), Cormier
above Jon Jones. Deep-dive identified two interacting causes — (1) title wins
were *multiple-counted* (champion opponent -> opp_quality 1.0 -> high weight,
PLUS the title weight multiplier, PLUS stacked +55/+35/+25 context bonuses),
and (2) the windowed *mean* still rewards "no easy fights" career shape over
depth (Cormier's 14 all-elite fights beat Jon Jones's 23-fight resume that
includes his climb). The WHR sidecar exhibited neither artifact — its
sustained top 6 was Jones, Nunes, Makhachev, GSP, Silva, DJ. Two fixes
shipped: `_context_adjustment` now deduplicates the title/champion/rank/P4P
win bonuses via `max` (not sum); and **WHR is promoted to the default headline
ranking surface**, with `method_integrity_performance` retained as a
comparison stream. The windowed-mean career-shape bias (cause 2) is now moot
for the headline since WHR — a trajectory smoother, not a windowed mean — is
the headline.

Not addressed:

- Cause 5 (integrity sleeve effectively inert — PED detection catches ~none)
  is a data/detection problem in `loaders/ped_flags.py`, not a `peaks.py`
  concern. Still open.
- Cause 7 (no peak-height column): the 2-year career-peak surface was
  deliberately discarded by the project owner and is not being reinstated.
- `replacement_framework.py` remains dead code; superseded by the above.
