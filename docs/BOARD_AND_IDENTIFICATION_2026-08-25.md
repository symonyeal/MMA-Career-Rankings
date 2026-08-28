# Board selection, title pricing, and the identification wall — 2026-08-25

**Snapshot:** `data/snapshots/2026-08-13` · **Scope:** `majors,pre_unified`

> **Partly superseded on 2026-08-27** by
> [Career coverage](CAREER_COVERAGE_2026-08-27.md), and again on **2026-08-28**
> by [Rating layer and ledger](RATING_LAYER_AND_LEDGER_2026-08-28.md), which
> decomposed the +110 Elo offset (it is **selection**: +274 Elo before a signee's
> UFC debut, +54 after) and reinstated a *measured* organisation correction on
> the title path only. The removal of `ORG_FACTOR_BY_CANONICAL` from that path
> rested on two within-model statistics; a pool offset is exactly what a
> within-model statistic cannot see. Three specifics:
>
> 1. **"The major external pools are *connected* to the tested core, so an
>    organisation discount is not identified and must not be applied" is
>    falsified.** That came from graph connectivity, not from prediction. Held
>    out, the pools are calibrated internally and mis-located relative to each
>    other by **+110 Elo [+76, +151]**. Connected is not the same as correctly
>    located. The operative half of the conclusion survives for a different
>    reason: the offset still must not be *applied* as a weight, because it is
>    fitted on 486 crossing bouts and would assert the answer the joint fit
>    exists to estimate.
> 2. **Every count here predates the career-coverage repair.** The corpus was
>    67,920 model bouts and 28,867 fighters; it is now 80,697 and 33,692. The
>    identification half-widths in "What gates the next scoring change" were
>    measured on the truncated corpus and have not been re-run.
> 3. **A third gate joined the two below**: per-fighter career coverage, which
>    was the actual cause of the top-100 anomalies this document was written to
>    reason about.
>
> Everything else — per-opponent title pricing, the age-through-inactivity
> projection, the rejected `phi`-as-mean-signal and unified-win-ledger
> experiments, and the acceptance rule — still stands.

This is the closing state of 2026-08-25. It supersedes the earlier score
contracts and same-day reverted experiment now preserved in the
[2026-08-26 documentation archive](../_archive/20260826-stale-project-material/README.md).
Three changes shipped; three candidate changes were measured and rejected; two
limits now gate the next scoring change.

## Shipped

### 1. The core board is `public_legacy_score`

The cohesive pass promoted raw `symon_career_skill_mass` to the core board and
that was reverted the same day. Career Skill Mass is a retrospective WHR
functional: it backfills whole-career evidence into earlier years, so a clean
low-loss record in a less-tested circuit accumulates above-bar years and lands
beside title legends as though the public resume question had been answered.
Before the division-bar correction below, top-25 unanchored names went from 7
under Career Skill Mass to **0** under Public Legacy. The current,
division-corrected board has **3**: Francis Ngannou, Aljamain Sterling, and Rose
Namajunas. All three are established UFC champions omitted from the supplied
anchor lists, not the lightly tested external-career profile that motivated the
regression check; `top10_active_external_unanchored` remains empty. The standing
comment is in `build_boards.CORE_RATING_CANDIDATES`, and
`build_top100_audit.py` reports both diagnostics.

### 2. Title resume is priced per opponent

`_title_points` (flat 20/45/60 per appearance/win/defense) and the title-path
`ORG_FACTOR_BY_CANONICAL` are gone. Each title win is priced by the opponent's
**pre-fight** rating against the contender line of that opponent's own division
and year, contributing `q ** 4`. The three components of the published score are
value-normalised by their own maxima, so no exchange rate is hand-set.

A hinge at the contender bar was tried and is **wrong**: `(2q-1)+` zeroes the
title component for 38 fighters with 3+ title wins, because a title challenger
is by construction near contender level, so the modal title fight sits on the
hinge. Any weight must be strictly positive.

#### The division bar was not actually running (fixed 2026-08-25)

`title_quality_ledger` takes `divisions` as an **optional** argument and falls
back to the sport-wide contender line when it is absent — silently, because
nothing raises. `rate_snapshot.run()` scored the public resume about thirty
lines before `career_division` was attached, so `_division_labels` returned
`None` and every title win in every published board was priced against the
sport-wide line. `refresh_career_columns()` reads a persisted snapshot that
already has the division columns, so the two code paths disagreed on the same
snapshot.

The measured cost was exactly what the note above `TITLE_QUALITY_SCALE`
predicted — the light divisions were priced against the heavy ones:

| fighter | sport-wide (published) | own division | under-priced |
|---|---:|---:|---:|
| Zhang Weili | 0.060 | 0.491 | 8.2× |
| Valentina Shevchenko | 0.149 | 0.636 | 4.3× |
| Demetrious Johnson | 0.493 | 1.487 | 3.0× |
| Georges St-Pierre | 0.517 | 1.233 | 2.4× |
| Jon Jones | 1.039 | 2.113 | 2.0× |

It also inverted comparisons between divisions: Matt Hughes scored 828.7 title
points against Volkanovski's 418.2, and repricing each against their own
division reverses it to 427.4 and 634.7. Volkanovski's three Holloway wins go
from ~0.09 each to ~0.24–0.29.

The fix is call ordering — the resume is now scored last, after
`primary_division_rows`. `tests/test_title_division_bar.py` pins both the
mechanism and the ordering; the integration test fails on the old order.

#### “Opponent that night” remains an explicit unresolved design choice

The title ledger uses the opponent's pre-bout row from the retrospective WHR
smoother. `allow_exact_matches=False` prevents the bout from pricing itself, but
future bouts still help locate the opponent's smoothed trajectory. For low-loss
elite careers that trajectory can be nearly flat: Hughes's 2004 win over GSP is
therefore priced close to career-GSP, and supplies 47.9% of Hughes's repaired
title component.

The no-future Glicko filter was measured as the direct alternative, with each
ledger priced against a contender bar built from its own rating source. It is
not a safe mechanical replacement:

- Hughes rises from 427.4 to 444.7 title display points rather than falling,
  because the causal filter already rates undefeated 2004 GSP very highly;
- his largest-win share does fall from 47.9% to 24.2%;
- across 245 commonly priced fighters, the two ledgers have Spearman 0.9149 and
  median absolute movement of 20.7 display points;
- the changes are large and mixed: GSP +295, Volkanovski +220, Aldo +238,
  Amanda Nunes -242, and Demetrious Johnson -138.

The division bug is fixed. The valuation semantics are not silently changed:
switching to the causal filter would alter the whole board without solving the
Hughes objection it was proposed to solve. Evidence is retained in
`Claude Func Folder/py/ufc/out/title_opponent_valuation.csv` outside the repo.

### 3. Age decline is projected through inactivity

`age_drift=True` applied the learned eight-bin age curve only *between* fitted
appearance nodes, so forecasts and the snapshot's current rating read the last
fitted mean, and a fighter could hold the same age-adjusted score through a long
layoff. `ratings.whr.project_age_rating` now integrates the same curve from the
last appearance to the forecast/snapshot date, including age-bin crossings.
`rate_snapshot` publishes `mu_whr_age_activity_adjusted`,
`whr_age_inactivity_adjustment`, and `whr_last_event_date`; **Current skill**
resolves to the adjusted column. **All-time is not decayed.**

Paired held-out result on the same 17-event, 195-bout set used to approve age
drift — projected minus unprojected log loss, event-bootstrap 95% CI:

| subset | bouts | change in log loss | 95% CI |
|---|---:|---:|---|
| all | 195 | **-0.00101** | **[-0.00190, -0.00025]** |
| a fighter over 35 | 69 | **-0.00274** | **[-0.00532, -0.00051]** |
| at least 1 year inactive | 34 | -0.00391 | [-0.00879, +0.00009] |
| at least 2 years inactive | 10 | **-0.01718** | **[-0.03737, -0.00506]** |

The one-year subset is directionally favourable but **unresolved** at this
sample size, and the two-year subset is too small to read as an effect size.
5,603 of 28,867 rated fighters have enough birth-date and inactivity
information to receive a nonzero adjustment; the observed range is 0 to
-115.74 Elo. An unknown birth date stays neutral. The prequential cache schema
moved 5 to 6.

## Measured and rejected

**Glicko/WHR `phi` as a mean signal.** Final `phi` is larger for thin records in
aggregate (median 266.6 with no UFC bouts, 167.9 with 1-7, 119.5 with 8+), but
the external top-100 careers that motivated the question sit at 115-136 and
overlap established UFC fighters. On 4,978 held-out bouts from 2021 onward,
fitted `phi` versus both `phi` set to zero moved log loss by -0.00005, 95%
[-0.00064, +0.00050]. Do not turn `phi` into a mean penalty.

**Organisation or connectivity shrinkage of `mu_whr`.** A time-aware appearance
graph — bout edges at maximum Bradley-Terry Fisher information, temporal edges
from `WHR_W2_PER_DAY`, appearances of fighters with 8+ UFC bouts grounded —
found 135,840 appearance nodes, 11,094 grounded, 124,504 connected unknown, and
only 242 disconnected. The major external pools are *connected* to the tested
core, so an organisation discount is **not identified** and must not be applied.

**One unified ledger over all wins.** Removing the title/non-title partition and
pricing all 47,525 wins once against the opponent's pre-fight rating repairs the
partition defect — a dominant champion fights his best opponents for the belt,
so splitting the ledger rewards perennial contenders — but it does not repair
the board. All five aggregations (sum, top-5, top-10, mean, mean times sqrt(n))
trail the shipped board on all four external reference lists, and among fighters
with 5+ priced wins the correlation between ledger value and raw win count stays
at +0.36 to +0.59. Shevchenko falls to 54-86, Weili to 177-223, Pantoja to
180-203.

The external lists are **descriptive diagnostics, not acceptance criteria**:
they were co-authored with the layer that scores them, and they agree with one
another only modestly.

## What gates the next scoring change

**1. Individual identification is not reported.** A connected pool mean and a
precisely pinned individual career are different questions. Optimistic
lower-bound 95% half-widths on career mass, relative to the published mass:
Freire 136%, Nemkov 135%, Izawa 131%, Amosov 123%, Eblen 116%, McKee 108%,
Usman Nurmagomedov 99% — against Jones 1%, St-Pierre 7%, Demetrious Johnson 82%.
Anchor and virtual-game priors were deliberately omitted from that computation
because they assume the pool level under test, so the true intervals are wider
than these. An identification/reliability field must ship before an
opponent-priced ledger is presented as precise all-time evidence.

**2. The career bar is gauge-dependent across rating components.** Men's and
women's bouts form separate large components (26,953 and 1,748 fighters). Adding
a constant to every rating in the women's component changes no modelled bout
probability, but moves total female career mass from 0 at -200 Elo to 45,382 at
+200; Weili moves from rank 30 with zero mass to rank 13 with 886. A sport-wide
bar is therefore not invariant to an unidentified gauge. Component and
component-plus-division bars are invariant to every shift tested.

A **full division** bar is not the answer either: adjacent divisions are bridged
by many fighters (FW-LW 231, LW-WW 208, MW-WW 182, BW-FW 182, LHW-MW 162), so
their relative level is structurally identified and already present in `mu_whr`,
and scoping career mass by division risks subtracting earned depth twice. The
defensible scope is the **large connected rating component**, with tiny
components left unranked rather than given cheap local bars.

This is a research conclusion, not a shipped change. Two things must be built
first: graph-component identity as a production column, and repaired gender
metadata — the current field implies 663 cross-gender model bouts because many
external women default to male.

## Acceptance rule

Changes to `mu_whr`, its uncertainty, or the forecast must pass a paired
prequential gate with event-level bootstrap intervals, and must report
unresolved intervals as unresolved.

A board-only ledger never enters the bout probability, so it **cannot** improve
held-out log loss by construction. Log loss can approve or reject a
rating-layer change; it cannot validate a retrospective achievement definition.
That asymmetry is why the two limits above are the gate instead.

## Reproduce

```bash
python -m ratings.rate_snapshot --snapshot-dir "data/snapshots/2026-08-13" --scope majors,pre_unified
python build_boards.py "data/snapshots/2026-08-13" --scope majors,pre_unified --write-readme
python build_top100_audit.py "data/snapshots/2026-08-13"   # inspect anchor and external-career diagnostics
```

The one-off probes behind the rejected candidates (`probe_q1_*`, `probe_q2_*`,
`probe_q3_*`, `probe_age_inactivity_projection.py`) and their CSV/JSON outputs
are kept outside this repository, beside the working material for this project.
The narrative report is `Claude Status Reports/UFC Opponent Quality Wall
Investigation 2026-08-25.md`.
