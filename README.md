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
| 2 | Georges St-Pierre | 2353.8 | 770.1 | 583.7 | 1000.0 |
| 3 | Alexander Volkanovski | 1734.5 | 495.2 | 634.7 | 604.5 |
| 4 | Daniel Cormier | 1615.9 | 520.9 | 550.5 | 544.4 |
| 5 | Demetrious Johnson | 1496.1 | 221.1 | 703.8 | 571.2 |
| 6 | Islam Makhachev | 1418.9 | 551.8 | 676.7 | 190.4 |
| 7 | Amanda Nunes | 1399.2 | 118.5 | 501.3 | 779.4 |
| 8 | Jose Aldo | 1377.1 | 347.9 | 563.8 | 465.4 |
| 9 | Anderson Silva | 1309.7 | 300.4 | 424.6 | 584.7 |
| 10 | Stipe Miocic | 1287.3 | 276.0 | 528.5 | 482.7 |
| 11 | Max Holloway | 1148.9 | 143.4 | 262.4 | 743.1 |
| 12 | Valentina Shevchenko | 1136.8 | 36.3 | 300.9 | 799.6 |
| 13 | Patricio Freire | 1134.6 | 268.1 | 642.8 | 223.7 |
| 14 | Matt Hughes | 1099.7 | 188.1 | 427.4 | 484.2 |
| 15 | Randy Couture | 1076.4 | 72.4 | 197.1 | 806.8 |
| 16 | Francis Ngannou | 1016.7 | 294.7 | 268.7 | 453.3 |
| 17 | Aljamain Sterling | 1001.6 | 145.0 | 341.9 | 514.6 |
| 18 | Dominick Cruz | 1000.3 | 229.8 | 458.5 | 312.0 |
| 19 | Khabib Nurmagomedov | 991.0 | 489.4 | 279.6 | 221.9 |
| 20 | Chuck Liddell | 987.8 | 291.2 | 123.3 | 573.3 |
| 21 | Cain Velasquez | 953.3 | 174.7 | 268.2 | 510.5 |
| 22 | Rose Namajunas | 933.6 | 0.0 | 285.2 | 648.5 |
| 23 | Ilia Topuria | 923.2 | 238.7 | 389.8 | 294.8 |
| 24 | Ryan Bader | 893.3 | 250.4 | 168.8 | 474.1 |
| 25 | Justin Gaethje | 890.3 | 216.7 | 229.4 | 444.1 |
| 26 | Merab Dvalishvili | 888.6 | 105.1 | 311.8 | 471.6 |
| 27 | Fedor Emelianenko | 886.3 | 464.6 | 317.5 | 104.2 |
| 28 | Lyoto Machida | 880.0 | 328.2 | 159.1 | 392.7 |
| 29 | Kamaru Usman | 866.1 | 240.8 | 221.9 | 403.3 |
| 30 | Zhang Weili | 863.2 | 0.0 | 232.4 | 630.8 |
| 31 | BJ Penn | 858.1 | 92.8 | 229.5 | 535.7 |
| 32 | Charles Oliveira | 833.7 | 106.8 | 114.6 | 612.3 |
| 33 | Jessica Andrade | 797.5 | 0.0 | 48.8 | 748.7 |
| 34 | Alex Pereira | 795.6 | 64.7 | 282.8 | 448.0 |
| 35 | Israel Adesanya | 788.1 | 62.7 | 292.1 | 433.3 |
| 36 | Dan Henderson | 780.3 | 416.7 | 47.1 | 316.5 |
| 37 | Rashad Evans | 775.9 | 167.4 | 40.5 | 567.9 |
| 38 | Frankie Edgar | 772.1 | 99.7 | 74.6 | 597.8 |
| 39 | Henry Cejudo | 759.6 | 22.1 | 317.2 | 420.2 |
| 40 | Junior Dos Santos | 756.2 | 182.7 | 139.9 | 433.7 |
| 41 | Fabricio Werdum | 743.8 | 131.1 | 125.1 | 487.6 |
| 42 | Benson Henderson | 728.1 | 168.1 | 281.0 | 279.0 |
| 43 | Michael Chandler | 721.4 | 129.2 | 359.0 | 233.1 |
| 44 | Dricus Du Plessis | 679.0 | 215.0 | 167.6 | 296.3 |
| 45 | Petr Yan | 666.3 | 77.8 | 223.9 | 364.5 |
| 46 | Chris Weidman | 654.3 | 71.2 | 168.4 | 414.7 |
| 47 | TJ Dillashaw | 649.7 | 0.0 | 83.7 | 565.9 |
| 48 | Vadim Nemkov | 632.0 | 228.8 | 246.7 | 156.6 |
| 49 | Eddie Alvarez | 624.8 | 145.8 | 226.4 | 252.7 |
| 50 | Tyron Woodley | 620.0 | 47.4 | 135.6 | 437.0 |
| 51 | Josh Barnett | 614.5 | 421.4 | 19.6 | 173.4 |
| 52 | Joanna Jedrzejczyk | 609.1 | 2.3 | 104.7 | 502.1 |
| 53 | Cristiane Justino | 593.2 | 388.7 | 140.9 | 63.6 |
| 54 | Tim Sylvia | 592.6 | 105.5 | 140.3 | 346.8 |
| 55 | Ronda Rousey | 591.7 | 101.7 | 106.3 | 383.7 |
| 56 | Joseph Benavidez | 576.4 | 140.2 | 0.0 | 436.1 |
| 57 | Conor McGregor | 573.5 | 31.9 | 271.5 | 270.2 |
| 58 | Leon Edwards | 573.0 | 20.8 | 212.0 | 340.2 |
| 59 | Gegard Mousasi | 559.7 | 187.6 | 197.6 | 174.5 |
| 60 | Antonio Rodrigo Nogueira | 557.8 | 369.8 | 20.2 | 167.8 |
| 61 | Tito Ortiz | 550.3 | 150.0 | 83.1 | 317.3 |
| 62 | Dustin Poirier | 550.2 | 95.7 | 137.5 | 317.0 |
| 63 | Quinton Jackson | 548.9 | 116.8 | 96.1 | 336.0 |
| 64 | Frank Mir | 548.6 | 5.9 | 135.8 | 406.9 |
| 65 | Vitor Belfort | 538.1 | 132.0 | 24.9 | 381.2 |
| 66 | Kyoji Horiguchi | 533.3 | 278.1 | 147.1 | 108.1 |
| 67 | Andrei Arlovski | 532.2 | 40.3 | 56.1 | 435.7 |
| 68 | Mauricio Rua | 526.1 | 154.2 | 162.1 | 209.8 |
| 69 | Anthony Pettis | 523.3 | 30.6 | 266.9 | 225.8 |
| 70 | Sean Sherk | 522.9 | 243.8 | 39.3 | 239.8 |
| 71 | Julianna Pena | 521.9 | 0.0 | 182.8 | 339.1 |
| 72 | Brandon Moreno | 504.8 | 0.0 | 140.5 | 364.3 |
| 73 | Deiveson Figueiredo | 503.4 | 5.7 | 90.9 | 406.8 |
| 74 | Luke Rockhold | 479.6 | 46.5 | 106.1 | 327.0 |
| 75 | Katlyn Cerminara | 477.5 | 0.0 | 0.0 | 477.5 |
| 76 | Yaroslav Amosov | 475.0 | 304.8 | 150.5 | 19.8 |
| 77 | Donald Cerrone | 474.6 | 71.4 | 0.0 | 403.2 |
| 78 | Rich Franklin | 474.4 | 96.4 | 31.4 | 346.5 |
| 79 | Ciryl Gane | 469.8 | 191.3 | 95.7 | 182.8 |
| 80 | A.J. McKee | 468.6 | 269.1 | 117.1 | 82.4 |
| 81 | Anthony Johnson | 452.5 | 102.4 | 0.0 | 350.2 |
| 82 | Robbie Lawler | 445.8 | 15.6 | 106.8 | 323.4 |
| 83 | Phil Davis | 442.1 | 201.3 | 50.9 | 189.9 |
| 84 | Ketlen Vieira | 431.1 | 0.0 | 0.0 | 431.1 |
| 85 | Johnny Eblen | 430.9 | 217.3 | 120.7 | 92.9 |
| 86 | Rafael Dos Anjos | 428.0 | 0.0 | 77.1 | 350.9 |
| 87 | Joshua Van | 422.7 | 12.9 | 168.1 | 241.7 |
| 88 | Urijah Faber | 415.8 | 119.4 | 7.4 | 289.0 |
| 89 | Sergio Pettis | 415.0 | 0.0 | 212.8 | 202.2 |
| 90 | Ben Askren | 413.6 | 188.5 | 166.3 | 58.9 |
| 91 | Robert Whittaker | 407.5 | 0.0 | 58.6 | 349.0 |
| 92 | Wanderlei Silva | 407.0 | 255.6 | 93.1 | 58.3 |
| 93 | Usman Nurmagomedov | 404.4 | 273.0 | 128.5 | 2.9 |
| 94 | Alexandre Pantoja | 397.9 | 6.7 | 148.8 | 242.4 |
| 95 | Seika Izawa | 396.2 | 138.3 | 0.0 | 257.8 |
| 96 | Yoel Romero | 386.0 | 22.5 | 0.0 | 363.5 |
| 97 | Sean Strickland | 375.4 | 8.6 | 155.1 | 211.7 |
| 98 | Pedro Rizzo | 375.2 | 117.6 | 0.0 | 257.7 |
| 99 | Douglas Lima | 374.0 | 30.9 | 225.3 | 117.8 |
| 100 | Forrest Griffin | 366.8 | 26.4 | 79.2 | 261.1 |

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
