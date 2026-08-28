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
| [Rating layer and ledger](docs/RATING_LAYER_AND_LEDGER_2026-08-28.md) | The current estimator contract: a scale-equivariant career functional, the refit WHR constants, method of victory in the winner score, why every bout-precision weight failed, the UFC pool offset decomposed into selection, and why the boards are split by gender |
| [Career coverage](docs/CAREER_COVERAGE_2026-08-27.md) | That the top-100 anomalies were a per-fighter data-coverage asymmetry rather than a scoring choice, what completing the coverage fixed, and what it left behind |
| [Board and identification](docs/BOARD_AND_IDENTIFICATION_2026-08-25.md) | The current score contract: per-opponent title pricing, age decline projected through inactivity, and the two limits that gate the next scoring change |
| [Whole-sport engine](docs/PLAN_WHOLE_SPORT_ENGINE_2026-08-21.md) | The historical design for whole-sport scope, era depth, and the Single-Entry principle that separates this engine from points-stacking systems |
| [Prior mass and uncertainty](docs/PRIOR_MASS_AND_UNCERTAINTY_2026-08-20.md) | The historical prior-mass fix, retired period scores, and bootstrap rank intervals |
| [Principled core evolution](docs/PRINCIPLED_CORE_EVOLUTION_2026-08-20.md) | The historical core design and audit, with later amendments identified |

Superseded execution reports, completed prompts, and reverted experiments are
preserved in the [2026-08-26 documentation archive](_archive/20260826-stale-project-material/README.md).

## All-time top 100

Snapshot `2026-08-13`, scope `majors,pre_unified`, 80,697 rated bouts. This is
the **men's** board; the women's is published separately below, for a reason
given there. The published score is **Public Legacy Score**, and it is the sum of three
components, each divided by its own observed maximum and scaled to 1000 — so the
three columns below add back to the total, and no exchange rate between them was
hand-set:

- **Skill** — Career Skill Mass, the years-above-the-field functional defined
  under [The Core](#the-core), multiplied by an organisation-exposure factor.
- **Title** — every title win priced by the opponent actually beaten: their
  pre-fight rating against the contender line of their own division and year,
  after a **measured** pool correction. Held out, a fighter with prior UFC
  experience beats a never-UFC opponent by +54 Elo [+10, +100] more than the
  ratings predict, so that offset is added to a UFC-tested fighter's rating and
  to the contender line alike before the comparison. It is a ledger correction
  and never touches the bout likelihood. `UFC_POOL_OFFSET_ELO = 0.0` removes it.
- **Schedule** — wins over ranked opposition, on the same exposure factor.
  "Ranked" is the top fifth of that division's active field, not a fixed top
  fifteen: this corpus pools every promotion into one division, so the fields
  run from 37 to 119 active fighters and a fixed window meant 40% of women's
  strawweight against 13% of featherweight.

Three things this table does **not** claim:

1. **The numbering is score order, not a separation claim.** The board's only
   ordering claim is its tier boundaries; see [Rank uncertainty](#rank-uncertainty).
2. **Careers far from the tested UFC core are pinned far less precisely.** The
   interval on a mostly-external career can exceed its own published score,
   against roughly 1% for Jon Jones. The measurement and its consequences are in
   [Board and identification](docs/BOARD_AND_IDENTIFICATION_2026-08-25.md).
3. **A fighter absent from this table is not ranked 101st.** Insufficient
   history and a zero score are both abstentions, reported as such.
4. **A low `Skill` is not a measurement of no skill.** Career Skill Mass counts
   how far a fighter-year stood above the contender line of its own division and
   year, so a career that never cleared that line contributes little.

The zero-skill defect this section used to describe is **fixed** as of
2026-08-26, and the fix moved the board. Two things were wrong at once:

- The contender line was struck **sport-wide**, across divisions whose rating
  levels are not mutually identified — the 0.90 quantile of annual mean ran from
  1659 in women's strawweight to 1735 at light heavyweight, and nobody claims
  that 76-point gap is skill. It is now struck inside each division-year.
- The year hinge was an absorbing `clip(lower=0)`, and it absorbed **79,101 of
  80,881 fighter-years** into one tie at exactly zero — 93,625 of 95,412, the
  same 98%, on the larger corpus this engine now rates. Whittaker missed the
  sport-wide line by 14 rating points in the year he won the UFC middleweight
  title and therefore tied with Travis Fulton. It is now a softplus whose scale
  is **0.175 times that calendar year's population rating spread** (24.9 Elo in
  the median year on this corpus). That makes the bar, excess and softness move
  together under a pure rescaling of the ratings. The former fixed 25-Elo result
  remains reproducible with `hinge_scale=DEFAULT_HINGE_SCALE`.

The relative hinge is scale-equivariant on the fitted history: under
`mu' = 1500 + beta*(mu - 1500)` for beta in {0.5, 0.7, 1.4, 2.0}, the complete
rank vector has **zero movers**, top-100 overlap is 100/100, and scores equal
`beta` times their originals to floating-point precision. Switching the current
unscaled board from fixed 25 Elo to the relative hinge changes no top-100 member.

Eleven of the previous hundred scored exactly zero — Whittaker, Dillashaw, Dos
Anjos, Moreno, Sergio Pettis and every woman on the board. None do now.

### The corpus used to carry two coverage rules (fixed 2026-08-27)

"`mu_whr` over-rates lightly-tested careers" was the symptom. The cause was that
a fighter's whole career reached the model only if they had once appeared on a
PRIDE / WEC / Strikeforce / Affliction / Bellator / RIZIN card: 4,501 Sherdog
career pages were read and **the UFCStats roster was never among them**. Of the
1,825 fighters with three or more UFC bouts, 547 (30.0%) had a whole-career page,
with a median recorded pre-UFC record of **13 bouts against 1** for the other
1,278. Khabib Nurmagomedov was rated on 14 bouts; his record is 29.

That is a rating defect, not a reporting one. A low-loss Bradley--Terry record
has no interior maximum, so the prior alone stops the climb and the equilibrium
sits near \(\theta_{\text{opp}} + 173.72\ln(2k/v)\) — where \(k\) is *how many of
the fighter's bouts the corpus happens to hold*. Against a coverage-symmetric
refit, the correlation between the observed rating shift and that prediction is
**+0.740 for careers losing under 15%** and **−0.146 above 35%**: it binds
exactly where the theory says and nowhere else.

[`build_sherdog_careers.py`](build_sherdog_careers.py) completes the coverage:
1,278 fighter pages read, corpus 63,813 → 80,902 bouts, coverage of the eligible
roster **30.0% → 95.6%**. `loaders/career_coverage.py` states the property as a
number, the majors staging writes `career_coverage.parquet` and warns when it
fails, `rating_run.json` publishes it, and `tests/test_career_coverage.py` fails
on the shape that broke the board.

The plan document named this risk — "ragged data masquerading as coverage" — and
prescribed *per-promotion* completeness figures. Per promotion the corpus is
complete and `majors_coverage.json` says so. The raggedness was per fighter.

**What that fixed, and what it did not.** Usman Nurmagomedov, Yaroslav Amosov,
A.J. McKee and Ben Askren left the top 100; Khabib rose 19 → 15, Makhachev 7 → 4,
Adesanya 29 → 22, Whittaker 83 → 75, Couture 16 → 14. External-only careers in
the top 100 went 7 → 5, and the median UFC bout count of the fighters entering
the top 100 is 15 against 9 for those leaving it.

The pool-level error has now been diagnosed without putting an organisation
weight into the likelihood. Under the fitted constants the old complete-career
label reproduces **+104 Elo [+67, +148]**, but future UFC signees are already
**+274 [+185, +389]** against never-UFC opponents before debut. The offset rises
from +154 more than three years before debut to +463 inside one year. A smaller
+54 [+10, +100] prior-UFC residual remains, so selection on who crosses and when
is the main measured mechanism, not a claim that every residual is closed. The
estimator defect underneath is **untouched**: an
unbeaten record still climbs without bound relative to the opponents it beat, and
the repair made that symmetric rather than removing it. Re-measured on the
2026-08-28 board, Seika Izawa is **+319** above the best fighter she has ever
faced (it was +269) and Khabib **+206** (+192), because completing those records
lengthened the unbeaten runs. The 2026-08-28 ledger correction moved where those
careers *rank*; it did not touch the rating that produces the gaps. Izawa,
Johnny Eblen and Vadim Nemkov are still on the board.

Raising `WHR_VIRTUAL_GAMES` is **not** the remaining fix. The repaired-corpus
predictive fit instead selected `WHR_PRIOR_VAR = 8`,
`WHR_W2_PER_DAY = 0.0004`, and `WHR_VIRTUAL_GAMES = 1`: calibrated held-out
log-loss delta **-0.00201**, paired event-bootstrap 95% CI
**[-0.00349, -0.00060]**, and AUC **0.7041 -> 0.7067** versus the former
4/0.0004/2 base. The empirical-Bayes fixed point 0.58 answers a different,
in-sample marginal-likelihood question and was strongly worse predictively.
Neither is shrinking by reliability a fix: Bradley--Terry information is
*lowest* for the dominant (Jones 2.63, Khabib 1.59, against Donald Cerrone
10.55), so it would penalise dominance. The career functional is now
scale-equivariant, so this fit measures differential shrinkage rather than a
fixed-hinge scale artifact.

<!-- BOARD:TOP100:BEGIN -->

| # | Fighter | Score | Skill | Title | Schedule |
| ---: | --- | ---: | ---: | ---: | ---: |
| 1 | Jon Jones | 2940.8 | 1000.0 | 1000.0 | 940.8 |
| 2 | Georges St-Pierre | 2207.8 | 637.1 | 570.7 | 1000.0 |
| 3 | Daniel Cormier | 1659.5 | 477.8 | 553.3 | 628.4 |
| 4 | Islam Makhachev | 1576.6 | 648.6 | 642.4 | 285.6 |
| 5 | Jose Aldo | 1576.3 | 397.9 | 593.6 | 584.8 |
| 6 | Demetrious Johnson | 1552.2 | 391.7 | 637.4 | 523.1 |
| 7 | Alexander Volkanovski | 1404.0 | 262.7 | 587.6 | 553.6 |
| 8 | Stipe Miocic | 1324.1 | 258.0 | 547.9 | 518.2 |
| 9 | Anderson Silva | 1308.3 | 205.3 | 489.6 | 613.4 |
| 10 | Max Holloway | 1285.8 | 80.6 | 310.8 | 894.5 |
| 11 | Khabib Nurmagomedov | 1096.6 | 586.6 | 311.3 | 198.7 |
| 12 | Randy Couture | 1094.0 | 22.7 | 196.7 | 874.6 |
| 13 | Francis Ngannou | 1085.0 | 336.4 | 306.8 | 441.8 |
| 14 | Aljamain Sterling | 1033.9 | 144.4 | 325.9 | 563.7 |
| 15 | Ilia Topuria | 989.4 | 342.2 | 379.3 | 267.9 |
| 16 | Cain Velasquez | 987.5 | 193.5 | 258.9 | 535.2 |
| 17 | Dominick Cruz | 976.7 | 239.5 | 445.7 | 291.5 |
| 18 | Israel Adesanya | 968.1 | 176.1 | 326.7 | 465.4 |
| 19 | Matt Hughes | 940.2 | 165.1 | 410.5 | 364.6 |
| 20 | Chuck Liddell | 905.0 | 247.9 | 100.4 | 556.7 |
| 21 | Frankie Edgar | 897.6 | 95.5 | 80.9 | 721.3 |
| 22 | Patricio Freire | 886.5 | 227.3 | 302.3 | 356.9 |
| 23 | Merab Dvalishvili | 883.3 | 68.9 | 332.4 | 482.0 |
| 24 | Justin Gaethje | 857.3 | 142.3 | 276.4 | 438.6 |
| 25 | BJ Penn | 839.2 | 58.7 | 225.5 | 555.0 |
| 26 | Charles Oliveira | 815.7 | 60.2 | 130.4 | 625.1 |
| 27 | Henry Cejudo | 807.7 | 99.8 | 269.4 | 438.5 |
| 28 | Kamaru Usman | 799.5 | 52.6 | 200.5 | 546.4 |
| 29 | Alex Pereira | 785.5 | 60.0 | 262.8 | 462.7 |
| 30 | Ryan Bader | 752.4 | 79.7 | 70.9 | 601.9 |
| 31 | Lyoto Machida | 740.5 | 260.2 | 123.1 | 357.2 |
| 32 | Tyron Woodley | 739.7 | 34.2 | 126.6 | 578.9 |
| 33 | Chris Weidman | 736.5 | 83.4 | 183.8 | 469.2 |
| 34 | Khamzat Chimaev | 704.0 | 360.6 | 108.6 | 234.8 |
| 35 | Petr Yan | 700.0 | 115.8 | 202.2 | 381.9 |
| 36 | Fabricio Werdum | 692.0 | 64.8 | 153.9 | 473.3 |
| 37 | TJ Dillashaw | 679.6 | 37.3 | 103.8 | 538.5 |
| 38 | Dricus Du Plessis | 679.3 | 189.7 | 138.3 | 351.2 |
| 39 | Joseph Benavidez | 670.7 | 288.7 | 0.0 | 382.0 |
| 40 | Benson Henderson | 667.2 | 75.2 | 250.8 | 341.2 |
| 41 | Dan Henderson | 653.9 | 302.4 | 30.6 | 320.9 |
| 42 | Vitor Belfort | 638.1 | 128.9 | 30.9 | 478.2 |
| 43 | Junior Dos Santos | 615.5 | 112.8 | 165.6 | 337.1 |
| 44 | Fedor Emelianenko | 607.2 | 307.4 | 216.2 | 83.6 |
| 45 | Rashad Evans | 606.9 | 94.0 | 35.6 | 477.3 |
| 46 | Deiveson Figueiredo | 593.3 | 127.5 | 66.8 | 399.0 |
| 47 | Ciryl Gane | 574.0 | 303.9 | 77.5 | 192.5 |
| 48 | Michael Chandler | 568.4 | 64.9 | 188.2 | 315.3 |
| 49 | Luke Rockhold | 551.8 | 44.6 | 84.9 | 422.3 |
| 50 | Conor McGregor | 551.3 | 21.0 | 264.0 | 266.3 |
| 51 | Sean Strickland | 542.9 | 66.0 | 177.4 | 299.6 |
| 52 | Vadim Nemkov | 534.1 | 169.8 | 172.3 | 192.1 |
| 53 | Eddie Alvarez | 525.1 | 51.1 | 156.0 | 318.0 |
| 54 | Yoel Romero | 524.0 | 44.3 | 0.0 | 479.7 |
| 55 | Leon Edwards | 512.9 | 6.9 | 172.8 | 333.3 |
| 56 | Brandon Moreno | 511.1 | 3.5 | 117.3 | 390.2 |
| 57 | Dustin Poirier | 507.4 | 44.0 | 137.9 | 325.5 |
| 58 | Movsar Evloev | 504.6 | 289.2 | 0.0 | 215.3 |
| 59 | Rafael Dos Anjos | 503.4 | 1.5 | 77.6 | 424.2 |
| 60 | Frank Mir | 500.9 | 1.1 | 130.6 | 369.2 |
| 61 | Robbie Lawler | 497.4 | 10.0 | 92.6 | 394.7 |
| 62 | Robert Whittaker | 490.1 | 32.3 | 66.6 | 391.3 |
| 63 | Anthony Pettis | 485.7 | 15.3 | 199.1 | 271.2 |
| 64 | Quinton Jackson | 481.4 | 62.7 | 92.6 | 326.1 |
| 65 | Tim Sylvia | 462.6 | 16.3 | 115.3 | 331.0 |
| 66 | Beneil Dariush | 459.2 | 7.1 | 0.0 | 452.0 |
| 67 | Tito Ortiz | 457.6 | 162.4 | 75.4 | 219.8 |
| 68 | Mauricio Rua | 456.7 | 88.6 | 130.8 | 237.3 |
| 69 | Donald Cerrone | 433.8 | 35.7 | 0.0 | 398.2 |
| 70 | Joshua Van | 427.9 | 78.4 | 152.0 | 197.5 |
| 71 | Renan Barao | 420.3 | 44.2 | 149.2 | 227.0 |
| 72 | Anthony Johnson | 418.5 | 41.6 | 0.0 | 376.9 |
| 73 | Sean O'Malley | 413.1 | 80.3 | 107.3 | 225.6 |
| 74 | Demian Maia | 401.4 | 121.1 | 0.0 | 280.2 |
| 75 | Kyoji Horiguchi | 401.2 | 165.4 | 30.9 | 205.0 |
| 76 | Rich Franklin | 396.3 | 173.5 | 35.0 | 187.8 |
| 77 | Sean Sherk | 394.2 | 141.3 | 54.6 | 198.3 |
| 78 | Phil Davis | 392.3 | 126.5 | 27.1 | 238.7 |
| 79 | Shavkat Rakhmonov | 391.9 | 301.9 | 0.0 | 90.0 |
| 80 | Urijah Faber | 390.3 | 130.3 | 6.9 | 253.1 |
| 81 | Gegard Mousasi | 381.6 | 81.1 | 94.6 | 206.0 |
| 82 | Wanderlei Silva | 374.6 | 249.7 | 67.5 | 57.3 |
| 83 | Josh Barnett | 370.9 | 216.5 | 21.2 | 133.1 |
| 84 | Michael Bisping | 363.2 | 34.0 | 55.0 | 274.2 |
| 85 | Johnny Eblen | 356.5 | 173.9 | 71.0 | 111.6 |
| 86 | Matt Serra | 335.8 | 20.7 | 218.2 | 96.8 |
| 87 | Tom Aspinall | 332.3 | 28.9 | 127.8 | 175.6 |
| 88 | Michael Morales | 331.3 | 214.8 | 0.0 | 116.5 |
| 89 | Alexander Volkov | 330.3 | 42.6 | 2.7 | 285.0 |
| 90 | Colby Covington | 314.5 | 3.2 | 28.0 | 283.3 |
| 91 | Belal Muhammad | 312.6 | 10.5 | 35.8 | 266.2 |
| 92 | Jacare Souza | 309.1 | 76.8 | 0.0 | 232.3 |
| 93 | Alistair Overeem | 309.0 | 6.4 | 2.8 | 299.8 |
| 94 | Sergio Pettis | 308.1 | 6.5 | 116.5 | 185.1 |
| 95 | Usman Nurmagomedov | 308.0 | 223.5 | 66.9 | 17.6 |
| 96 | Jussier Formiga | 298.4 | 66.4 | 0.0 | 232.0 |
| 97 | Carlos Ulberg | 297.3 | 90.3 | 32.5 | 174.5 |
| 98 | Chad Mendes | 291.0 | 139.8 | 0.0 | 151.3 |
| 99 | Alexandre Pantoja | 290.7 | 62.4 | 75.3 | 153.0 |
| 100 | Ben Askren | 289.2 | 127.5 | 90.9 | 70.8 |

<!-- BOARD:TOP100:END -->

Regenerate this table from a rebuilt snapshot with `build_boards.py
--write-readme`; see [Rebuild](#rebuild).

### Women's all-time top 10

The table above is the **men's** board, and that is an identification statement
rather than a default. "All-time" and "Prime" without a gender mean men's.

<!-- BOARD:WOMEN10:BEGIN -->

Men and women never fight, so no bout locates the two rating levels against each other: their relative level is set by the prior, not by evidence, and one number cannot rank them together. The boards are therefore separate, and each one's ranks are identified within it.

| # | Fighter | Score | Skill | Title | Schedule |
| ---: | --- | ---: | ---: | ---: | ---: |
| 1 | Amanda Nunes | 1681.0 | 475.5 | 587.5 | 618.0 |
| 2 | Valentina Shevchenko | 1472.3 | 522.2 | 399.7 | 550.4 |
| 3 | Zhang Weili | 1160.5 | 358.5 | 242.4 | 559.7 |
| 4 | Rose Namajunas | 977.9 | 101.1 | 363.5 | 513.4 |
| 5 | Ronda Rousey | 746.1 | 306.8 | 147.5 | 291.8 |
| 6 | Cristiane Justino | 725.3 | 577.8 | 82.5 | 65.0 |
| 7 | Jessica Andrade | 706.2 | 20.0 | 68.1 | 618.1 |
| 8 | Joanna Jedrzejczyk | 611.6 | 148.9 | 104.3 | 358.4 |
| 9 | Tatiana Suarez | 591.7 | 396.2 | 0.1 | 195.5 |
| 10 | Seika Izawa | 450.0 | 234.7 | 0.0 | 215.3 |

<!-- BOARD:WOMEN10:END -->

Both blocks come from the same `build_boards.py --write-readme` run, so the two
boards cannot drift apart.

## The Core

Every decided bout contributes one Bradley--Terry likelihood. The winner and
loser share the same bout weight:

\[
\ell_b=\omega_b\{y_b\log\sigma(\theta_i-\theta_j)
+(1-y_b)\log\sigma(\theta_j-\theta_i)\}.
\]

\(y_b\) is the winner's score, and since 2026-08-28 it carries the **method of
victory**: 1.00 for a KO/TKO or submission, 0.95 for a unanimous decision, 0.90
for a split or majority one, 0.85 for a DQ. A finish is a less ambiguous
observation of a skill gap than a split decision, and that is a statement about
the *outcome*, not about how much the bout weighs -- so it lives in \(y_b\) and
not in \(\omega_b\). It was measured before it shipped: calibrated held-out log
loss **-0.00332**, 95% event bootstrap **[-0.00503, -0.00161]**, AUC 0.6967 ->
0.7006, over 2,039 bouts and 371 events. The confound was excluded too -- a
*constant* winner score with the same mean but no method grading is worth
nothing (+0.00018 [-0.00033, +0.00065]), so the gain is method of victory and
not uniform outcome shrinkage. `WHR_WINNER_SCORE_COL = None` restores the binary
model.

The mirror-image claim **failed** and is not in the model: giving title fights,
five-round fights or finishes a larger \(\omega_b\) never improved held-out
prediction, and the finish weighting was significantly *worse* on decisions.
"More important" and "more informative" are different claims, and only the first
one turned out to be true.

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
the fix, the highest rating of all 2,554 UFC fighters then rated belonged to a man with one UFC
bout, and 56 fighters at 1-0 averaged above the 98th percentile of the roster;
going from 1-0 to 10-0 bought 67 rating points.

Both priors carry a fixed mass per fighter, spread across that fighter's
appearances: a Gaussian anchor (`WHR_PRIOR_VAR = 8`) and
`WHR_VIRTUAL_GAMES = 1` bout of prior evidence against an average opponent,
half won and half lost, as in Coulom's paper. Those constants were selected
jointly on 14 rolling cutoffs / 8,435 paired bouts after the whole-career corpus
repair. Prior variance 16 was worse, virtual mass 0.5 was unresolved, and the
temporal variance remained at 0.0004 because 0.0002 was unresolved. The
incremental prior-variance gain after changing virtual mass was also unresolved,
so the components are not claimed to be independently identified. An undefeated
fighter with \(k\) wins over average opposition settles at
\(\sigma(r)=(k+v/2)/(k+v)\), which rises with the evidence as it must.

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

The published bar is `contender:5` **inside each division-year**: that
division's top five that year, or its top decile while the division is smaller
than fifty rated fighter-years. A division-year thinner than thirty falls back
to the sport-wide `contender:60`, because too few fighters cannot describe a
contender line. `count:N`, `mean`, numeric quantiles and `hybrid:<lambda>`
remain explicit research alternatives, and omitting the division labels
reproduces the sport-wide bar exactly.

Scoping the bar to the division does **not** post field depth twice. That
objection holds only where the rating scale is identified across divisions, and
it is not: divisions barely fight each other, so the offset between two
divisions' levels is set by the prior rather than by evidence. Measured on the
2026-08-13 snapshot, 5.64% of light heavyweight fighter-years cleared the old
sport-wide line against 0.65% of women's strawweight ones — an 8.7x gap that is
an artifact of that unidentified offset, not a depth measurement.

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

**Every one of these views is ranked within a gender, and "All-time" or "Prime"
without one means men's.** Men and women are disjoint components of the bout
graph -- 0 of 80,697 rated bouts and 0 shared opponents join them -- so adding a
constant to every women's rating changes no modelled bout probability while
moving the mixed board a great deal. Ranks inside each component are identified;
one number across both is not. See
[Women's all-time top 10](#womens-all-time-top-10).

## What Is Not in the Core

- **Titles, rankings, P4P labels, streaks, and odds** are descriptive or
  benchmarking data, not repeated rating bonuses. Championship status was tested
  as a likelihood *precision* on 2026-08-28 and failed, so it stays a ledger
  term only.
- **Method of victory** is the one exception, and it is in \(y_b\), not a
  bonus: see [The Core](#the-core). Dominance remains a published diagnostic.
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

Held-out charts load only when `prequential_summary.json` matches the current
prequential cache schema. The older evaluation was archived on 2026-08-26 and
no replacement was built during that cleanup, so the dashboard deliberately
shows an unavailable-evidence panel until a separately authorized evaluation.

### Investigations

The 2026-08-21 top-100 era-skew investigation established that the apparent
modern-era wall was a scope defect, not a density or drift-rate defect. Its
notebook, helper modules, tests, and caches are now preserved together in the
[2026-08-26 archive](_archive/20260826-stale-project-material/investigation-top100-era-skew/README.md).
It is historical evidence, not a runnable description of the current
`majors,pre_unified` engine.

## Current Data Scope

The standard local snapshot is `data/snapshots/2026-08-13`:

- 81,308 combined fight rows, 80,697 model bouts;
- 33,692 fighters in the whole-sport scope;
- 0 duplicate bout fingerprints after scope guard;
- 95.6% of the fighters with three or more UFC bouts have a whole-career page,
  which is the per-fighter coverage figure the board depends on;
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

`--write-readme` rewrites the blocks between the `BOARD:TOP100` and
`BOARD:WOMEN10` markers in this README from the boards it just built, so the two
published tables cannot drift away from the artifacts or from each other. It is
opt-in; without it the boards are written and the README is left alone.
Snapshots are not committed, so those tables are the only published form of the
board. `--women-top` sets the length of the second one.

Audit candidate organisation weights against the top-100 sanity panel:

```bash
python build_org_strength_audit.py "data/snapshots/2026-08-13" --out-dir data/model_tuning/org-strength/2026-08-13
```

Publish rank intervals for the career board. Each replicate is a full refit, and
the 80,697-bout age-aware scope takes about five minutes of it on the measured
machine; 12 replicates are an exploratory check, while a 150-replicate release
run needs an overnight budget:

```bash
python build_uncertainty.py "data/snapshots/2026-08-13" --replicates 12
```

`refresh.py --bootstrap-replicates 12` does the same inside a full refresh.

Regenerate held-out evaluation after any estimator or probability change:

```bash
python build_prequential_evaluation.py "data/snapshots/2026-08-13" \
  --events 40 --calibration-events 40 --mode recent --force \
  --scope majors,pre_unified \
  --artifact-dir "data/snapshots/2026-08-13"
```

`--scope` defaults to the published scope. It did not exist before 2026-08-28,
and without it this harness scored **UFC-only** -- 8,479 bouts against the
board's 80,697 -- so the gate certified a model the board does not use. The
scope it ran on is now recorded in `prequential_summary.json`. Each WHR fold is
a full refit, so cost scales with `--events`.

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
| `majors` | the Sherdog whole-career corpus | seeded by an event crawl of PRIDE, WEC, Strikeforce, Affliction, Bellator and RIZIN, then extended to one page per fighter so the six-promotion boundary stops censoring records. Until 2026-08-27 that extension covered only the fighters who had appeared on one of those cards, so the UFCStats roster stayed truncated; `build_sherdog_careers.py` closed it. 80,902 bouts, 33,638 fighters, 1980-2026 |
| `pre_unified` | UFC 1-27 | recovered from the snapshot's own `_excluded_bouts.csv` |
| `fightmatrix` | a bounded ranked-cohort crawl | seeded from **today's** FightMatrix rankings |
| `all` | every staged corpus | |

The published default is `majors,pre_unified`.

Combine explicitly: `--scope majors,pre_unified`.

The naming is not bureaucracy. The two non-UFC corpora move the board in
**opposite directions**, because of how each was built — `majors` reaches back
to 1997 and back-fills the early era, while `fightmatrix` is seeded from
currently ranked fighters and back-fills the modern regional circuit:

Scope sensitivity measured on the **2026-08-21 corpus at the 0.9 bar** — kept
because the *direction* is the point and it is what named the two corpora, but
every bout count below predates the 2026-08-27 career-coverage repair and none of
them describes the current published board:

| scope | bouts (2026-08-21 corpus) | top-100 active in 2024 | median debut |
|---|---:|---:|---:|
| `ufc` | 8,479 | 70 | 2015 |
| `majors` | 67,820 | 57 | 2009 |
| `majors,pre_unified` | 67,920 | 57 | 2009 |
| `fightmatrix` | 18,312 | 85 | 2012 |

Current, for the published scope only: `majors,pre_unified` is **80,697** model
bouts of an 82,170-row maximum-coverage table (`majors` 72,577, `ufc` 8,479,
`fightmatrix` 862, `pre_unified` 252, before the scope guard's drops), and 53 of
its top 100 were active in 2024 or later.

```bash
# Stage every corpus the inputs support, then rate one scope.
python refresh.py --snapshot-date 2026-08-13 --scope majors,pre_unified
```

Two rules hold across every scope.

**No organisation weight *in the likelihood*.** Relative promotion strength is
an *output* of the joint fit, read off the fighters who crossed between
promotions. A weight would assert the answer the fit exists to estimate — and
the weights that existed were derived from fighters' *eventual UFC careers*, so
a 2003 PRIDE bout was priced by what its participants went on to do years later.
Production discards any staged `org_weight`; `--experimental-org-weight` opts
back in and says so.

This rule governs the **rating layer** and is unchanged. The achievement ledger
is a different layer and does carry a measured pool correction
(`UFC_POOL_OFFSET_ELO`, see [The Core](#the-core) and
[Rating layer and ledger](docs/RATING_LAYER_AND_LEDGER_2026-08-28.md) §3-4):
held out, a UFC-tested fighter beats a never-UFC opponent by +54 Elo
[+10, +100] more than the ratings predict, and most of the larger +104 Elo
whole-pool gap turns out to be **selection** — future signees already run +274
Elo ahead of their rating *before* their UFC debut. Selection is not promotion
strength, so nothing was subtracted from any bout probability.

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
ratings/                     Glicko-2, WHR, Career Skill Mass, policy boards
loaders/                     UFCStats and optional-source ingestion
build_boards.py              Integrity ledger/debit, completeness views, both published tables
build_sherdog_careers.py     Completes per-fighter career coverage; idempotent, cache-first
build_top100_audit.py        Board diagnostics: anchor coverage and external-career outliers
build_prequential_evaluation.py  Rolling-origin validation artifacts (takes --scope)
build_uncertainty.py         Event-bootstrap rank intervals and tiers
build_database.py            SQLite export
data/SOURCE_MATRIX.md        Field-level provenance and coverage contract
docs/                        Current audit and design notes
_archive/                    Dated superseded records and closed-question research
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
