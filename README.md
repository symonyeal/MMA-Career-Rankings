# Symon UFC Rank Engine

A local, auditable UFC ranking lab built around a deliberately small
mathematical core. The engine separates three questions that older versions
mixed together:

1. What is a fighter's latent skill?
2. How much high-level skill did the fighter sustain across a career?
3. Which data-quality or integrity policies should change what is displayed?

The design record, newest first. Each entry states what it settled, so nothing
below is a summary of something else:

| Document | What it settled |
|---|---|
| [Board and identification](docs/BOARD_AND_IDENTIFICATION_2026-08-25.md) | The current score contract: per-opponent title pricing, age decline projected through inactivity, and the two limits that gate the next scoring change |
| [Cohesive engine pass](docs/COHESIVE_ENGINE_PASS_2026-08-25.md) | One deduped model-input table, `combined_fights.parquet` |
| [Final outcome](docs/OUTCOME_2026-08-24.md) | Scope, career bar, age prior, and the top-100 evaluation |
| [Whole-sport engine](docs/PLAN_WHOLE_SPORT_ENGINE_2026-08-21.md) | Whole-sport scope, era depth, and the Single-Entry principle that separates this engine from points-stacking systems |
| [Prior mass and uncertainty](docs/PRIOR_MASS_AND_UNCERTAINTY_2026-08-20.md) | The prior-mass defect, retired period scores, bootstrap rank intervals |
| [Principled core evolution](docs/PRINCIPLED_CORE_EVOLUTION_2026-08-20.md) | The original core design and audit |

## All-time top 100

Snapshot `2026-08-13`, scope `majors,pre_unified`, 67,920 rated bouts. The
published score is **Public Legacy Score**, and it is the sum of three
components, each divided by its own observed maximum and scaled to 1000 — so the
three columns below add back to the total, and no exchange rate between them was
hand-set:

- **Skill** — Career Skill Mass, the years-above-the-field functional defined
  under [The Core](#the-core), multiplied by an organisation-exposure factor.
- **Title** — every title win priced by the opponent actually beaten: their
  pre-fight rating against the contender line of their own division and year.
- **Schedule** — wins over ranked opposition, on the same exposure factor.

Three things this table does **not** claim:

1. **The numbering is score order, not a separation claim.** The board's only
   ordering claim is its tier boundaries; see [Rank uncertainty](#rank-uncertainty).
2. **Careers far from the tested UFC core are pinned far less precisely.** The
   interval on a mostly-external career can exceed its own published score,
   against roughly 1% for Jon Jones. The measurement and its consequences are in
   [Board and identification](docs/BOARD_AND_IDENTIFICATION_2026-08-25.md).
3. **A fighter absent from this table is not ranked 101st.** Insufficient
   history and a zero score are both abstentions, reported as such.
4. **A `Skill` of 0.0 is an abstention too, not a measurement of no skill.**
   Career Skill Mass counts only years spent above the annual contender line, so
   zero means no year cleared that bar. Twelve of these hundred sit there. For
   the women's classes it is also a **known defect**: men's and women's bouts
   form separate rating components, and a sport-wide bar is not invariant to the
   unidentified offset between them — which is why the bar is going to become
   component-scoped. Weili, Namajunas, Andrade, Peña and Vieira rank here on
   resume alone as a result.

<!-- BOARD:TOP100:BEGIN -->

| # | Fighter | Score | Skill | Title | Schedule |
| ---: | --- | ---: | ---: | ---: | ---: |
| 1 | Jon Jones | 2849.1 | 1000.0 | 1000.0 | 849.1 |
| 2 | Georges St-Pierre | 2267.1 | 770.1 | 496.9 | 1000.0 |
| 3 | Daniel Cormier | 1616.7 | 520.9 | 551.3 | 544.4 |
| 4 | Alexander Volkanovski | 1518.0 | 495.2 | 418.2 | 604.5 |
| 5 | Matt Hughes | 1501.0 | 188.1 | 828.7 | 484.2 |
| 6 | Randy Couture | 1430.5 | 72.4 | 551.2 | 806.8 |
| 7 | Stipe Miocic | 1370.9 | 276.0 | 612.2 | 482.7 |
| 8 | Islam Makhachev | 1346.7 | 551.8 | 604.5 | 190.4 |
| 9 | Anderson Silva | 1320.8 | 300.4 | 435.8 | 584.7 |
| 10 | Demetrious Johnson | 1266.4 | 221.1 | 474.1 | 571.2 |
| 11 | Amanda Nunes | 1259.2 | 118.5 | 361.3 | 779.4 |
| 12 | Jose Aldo | 1242.4 | 347.9 | 429.0 | 465.4 |
| 13 | Fedor Emelianenko | 1204.8 | 464.6 | 636.0 | 104.2 |
| 14 | Chuck Liddell | 1049.4 | 291.2 | 184.9 | 573.3 |
| 15 | Max Holloway | 1038.9 | 143.4 | 152.3 | 743.1 |
| 16 | Francis Ngannou | 1034.3 | 294.7 | 286.3 | 453.3 |
| 17 | Valentina Shevchenko | 978.8 | 36.3 | 142.9 | 799.6 |
| 18 | Tito Ortiz | 961.6 | 150.0 | 494.3 | 317.3 |
| 19 | Cain Velasquez | 943.8 | 174.7 | 258.6 | 510.5 |
| 20 | Justin Gaethje | 935.7 | 216.7 | 274.9 | 444.1 |
| 21 | Khabib Nurmagomedov | 925.9 | 489.4 | 214.5 | 221.9 |
| 22 | Patricio Freire | 923.4 | 268.1 | 431.6 | 223.7 |
| 23 | BJ Penn | 919.9 | 92.8 | 291.4 | 535.7 |
| 24 | Dominick Cruz | 908.1 | 229.8 | 366.3 | 312.0 |
| 25 | Ilia Topuria | 900.0 | 238.7 | 366.6 | 294.8 |
| 26 | Lyoto Machida | 894.4 | 328.2 | 173.6 | 392.7 |
| 27 | Aljamain Sterling | 875.5 | 145.0 | 215.9 | 514.6 |
| 28 | Ryan Bader | 837.8 | 250.4 | 113.3 | 474.1 |
| 29 | Merab Dvalishvili | 833.1 | 105.1 | 256.3 | 471.6 |
| 30 | Dan Henderson | 791.8 | 416.7 | 58.6 | 316.5 |
| 31 | Charles Oliveira | 790.5 | 106.8 | 71.4 | 612.3 |
| 32 | Alex Pereira | 783.8 | 64.7 | 271.0 | 448.0 |
| 33 | Rashad Evans | 781.1 | 167.4 | 45.7 | 567.9 |
| 34 | Junior Dos Santos | 772.7 | 182.7 | 156.3 | 433.7 |
| 35 | Jessica Andrade | 762.8 | 0.0 | 14.1 | 748.7 |
| 36 | Frankie Edgar | 745.5 | 99.7 | 47.9 | 597.8 |
| 37 | Rose Namajunas | 737.4 | 0.0 | 88.9 | 648.5 |
| 38 | Israel Adesanya | 734.8 | 62.7 | 238.7 | 433.3 |
| 39 | Kamaru Usman | 732.2 | 240.8 | 88.0 | 403.3 |
| 40 | Fabricio Werdum | 728.2 | 131.1 | 109.5 | 487.6 |
| 41 | Zhang Weili | 688.6 | 0.0 | 57.8 | 630.8 |
| 42 | Benson Henderson | 685.5 | 168.1 | 238.4 | 279.0 |
| 43 | Tim Sylvia | 684.1 | 105.5 | 231.8 | 346.8 |
| 44 | Henry Cejudo | 676.2 | 22.1 | 233.8 | 420.2 |
| 45 | Vadim Nemkov | 663.0 | 228.8 | 277.7 | 156.6 |
| 46 | Josh Barnett | 661.7 | 421.4 | 66.8 | 173.4 |
| 47 | Michael Chandler | 660.3 | 129.2 | 297.9 | 233.1 |
| 48 | Dricus Du Plessis | 650.6 | 215.0 | 139.2 | 296.3 |
| 49 | Frank Mir | 638.6 | 5.9 | 225.9 | 406.9 |
| 50 | Petr Yan | 632.5 | 77.8 | 190.1 | 364.5 |
| 51 | Chris Weidman | 624.6 | 71.2 | 138.8 | 414.7 |
| 52 | Wanderlei Silva | 620.1 | 255.6 | 306.2 | 58.3 |
| 53 | Ronda Rousey | 612.8 | 101.7 | 127.4 | 383.7 |
| 54 | TJ Dillashaw | 612.1 | 0.0 | 46.1 | 565.9 |
| 55 | Eddie Alvarez | 593.8 | 145.8 | 195.3 | 252.7 |
| 56 | Andrei Arlovski | 585.4 | 40.3 | 109.4 | 435.7 |
| 57 | Joseph Benavidez | 576.4 | 140.2 | 0.0 | 436.1 |
| 58 | Quinton Jackson | 573.7 | 116.8 | 120.9 | 336.0 |
| 59 | Mauricio Rua | 567.3 | 154.2 | 203.3 | 209.8 |
| 60 | Antonio Rodrigo Nogueira | 561.7 | 369.8 | 24.1 | 167.8 |
| 61 | Vitor Belfort | 558.1 | 132.0 | 44.9 | 381.2 |
| 62 | Tyron Woodley | 544.0 | 47.4 | 59.6 | 437.0 |
| 63 | Anthony Pettis | 539.5 | 30.6 | 283.1 | 225.8 |
| 64 | Joanna Jedrzejczyk | 531.1 | 2.3 | 26.7 | 502.1 |
| 65 | Sean Sherk | 525.2 | 243.8 | 41.7 | 239.8 |
| 66 | Cristiane Justino | 519.4 | 388.7 | 67.1 | 63.6 |
| 67 | Dustin Poirier | 513.0 | 95.7 | 100.3 | 317.0 |
| 68 | Leon Edwards | 500.4 | 20.8 | 139.4 | 340.2 |
| 69 | Mark Coleman | 495.0 | 38.9 | 444.6 | 11.5 |
| 70 | Conor McGregor | 492.2 | 31.9 | 190.1 | 270.2 |
| 71 | Rich Franklin | 484.4 | 96.4 | 41.4 | 346.5 |
| 72 | Gegard Mousasi | 481.9 | 187.6 | 119.8 | 174.5 |
| 73 | Ciryl Gane | 480.5 | 191.3 | 106.5 | 182.8 |
| 74 | Kyoji Horiguchi | 477.6 | 278.1 | 91.4 | 108.1 |
| 75 | Katlyn Cerminara | 477.5 | 0.0 | 0.0 | 477.5 |
| 76 | Donald Cerrone | 474.6 | 71.4 | 0.0 | 403.2 |
| 77 | Matt Serra | 458.9 | 0.0 | 370.5 | 88.4 |
| 78 | Anthony Johnson | 452.5 | 102.4 | 0.0 | 350.2 |
| 79 | Deiveson Figueiredo | 451.1 | 5.7 | 38.6 | 406.8 |
| 80 | Julianna Pena | 447.9 | 0.0 | 108.9 | 339.1 |
| 81 | Luke Rockhold | 447.4 | 46.5 | 73.9 | 327.0 |
| 82 | Ketlen Vieira | 431.1 | 0.0 | 0.0 | 431.1 |
| 83 | Brandon Moreno | 429.7 | 0.0 | 65.4 | 364.3 |
| 84 | Phil Davis | 426.9 | 201.3 | 35.7 | 189.9 |
| 85 | A.J. McKee | 420.9 | 269.1 | 69.4 | 82.4 |
| 86 | Yaroslav Amosov | 419.9 | 304.8 | 95.3 | 19.8 |
| 87 | Johnny Eblen | 418.1 | 217.3 | 107.9 | 92.9 |
| 88 | Urijah Faber | 416.3 | 119.4 | 7.9 | 289.0 |
| 89 | Rafael Dos Anjos | 405.3 | 0.0 | 54.5 | 350.9 |
| 90 | Robbie Lawler | 398.8 | 15.6 | 59.8 | 323.4 |
| 91 | Seika Izawa | 396.2 | 138.3 | 0.0 | 257.8 |
| 92 | Forrest Griffin | 395.1 | 26.4 | 107.6 | 261.1 |
| 93 | Usman Nurmagomedov | 392.3 | 273.0 | 116.4 | 2.9 |
| 94 | Sean Strickland | 388.9 | 8.6 | 168.7 | 211.7 |
| 95 | Yoel Romero | 386.0 | 22.5 | 0.0 | 363.5 |
| 96 | Robert Whittaker | 385.8 | 0.0 | 36.8 | 349.0 |
| 97 | Frank Shamrock | 382.2 | 19.4 | 362.8 | 0.0 |
| 98 | Pedro Rizzo | 375.2 | 117.6 | 0.0 | 257.7 |
| 99 | Sergio Pettis | 365.5 | 0.0 | 163.3 | 202.2 |
| 100 | Ben Askren | 364.2 | 188.5 | 116.8 | 58.9 |

<!-- BOARD:TOP100:END -->

Regenerate this table from a rebuilt snapshot with `build_boards.py
--write-readme`; see [Rebuild](#rebuild).

## The Core

Every decided bout contributes one binary Bradley--Terry likelihood. The
winner and loser share the same bout weight:

\[
\ell_b=\omega_b\{y_b\log\sigma(\theta_i-\theta_j)
+(1-y_b)\log\sigma(\theta_j-\theta_i)\}.
\]

The published scope is `majors,pre_unified`: UFCStats plus the six-promotion
Sherdog corpus and UFC 1-27. The selected scope is materialized as
`combined_fights.parquet`, preserving source-specific columns while enforcing
one bout fingerprint and one dedupe policy. Every admitted production bout has
\(\omega_b=1\). Two estimators read the same evidence:

- **Skill filter**: causal Glicko-2 for one-step-ahead validation and current
  skill.
- **Skill smoother**: Whole-History Rating (WHR) for retrospective career
  analysis.

### Prior mass is fixed per fighter

An undefeated record has no interior maximum-likelihood rating: the
Bradley--Terry gradient stays positive at every finite rating, so only the prior
stops the climb. If the prior is applied once per appearance, its mass grows
with career length at the same rate as the likelihood and the stopping point
becomes a constant that ignores the evidence. Measured on this database before
the fix, the highest rating of all 2,554 fighters belonged to a man with one UFC
bout, and 56 fighters at 1-0 averaged above the 98th percentile of the roster;
going from 1-0 to 10-0 bought 67 rating points.

Both priors carry a fixed mass per fighter, spread across that fighter's
appearances: a Gaussian anchor (`WHR_PRIOR_VAR`) and `WHR_VIRTUAL_GAMES = 2`
bouts of prior evidence against an average opponent, half won and half lost, as
in Coulom's paper. That value was measured over 60 held-out events and is
**unresolved** — every paired interval crosses zero — so it ships on a stated
tie-break (the smallest prior mass that wins the point estimate), with no
accuracy claim attached. An undefeated fighter with \(k\) wins over average
opposition then settles at \(\sigma(r)=(k+v/2)/(k+v)\), which rises with the
evidence as it must.

The temporal prior is age-aware when a birth date is known. A neutral fit
estimates a population trajectory in eight age buckets and the model is then
refit under that curve; an unknown birth date retains zero drift. On the held-out
age panel this improves log loss by **0.00382** overall and **0.00965** for bouts
involving a fighter over 35.

The same learned curve is projected forward through inactivity, so a rating does
not sit frozen at its last fitted appearance through a long layoff. That
projection improves held-out log loss by a further **0.00101**
([−0.00190, −0.00025]), and it moves the current-skill view only — the all-time
board is never decayed.

The career functional underneath the public board is **Symon Career Skill
Mass**:

\[
C_i=\sum_{y\in A_i}
\left[\overline{\theta}_{iy}-\overline{\theta}_{\text{field},y}\right]_+.
\]

It contributes at most once per active calendar year. Peak height, losses,
opponent strength, activity, and longevity therefore enter through the latent
rating history without adding opponent rank, title, streak, or activity points
a second time.

Career Skill Mass is a **skill diagnostic, not the published board**. Selecting
it directly is what put three lightly-tested external careers in the all-time
top ten: it backfills whole-career evidence into earlier years, so a clean
low-loss record in a less-tested circuit accumulates above-bar years as though
the resume question had been answered. The published board wraps it in the
exposure factor and the two resume components above.

The published yearly bar is `contender:60`: the top decile while a field has
fewer than 600 fighter-years, capped at the 60th-best level thereafter. This
keeps an elite fraction in genuinely small fields without letting a larger
source corpus silently multiply the number of contenders. `count:60`, `mean`,
numeric quantiles and `hybrid:<lambda>` remain explicit research alternatives.

### Rank uncertainty

`build_uncertainty.py` refits the entire smoother under Dirichlet-reweighted
events (the Bayesian bootstrap) and recomputes the career functional on each
replicate, writing `career_mass_uncertainty.parquet`. Ranks are published with
those intervals after applying the same 13-period completeness gate as the
published board: where two intervals overlap, the board is not claiming an
ordering.

The original 150-replicate UFC-only run showed that rank uncertainty matters,
but it does not describe the published whole-sport, age-aware board. The current
snapshot records its scope, bar, model and replicate count beside the interval
artifact. Printing 1 through 25 without that qualification would claim
precision the evidence does not contain. Resampling events with replacement is
deliberately *not* used — career mass is a sum over years, so dropping ~37% of
events biases every replicate low.

The correctly gated 12-replicate exploratory run has a median top-50 rank width
of **91** and four tiers; tier 1 runs from Jon Jones through Khabib Nurmagomedov.
Those endpoints are diagnostic, not release-grade—a 150+ replicate run remains
the release standard.

So the board publishes **tiers**, and the rule is stated rather than implied.
Walk the board in descending mass: the first fighter opens tier 1 and is its
*leader*; each next fighter joins the current tier unless the leader outscores
them in at least 95% of replicates, in which case they open the next tier and
become its leader. A tier therefore means exactly one thing — **nobody in it is
separated from the fighter at the top of it** — and a tier boundary is the only
ordering claim the board makes.

Separation is measured **paired**, from the replicate draws, not by comparing
two marginal intervals. Both careers are reweighted by the same events, so most
of what moves them moves them together; two heavily overlapping marginal
intervals are perfectly consistent with a difference of the same sign in every
replicate. Anchoring each tier on its leader rather than on neighbours is also
deliberate: "indistinguishable" is not transitive, so chaining pairwise overlaps
collapses the whole board into one block.

WHR's optional `return_variance` is not this quantity and is not a rank
interval: it inverts one fighter's Hessian block with every opponent held
fixed.

## Public Ranking Views

| View | Column | Definition |
|---|---|---|
| All-time | `public_legacy_score` | Exposure-adjusted Career Skill Mass, per-opponent title quality, and ranked-opponent wins, each value-normalised |
| Prime | `symon_prime_score` | Best fixed 10-year WHR mean, at least 13 appearances, EB-shrunk |
| Current skill | `mu_whr_age_activity_adjusted` | Latest WHR state with the learned age curve projected to the snapshot date |

Prime is a separate view and does not feed back into All-time. Career Skill Mass
(`symon_career_skill_mass`) is published as a diagnostic column beside them, and
is never the board.

## What Is Not in the Core

- **Titles, rankings, P4P labels, streaks, and odds** are descriptive or
  benchmarking data, not repeated rating bonuses.
- **Integrity** is a visible ledger and optional direct-debit board. It does
  not propagate a penalty through an opponent graph.
- **Completeness** is a separate gate. Insufficient history is shown as such,
  not disguised as low skill.
- **Era strength** is neutral by default. A common era offset is not
  identifiable from within-era bout outcomes; any modern-depth premium must be
  labelled as an external scenario.
- **FightMatrix ranked-cohort history and organisation weights** are
  diagnostics. The published whole-sport scope uses the named major-promotion
  corpus, but production still gives every admitted bout unit evidence weight.
  Candidate org weights are evaluated by `build_org_strength_audit.py`, not
  hard-coded into the model.

Former `method_*_performance`, `method_*_integrity`, and
`whr_integrity_performance` production streams are retired. The WHR solver also
rejects side-specific winner/loser likelihood weights because they do not form
one joint posterior.

The rolling opponent-quality period scores (`sustained_peak_*`,
`five_year_peak_*`) and the public `symon_peak_score` output are retired. The
old rolling scores re-counted opponent quality, title status, activity volume
and era position on top of a rating that already reflects all four, and needed
about twenty hand-set constants to do it. Opponent context survives only where
it answers a different question: `ratings/appearance_context.py` feeds the
division resume boards.

## Notebook

Open the generated dashboard:

```bash
jupyter lab analysis/notebook.ipynb
```

Or regenerate it from source:

```bash
python analysis/build_notebook.py
```

The public narrative is intentionally short:

1. snapshot and scope contract;
2. one ranking control and leaderboard;
3. held-out scorecard and paired ablation forest;
4. how firm the ranking is — bootstrap rank intervals, the bar-sensitivity
   ladder, and rating against the evidence under it;
5. where the score came from — one fighter's yearly contribution receipt, and
   the whole board decomposed into years above the field versus distance above
   it;
6. fighter and division exploration;
7. results versus the closing market;
8. integrity, source-scope, and FightMatrix appendices.

FightMatrix is a sanity check, never a tuning target. The odds are an external
prediction benchmark, never a rating input.

### Investigations

One-off analyses live beside the dashboard and are built the same way:

```bash
python -m analysis.investigations.build_cache          # pre-warm the refits
python -m analysis.investigations.build_top100_notebook
jupyter lab analysis/investigations/top100_era_skew.ipynb
```

`top100_era_skew.ipynb` asks why the all-time board is dominated by active
fighters and why several champions score zero career mass. It tests six
hypotheses, each with a stated falsification rule and a verdict, and closes with
a ranked defect list. Its expensive refits cache to
`data/model_tuning/top100-era-skew/`; the committed notebook carries no outputs.

## Current Data Scope

The standard local snapshot is `data/snapshots/2026-08-13`:

- 68,415 combined fight rows, 67,920 model bouts;
- 28,867 fighters in the whole-sport scope;
- 0 duplicate bout fingerprints after scope guard;
- UFCStats/Greco fight and round data;
- optional UFC-DataLab, mdabbert odds, and FightMatrix comparison artifacts.

Large raw snapshots, caches, and generated SQLite files are intentionally
ignored by Git. Field-level provenance and known source gaps live in
[data/SOURCE_MATRIX.md](data/SOURCE_MATRIX.md).

## Rebuild

Run these commands from the project root.

Refresh the canonical snapshot, ratings, policy boards, changelog, and
notebook:

```bash
python refresh.py --snapshot-date 2026-08-13 \
  --greco-dir "data/raw/2026-08-13" \
  --include-external --include-odds \
  --mdabbert-csv "../../archive/ufc-master.csv"
```

Rebuild only ratings and the three standard board artifacts:

```bash
python -m ratings.rate_snapshot --snapshot-dir "data/snapshots/2026-08-13" --scope majors,pre_unified
python build_boards.py "data/snapshots/2026-08-13" --scope majors,pre_unified --write-readme
```

`--write-readme` rewrites the block between the `BOARD:TOP100` markers in this
README from the board it just built, so the published table cannot drift away
from the artifacts. It is opt-in; without it the boards are written and the
README is left alone. Snapshots are not committed, so that table is the only
published form of the board.

Audit candidate organisation weights against the top-100 sanity panel:

```bash
python build_org_strength_audit.py "data/snapshots/2026-08-13" --out-dir data/model_tuning/org-strength/2026-08-13
```

Publish rank intervals for the career board. The 67,920-bout age-aware scope
took about 100 seconds per fit on the measured machine; 12 replicates are an
exploratory check, while a 150-replicate release run needs a multi-hour budget:

```bash
python build_uncertainty.py "data/snapshots/2026-08-13" --replicates 12
```

`refresh.py --bootstrap-replicates 12` does the same inside a full refresh.

Regenerate held-out evaluation after any estimator or probability change:

```bash
python build_prequential_evaluation.py "data/snapshots/2026-08-13" \
  --events 40 --calibration-events 40 --mode recent --force \
  --artifact-dir "data/snapshots/2026-08-13"
```

Build the queryable SQLite export:

```bash
python build_database.py --snapshot-dir "data/snapshots/2026-08-13"
```

Run the test suite:

```bash
python -m pytest -q
```

## Scopes — which bouts a rating is allowed to see

Scopes are **named**, and nothing is merged unless the merge is asked for by
name. There is no single "cross-org" switch, because there is no single
cross-org corpus.

| scope | corpus | how it was built |
|---|---|---|
| `ufc` | UFCStats, UFC 28 onward | baseline research scope |
| `majors` | the Sherdog whole-career corpus | seeded by an event crawl of PRIDE, WEC, Strikeforce, Affliction, Bellator and RIZIN, then extended to one page per fighter so the six-promotion boundary stops censoring records. 63,813 bouts, 28,491 fighters, 1980-2026 |
| `pre_unified` | UFC 1-27 | recovered from the snapshot's own `_excluded_bouts.csv` |
| `fightmatrix` | a bounded ranked-cohort crawl | seeded from **today's** FightMatrix rankings |
| `all` | every staged corpus | |

The published default is `majors,pre_unified`.

Combine explicitly: `--scope majors,pre_unified`.

The naming is not bureaucracy. The two non-UFC corpora move the board in
**opposite directions**, because of how each was built — `majors` reaches back
to 1997 and back-fills the early era, while `fightmatrix` is seeded from
currently ranked fighters and back-fills the modern regional circuit:

Earlier 0.9-bar scope sensitivity (not the current published board):

| scope | bouts | top-100 active in 2024 | median debut |
|---|---:|---:|---:|
| `ufc` | 8,479 | 70 | 2015 |
| `majors` | 67,820 | 57 | 2009 |
| `majors,pre_unified` | 67,920 | 57 | 2009 |
| `fightmatrix` | 18,312 | 85 | 2012 |

```bash
# Stage every corpus the inputs support, then rate one scope.
python refresh.py --snapshot-date 2026-08-13 --scope majors,pre_unified
```

Two rules hold across every scope.

**No organisation weight.** Relative promotion strength is an *output* of the
joint fit, read off the fighters who crossed between promotions. A weight would
assert the answer the fit exists to estimate — and the weights that existed
were derived from fighters' *eventual UFC careers*, so a 2003 PRIDE bout was
priced by what its participants went on to do years later. Production discards
any staged `org_weight`; `--experimental-org-weight` opts back in and says so.

**Ask for a scope and get it, or get an error.** A scope whose artifact is
missing raises, and the error names the builder that makes it. Silently
returning UFC-only and calling it a joint fit is how "cross-org makes no
difference" became a believed result.

### The Unified-Rules boundary

UFC 1-27 (253 source rows; 252 rated after dedupe, 1993-11-12 to 2000-09-22)
were scraped, parsed, and then
dropped. That is defensible on its own terms, and it means the engine
structurally could not rank the 1993-2000 generation — it is most of why Randy
Couture scored zero.

They are now admitted to the rating through the `pre_unified` scope, carrying an
explicit `rules_era` label so the difference between the two rule sets is
*estimated* rather than assumed. `build_rules_era_sweep.py` is the estimator,
and its answer is that the term is **not identified by prediction**: only 36
held-out bouts involve a fighter who crossed the boundary, and every interval
crosses zero. `RULES_ERA_WEIGHT` therefore stays at 1.0 — full admission — by
that finding, not by preference.

The label is deliberately narrow. PRIDE never fought under unified rules either,
but its rules differed *per promotion*, and a date-keyed rules indicator applied
across promotions would quietly become an organisation weight wearing a
different name.

## Project Layout

```text
analysis/                    Notebook builder and Plotly charts
analysis/investigations/     One-off investigations: notebook + its module
ratings/                     Glicko-2, WHR, Career Skill Mass, policy boards
loaders/                     UFCStats and optional-source ingestion
build_boards.py              Integrity ledger/debit, completeness views, published table
build_top100_audit.py        Board-regression check: read top25_unanchored_count
build_prequential_evaluation.py  Rolling-origin validation artifacts
build_database.py            SQLite export
data/SOURCE_MATRIX.md        Field-level provenance and coverage contract
docs/                        Current audit and design notes
docs/archive/                Superseded historical reports
_archive/                    Closed-question research drivers, with the answers they produced
tests/                       Model, pipeline, database, and chart tests
```

## Mathematical References

- Mark Glickman, [Example of the Glicko-2 system](https://www.glicko.net/glicko/glicko2.pdf)
- Mark Glickman, [Parameter estimation in large dynamic paired-comparison experiments](https://www.glicko.net/research/acjpaper.pdf)
- Rémi Coulom, [Whole-History Rating](https://www.remi-coulom.fr/WHR/)

Symon's novelty is the disciplined composition: one paired likelihood, two
estimators, one transparent career functional, and policy layers that never
silently mutate the skill model. It does not claim to have invented Glicko-2,
Bradley--Terry, WHR, or empirical Bayes.
