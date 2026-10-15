# Open decisions, remaining data work and settled ground

The one register for unresolved model choices, remaining data work, accepted
limitations and changes already tried and refused. Two separate registers were
kept until 2026-09-01 and repeated six of seven refusals word for word; they are
in `_archive/20260901-lean-pass/docs/` with the analysis that produced them.

How the engine works is a different document:
[How the ratings and the score are built](RATING_LAYER_AND_LEDGER_2026-08-28.md).
Where the data comes from is [Source Matrix](../data/SOURCE_MATRIX.md).

## Rules that bind every change

- **Count each fact once.** Career length already has a home, in a score that
  takes at most one contribution per active year. Anything else that grows with
  career length is charging for the same thing twice.
- **A rating change passes a held-out prediction test. A score change cannot.**
  The score never predicts a fight, so it is argued from mechanism and checked
  against outside reference lists — and the check reports how much it can
  actually detect.
- **Report unresolved as unresolved.** An earlier assessment is handed to you to
  attack, this document included.

## Open model and score decisions

1. **A major title now carries a minimum credit; what the title term still
   cannot price is the rest.** Shipped 2026-09-02. A title win is priced
   `floor + (1 - floor) * q**4` with `floor = 0.05`, applied only to
   championships in a tier-1 promotion — UFC, PRIDE, Zuffa-era WEC,
   Showtime-era Strikeforce, 2011-onward Bellator, Affliction. 614 of 653
   priced title wins clear that gate.

   The defect it fixes is real and was visible on named fighters: value comes
   from the opponent beaten against their own division-year line, which is right
   in general and wrong at the bottom. Glover Teixeira rated 1879 against an 1865
   bar, so winning the UFC light-heavyweight title priced at **0.073**; it now
   prices at **0.119**. Winning a major world championship is an achievement in
   itself and the score now says so, without paying the flat per-belt bonus the
   2026-08-25 rebuild removed.

   Measured on a fixed population before adoption, against no floor:

   | floor and gate | top 100 scoring zero on titles | agreement, elite wins | agreement, Prime | Serra |
   |---|---:|---:|---:|---:|
   | none | 16 | 0.5911 | 0.5312 | 60 |
   | **0.05, major promotions only — shipped** | **14** | **0.6055** | 0.5238 | 70 |
   | 0.10, major promotions only | 14 | 0.6114 | 0.5210 | 74 |
   | 0.10, any title | 14 | 0.6123 | 0.5205 | 74 |

   Single-upset padding does **not** return: Matt Serra falls, because a floor
   paid to every champion dilutes a career built on one exceptional win. All
   sixteen outside-list intervals straddled zero, so the outside check could not
   separate these and no claim is made that it did.

   **What is still open.** Three things the floor does not touch, each of which
   would need its own measurement:
   - A tier-2 championship gets nothing extra. That is the promotion judgement
     the gate deliberately makes, and it is a policy, not a finding.
   - Title *losses* still price at nothing, while a loss to an elite champion is
     priced higher than most wins on the opponent scale. Crediting them was
     measured and refused on 2026-09-01 because it pays for exposure rather than
     contention; that refusal stands.
   - Below the floor the ordering is gone rather than merely small. Two major
     title wins over opponents far under their line used to differ by an order of
     magnitude and now both read about 0.050. Any test asking what the *bar*
     does must pass `major_title_floor=0.0`.

   Harness: `Claude Func Folder\ufc-rank-engine\py\title_floor_shapes.py`.
2. **The ratings themselves are the largest error, and completing the data fixed
   part of it.** Measured as a fighter's final rating minus the final rating of
   the strongest opponent they ever faced:

   | fighter | before career completion | after | why |
   |---|---:|---:|---|
   | Seika Izawa | +319 | **+320** | her record was already complete; nothing was added |
   | Khabib Nurmagomedov | +206 | **+160** | rated on 14 fights before, 30 after |

   That is the coverage argument confirming itself: the fighter whose record was
   truncated moved, the fighter whose record was already whole did not. The gap
   that remains is the real one, and every board still reads it.
3. **A single upset can still climb, but less than it did.** Matt Serra sits at
   **70** on the board published 2026-09-02, having been 60 before the major-title
   floor; the floor moved him down because a minimum paid to every champion
   dilutes a career built on one exceptional win. The concern itself stands: he
   still keeps rising as the achievement weight rises — measured before the floor
   at 60 / 49 / 43 / 40 for weights 0.30 / 0.40 / 0.50 / 0.60, a sweep that has
   not been re-run since. The weights are owner policy, and this is what raising
   the achievement weight buys.
4. **The promotion table is typed in by hand** and multiplies both quality
   components. It is not fitted to anything. A measurement on 2026-09-01 found no
   *further* promotion term is needed — after the +54 correction a UFC title win
   prices at 0.119 against Bellator's 0.059, difference +0.061, CI95 [+0.044,
   +0.078] — but the table itself was never justified.

   **What an unlabelled bout is worth is now settled.** Shipped 2026-09-02. 54.1%
   of rated bouts carry no promotion, and the rule this replaced read every one of
   them as the lowest tier, 0.20 — the same number a genuinely small show gets.
   An unlabelled bout is missing evidence, not evidence of a weak promotion, so it
   is now left out of the two averages, and the identified-bout factor is shrunk
   back toward the pooled mean of every identified bout by `n / (n + k)` with
   `k = 5` bouts. Reading unlabelled bouts at the floor is the `k -> inf` limit of
   that estimator with the floor as its prior; dropping them outright is `k = 0`,
   which reads a career identified on two bouts at those two bouts' level with
   full confidence.

   Re-measured on 2026-09-08 after the promotion vocabulary was completed, since
   the arms had first been compared while a rule-table gap was reading 13.5% of
   labelled bouts as unlabelled. `k = 5` still wins: it holds the guard that
   top-100 fighters with no UFC bout stays at three, and reads 0.6479 against
   elite wins where the tier-4 rule reads 0.6337. `k = 10` breaks that guard at
   four and is the bound above.

   Measured on one fixed population against the shipped board:

   | unlabelled bout treated as | top 100 with no UFC bout | top 100 zero on titles | agreement, elite wins | agreement, Prime |
   |---|---:|---:|---:|---:|
   | lowest tier, 0.20 — the rule replaced | 3 | 12 | 0.6337 | 0.6153 |
   | left out, no shrinkage (`k = 0`) | 3 | 13 | 0.6403 | **0.6434** |
   | recognised regional, 0.42 | 3 | 12 | 0.6304 | 0.6235 |
   | left out, `k = 1` | 3 | 13 | 0.6423 | 0.6404 |
   | left out, `k = 3` | 3 | **12** | 0.6445 | 0.6335 |
   | **left out, `k = 5` — shipped** | **3** | **12** | **0.6479** | 0.6260 |
   | left out, `k = 10` | **4** | **11** | 0.6455 | 0.6184 |

   `k = 10` is the bound above: it breaks the failure that refuted removing
   exposure altogether on 2026-08-27, putting a fourth fighter with no UFC bout in
   the top 100. Every lighter arm holds that guard at 3.

   **The outside check could not detect any of this.** Against the replaced
   tier-4 arm, the shipped arm reads The 100 Greatest +0.0086 (p 0.17),
   FightMatrix +0.0031 (p 0.42), Tapology +0.0121 (p 0.58) and ESPN +0.0242
   (p 0.58). Every sign test across every arm came back p >= 0.12. This ships on
   mechanism, which is what a score change ships on, and no claim is made that
   the outside lists chose it.

   **Two corrections to what this item used to say.** The three-way table it
   carried was measured against the *pre-floor* board — baseline elite wins
   0.5911, Prime 0.5312 — so its numbers are not comparable with anything
   measured since, and they are replaced above rather than extended. On that
   pre-floor population, leaving unlabelled bouts out moved FightMatrix −0.0272
   (p 0.052); re-measured against the completed shipped board the same arm moves
   it +0.0031 (p 0.42). The direction reversed with the population, which is why
   the earlier run cannot be read as evidence either way.

   **What the change does not fix.** Sean Strickland rises 20 to 17, and he is
   this project's named symptom of paying for exposure rather than contention.
   That movement is common to every arm that changes anything at all except the
   0.42 arm, so it does not separate the shipped rule from its alternatives — but
   it is not answered by it either. A career identified from a handful of bouts
   still receives an estimate rather than an admission that it cannot be told
   apart. Harness:
   `Claude Func Folder\ufc-rank-engine\py\exposure_unknown_shapes.py`, which
   also refuses a run unless the shipped ledger exactly reproduces `shrink5`.
5. **Two contender bars, not one.** The résumé uses the absolute contender line;
   the title résumé uses a division-year quantile. Unifying them was measured and
   reverted on 2026-08-26 for reasons that still hold: fix the rating first.
6. **`WHR_W2_PER_DAY` is bounded below but still not fitted from above.**
   How fast a rating is allowed to drift between fights is the one production
   setting a held-out test can actually choose, so it was re-measured on the
   completed corpus (2026-09-02: seven rolling origins, 180-day scoring windows,
   temperature learned only on earlier folds, event bootstrap, 1,417 events and
   4,060 scored bouts).

   | drift setting | log loss against 0.0004 | 95% CI | resolves? |
   |---|---:|---|---|
   | 0.0002 | **+0.00178** worse | [+0.00033, +0.00323] | **yes — worse** |
   | 0.0008 | +0.00161 worse | [−0.00033, +0.00349] | no |

   Brier agrees on both rows. This closes half the question and leaves the other
   half open: halving the drift is now *resolved worse*, where the 2026-08-28
   refit could only say it did not resolve, so the setting is no longer free to
   move down. Doubling it is still merely unresolved, so nothing has bounded it
   from above. **0.0004 stays**, because a setting change ships only on a
   resolved improvement and there is none. Harness:
   `Claude Func Folder\ufc_whr_drift_recalibration.py`.

**The WHR fit was repaired on 2026-10-09, and the boards were refitted with it on
2026-10-13.** The fit used to subtract the average rating after every pass. The
anchor and virtual-game priors already fix where the scale sits, so the shift
pulled the fit away from the posterior it claims to solve, and a fight between
two fighters could move the ratings of fighters they never met. In the
[2026-10-08 review](validation/review-2026-10-08/EVALUATION.md)'s ten-fight example, adding ten unrelated fights moved the gap
between the winner and the last opponent by 93.88 points. The shift is gone.
`tests/test_whr_joint_map.py` now checks that the fit reaches the posterior's
stationary point and that unconnected fights leave existing ratings unchanged.

Three smaller repairs from the same review shipped with it. The accuracy check
now forecasts with each fighter's uncertainty as it stood entering the event,
including growth from inactivity, instead of the value after his previous fight
(cache schema 9, so older cached predictions are not reused). The Prime window
reports the ten years its level is actually averaged over. Paired comparisons
resample whole cards rather than single bouts, because bouts on one card are not
independent.

Held-out check against `c0072b4`, scored on 2004 cards: log loss −0.0143,
95% CI [−0.0506, +0.0240]; Brier −0.0065, [−0.0230, +0.0118]; 38 bouts on 5
cards. **Did not resolve.** Birth dates were not available, so age drift was
neutral, which means this is not the production model. It shows the repair does
not damage prediction on that sample. It is not the held-out test a rating
change must pass, which needs the production inputs. Evidence:
`docs/validation/whr-solver-2026-10-09/`, harness
`analysis/check_whr_solver.py`.

**The refit, 2026-10-13.** The inputs had been lost from this machine and were
rebuilt: the UFCStats tables from Greco's CSVs at commit `9ffbd78` (2026-09-01,
last card 2026-08-29); 5,601 Sherdog fighter pages (the career pages behind the
committed bouts, every fighter on a Bellator card, and the identity-resolution
pages); and the 302 Fight Matrix profiles. The rebuilt corpus is the published
one: 81,512 rated bouts, 163,024 history rows, 34,126 rated fighters, 6,193
events and 1,827 of 1,827 careers covered, and `combined_fights.parquet` is
byte-identical. It holds 5,969 birth dates against the 6,012 the release used.

Two checks separate the repair from the rebuild. Refitted with the *old* solver,
the rebuilt inputs reproduce every rank in all four published tables, so the 43
missing birth dates move nothing and every change below is the repair's. The
repaired fit gives the same ratings at 50 and at 200 passes, so the change is
not an unconverged solve.

The repair moves the boards substantially. In the men's all-time top 100, 90
fighters remain, 2 hold their rank, and the median move is 9 places. Earlier
eras rise and recent fighters fall: Donald Cerrone 90 to 40, Fabricio Werdum 74
to 39, Demian Maia 76 to 43; Movsar Evloev 45 to 93, Tom Aspinall 61 to 96. The
fighters this register tracks: Strickland 17 to 38, Whittaker 46 to 41, Usman 24
to 19, Dariush 69 to 63, Anthony Johnson 50 to 80, Chandler 87 to 92, Serra 78
to outside the top 100, Prochazka outside before and after, and Neil Magny from
outside to 74. On the Prime board Cerrone moves 50 to 7 and Khamzat Chimaev 16
to 50; the current board barely moves (median 2 places).

**Still open.** Magny entering the top 100 and Cerrone at 7th on Prime are the
kinds of result this register treats as symptoms. The score layer's constants
(exposure, contender bars, title floor) were set against ratings the old solver
produced; whether they still hold on the repaired ratings is unmeasured, and the
review's instruction stands: do not tune them around the solver. Not measured:
the held-out comparison on these production inputs (about 4.5 hours:
`python analysis/check_whr_solver.py data/snapshots/2026-08-13 --years 2024 2025
--workers 6 --out docs/validation/whr-solver-2026-10-13`), and agreement with
the outside lists.

**A win over a fighter returning from a long absence is priced lower.** Shipped
2026-09-03, in the ledgers, after the rating-layer version was built and
refused.

The rating charges age but cannot distinguish active time from idle time. Stipe
Miocic was 35 and active when Daniel Cormier fought him, then 42 and 44 months
out when Jon Jones did; the rating alone separates the Stipe Cormier beat from
the one Jones beat by 35 points, while the Jones win is priced 232 points below
its unadjusted value.

`ratings/layoff.py` now discounts the opponent's price by how far past a normal
turnaround they had been idle, at `OPPONENT_LAYOFF_ELO_PER_TURNAROUND = -90`,
capped at 4 turnarounds. One function, used by the title ledger, the contender
resume and the elite-Prime gate, so all three agree about what beating a
returning fighter is worth. It changes no rating: a fighter's own number
continues to say what their fights say.

**The unit is an era-normal turnaround, not a year.** A fixed number of days
cannot mean "a layoff" across this corpus. The 75th-percentile gap between bouts
runs 112 days in 1995 and 392 in 2020 — fighters used to compete five times a
year and now fight twice — so charged in days past a fixed 270-day grace, a
2020-era transition is charged 0.416 idle years against 0.087 for a 1995-era
one, 4.8x. Divided by the era's own normal, mean charged excess runs 0.298
turnarounds in 1995 against 0.369 in 2025.

## Tested and refused: the layoff charge does not belong in the rating

Charging the layoff inside the WHR transition prior was implemented, measured on
the full corpus and reverted the same day. **Do not propose it again.**

A transition prior constrains the *difference* between consecutive nodes, while
a fighter's level is pinned by their record. "You declined across this gap" is
therefore equally satisfiable as "you used to be better", and for gap-heavy
careers the fit chooses the second:

| fighter | early career | late career | peak |
|---|---:|---:|---:|
| Sean Sherk | 1927 → **2124** | −36 | **+197** |
| Mark Coleman | 1768 → **1948** | −170 | **+179** |
| Stipe Miocic | −19 | 1936 → 1615 | −14 |
| Movsar Evloev | −14 | −103 | −30 |

Sean Sherk's 1999 rating rising to 2125 would make him one of the highest-rated
fighters in the corpus. Career Skill Mass sums rating above a per-year bar, so
inflated early peaks inflate the all-time score, and erratic careers concentrate
in the old era: rank agreement with the previous board fell to **0.813**, with
Sean Sherk +59 places, Mark Coleman +44 and Josh Barnett +42 against Movsar
Evloev −35, Ciryl Gane −31 and Sean Strickland −24. That is the era skew this
project has already fought once, re-entering through a side door.

It is structural, not a tuning failure. Re-running it in era-normal units rather
than days made the skew **worse** (0.895 → 0.813), because normalising the unit
does not stop a symmetric prior from raising the earlier node. The only
rating-layer fix would be a one-sided force on the post-layoff node, which is
not a valid joint prior and was not adopted.

**The fitted age curve is estimated on survivors, and says a 42-year-old
declines more slowly than a 37-year-old.** Open, and the reason the layoff term
below is supplied rather than fitted.

The curve is built from *observed transitions* — the change between one
appearance and the next. A fighter needs a next appearance to contribute one, so
a decline steep enough to end a career is never in the sample. The censoring
rate rises exactly where the decline should be steepest:

| age bucket | appearances | career-ending | censored |
|---|---:|---:|---:|
| <24 | 20,541 | 162 | 0.8% |
| 30-33 | 17,465 | 1,263 | 7.2% |
| 33-36 | 10,920 | 1,237 | 11.3% |
| 36-39 | 5,488 | 933 | 17.0% |
| 39-42 | 2,183 | 441 | 20.2% |
| 42+ | 1,295 | 363 | 28.0% |

and the fitted curve turns the wrong way at the same point:

| bucket | <24 | 24-27 | 27-30 | 30-33 | 33-36 | 36-39 | 39-42 | 42+ |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Elo/year | 0.00 | -1.55 | -3.78 | -5.48 | -6.43 | **-6.83** | **-5.86** | **-3.87** |

Ageing does not slow down at 39. The fighters who kept appearing after 39 are
the ones it had not yet caught. Correcting this needs a censoring model — the
decline has to be inferred from the fact that the career stopped, which is
survival analysis, not a bucket mean — so it is recorded here rather than
patched with a hand-drawn curve. Until it is done, the age term understates
decline in exactly the buckets where a published board is most likely to be
questioned, and no measured rate from this estimator should be quoted as the
cost of aging.

## Completed data work

7. **Whole-career coverage is complete.** Resolved 2026-09-08. The completion
   crawl fetched all eleven pages exposed by the identity repair, parsed 252
   career rows and added 153 fights after event-card precedence. Merged coverage
   is 1,827 of 1,827 eligible careers, 100.0%, with no unresolved source-ID
   conflict.

   The full published scope was restaged, refitted and republished. In particular,
   the 2021-05-22 flyweight bout against Victor Rodriguez now aligns to
   `Bruno Silva (sherdog:118601)`: all eleven of his UFC bouts are flyweight, and
   all eleven UFC bouts belonging to the other `Bruno Silva` are middleweight.

## Accepted limitations and clarifications

8. **The rank-context window reaches nothing published.** An earlier version of
   this register called it "live in the model fit". That was wrong, and the
   correction matters because it retires the item rather than answering it. The
   published fit takes one shared bout weight and the staged method score; the
   side-specific performance weights that carry `perf_factor_rank_context` are
   retired and say so in their own module. The window survives in exactly three
   places, none of them published: the retired performance-weight audit table,
   the diagnostic division résumé, and `public_legacy_rank_context_win_mass`,
   which is reported beside the all-time score and deliberately excluded from
   it. Its measured ceiling — the factor does nothing on 94.02% of 161,196
   appearances — was therefore a ceiling on an audit column. Changing the window
   cannot move a rating or a board, so do not budget a re-rate against it.
9. **About 11% of filled weight classes are wrong for that particular fight.**
   That is the price of the 2026-08-28 schedule repair, paid knowingly. The
   2026-09-03 four-neighbour vote cut it from 17%; event-page evidence retires
   the inference wherever a card can be read.
10. **Three close-date repeat cases are recorded, not guessed away.** Canonical
    UFC URLs establish Sakuraba against Silveira at UFC Ultimate Japan as a
    genuine same-night tournament rematch, so both fights remain distinct. Two
    non-UFC pairs recur one day apart in the `majors` source: Anthony Ruiz–Jaime
    Jara on 2004-06-02/03 and Mike Whitehead–Tim Sylvia on 2002-04-26/27. Both
    rows remain because their source names successive events and no available
    evidence establishes a duplicate. These are two possible extra rows among
    81,281 rated bouts; neither changes the contender-win count.
11. **The career contender-win count and the printed Elite-wins column are
    different measures** — whole career against best ten years — so they
    legitimately differ (Jones 16 against 12). They can also differ by one fight
    at the margin, because the résumé prices the opponent before the fight and
    the printed column reads the value at the event. Not a defect; do not
    "reconcile" them.
12. **Two third-party datasets are published without a redistribution
    licence, by the owner's decision of 2026-10-12.** The repository is public.
    It carries the 13 Fight Matrix ranking pages under
    `data/external/fightmatrix/html/` and the Sherdog-derived
    `data/external/sherdog/crossorg_bouts.parquet`. Each directory's
    `LICENSE.txt` records that no redistribution licence was identified, and
    Sherdog's terms (§4) restrict collating its content for use elsewhere.
    The data stays because it is the only copy of the crawl evidence behind the
    published boards; removing it would leave those boards unverifiable. This
    is a known rights risk, accepted, not a finding that redistribution is
    permitted. If either source objects, untrack the file; history rewriting is
    a separate decision.
13. **Weight-class boards are the All-time score split by where it was earned.**
    Shipped 2026-10-14 (`ratings/division_legacy.py`, `class_board.parquet`, the
    class tables in `RANKINGS.md`). Before this, every board was pound-for-pound,
    a fighter belonged to one career class, and the ten men who won titles in two
    classes (Jones, St-Pierre, Makhachev, Cormier, Topuria, Penn, Couture, Cejudo,
    Pereira, McGregor) were missing from the second. The diagnostic class score in
    `division_resume.parquet` gave a second order inside each class that
    disagreed with the All-time board: across the men's top fifteens, rank
    correlation 0.57 to 0.89, and a different #1 at featherweight and
    bantamweight.

    Each title win, contender win and career year is assigned to the class of its
    bout, and a class score is the All-time score over that class's evidence,
    with the board-wide normalisers. A fighter's class scores therefore sum to
    their All-time score, and `build_boards.py` refuses to publish if they do
    not; on 2026-08-13 the largest gap is 5e-13. Two terms need a stated
    allocation rule: a capped contender-win year is split pro rata, and a career
    year's credit is split by the share of that year's bouts in each class. Bouts
    at open weight or with no weight class count toward no class (a median 0% of
    a top-100 score, at most 11.5%). Within a class, Prime and Current keep the
    published order, renumbered; they are restrictions, not new scores.
14. **A career year is still measured against the bar of the fighter's career
    class, not the class fought in that year.** Open. It is the remaining
    inconsistency under item 13: a fighter who moved up is credited at the new
    weight against the old weight's field. Changing it moves published scores, so
    it is a score change, argued from mechanism and checked against the outside
    lists like any other; it was kept out of item 13 so that the class boards
    could ship without moving a published rank.

## Tested and refused — do not propose these again

**On the all-time score**

- **Removing the exposure factor.** Correlation with UFC fight count falls 0.483
  to 0.345, but fighters with no UFC record in the top 100 double, 5 to 9, and
  Patricio Freire returns to 14th. All three versions hold 37 listed fighters in
  the top 100, so the outside check cannot separate them.
- **A hard cut-off at the contender bar in the title résumé.** It zeroed the
  title component for 38 fighters with three or more title wins — Shevchenko 11
  to 0, Usman 6 to 0 — and put Matt Serra 50th all-time on a 7–7 record.
- **Splitting the quality résumé on title status.** Five versions; every one
  raised Freire and wrecked agreement with the outside lists. A dominant champion
  fights his best opponents for the belt, so the split pays perennial contenders
  instead.
- **Swapping the title résumé to fight-by-fight ratings.** Hughes 427.4 to 444.7,
  agreement 0.9149 across 245 fighters, median movement 20.7 points. It replaces
  the timing problem with a different one.
- **Putting the title bar on the division contender line.** St-Pierre's title
  résumé fell to 279 against Namajunas's 657, and Namajunas reached 9th all-time.

**On the title cliff, measured 2026-09-01, both refused**

- **Crediting a title-fight loss** at a quarter or half the win's weight drops the
  cliff 15 to 7 or 6 and moves Prochazka 139 to 129 or 121 — but raises Sean
  Strickland 20 to 19 to 17. Strickland is this project's named symptom of paying
  for exposure rather than contention, and the component retired the same day
  correlated +0.360 with elite *losses*. Paying for reaching a title fight and
  losing it is that component under a new name. Agreement with elite wins
  +0.013 / +0.018; with Prime −0.009 / −0.019.
- **Elite-win mass with belts as a multiplier** shows the largest numbers in the
  table — elite wins 0.730 to 0.816, Prime 0.632 to 0.767 — and they are
  circular. This version's title term *is* elite wins multiplied by rating above
  a bar, which is exactly what the acceptance statistics measure: it is scored
  against its own inputs. It also breaks the term it replaces. Matt Serra, a UFC
  champion, scores 0.0 while Neil Magny, who never fought for a title, scores
  50.2. And it counts the résumé twice.

All sixteen list intervals straddle zero for both shapes. The 100 Greatest is the
only list with real power, and both are flat to slightly negative on it.

**On the Prime board**

- **Ranking by rating alone** (Topuria on 5 wins above St-Pierre on 11),
  **by opponent strength ignoring results** (Roy Nelson at 0–10 above Khabib and
  St-Pierre), and **by evidence-discounted rating** (it flattens — Silva and
  Nemkov finish 1.2 points apart). Settled: elite-win mass.

**On the rating model**

- **Raising `WHR_VIRTUAL_GAMES`.** Refused twice. On the repaired data the
  predictive fit moved it *down*, 2.0 to 1.0.

**On method**

- **Using the outside lists to judge a small change.** Ten to thirty-four
  hand-picked names cannot settle a 54-Elo correction, and they could not
  separate the three exposure versions. Use them to catch a large reordering,
  never to choose a setting.
- **Choosing a setting on the accuracy check.** It is 24 events and 218 scored
  fights. Use it as a regression check. Ignore its betting-market row entirely:
  17 fights.

## Reporting a change

Report movement of the fighters under discussion plus Magny, Maia, Dariush and
Anthony Johnson; the count of top-100 fighters with a zero title component before
and after; agreement between the score and elite wins and between the score and
Prime; and agreement with all three outside lists, each with its confidence
interval and a statement of what that check can detect.

On the board published 2026-09-02, after the exposure change in item 4, those two
figures are **0.6453 and 0.5144**, with 13 of the top 100 scoring zero on the
title term. Agreement with the outside lists is ESPN 0.9152, FightMatrix 0.6824,
The 100 Greatest 0.6098, Tapology 0.5515.

Read the first two against the previous board's 0.6067 and 0.5629 only with the
population caveat below: those were measured over the previous top 100, and the
top 100 changed. The variant table in item 4 holds one population across all of
its arms and reads 0.6132 and 0.5678 for this same shipped board — that is the
number to compare arms on, and the pair above is the number to publish.

The exposure change moved the fighters this section names as follows: Prochazka
146 to 137, Strickland 20 to 17, Whittaker 51 to 49, Serra 70 unchanged, Dariush
75 unchanged, Usman 24 to 25, Johnson 50 to 51, Chandler 87 to 90, Maia 78 to 82,
Magny 136 to 139.

Do not compare any of these with the 0.722 and 0.637 this section used to quote.
Both are measured over a population held fixed across variants, and the
population changed: the preserved 2026-09-01 incumbent board those numbers came
from was swept in the lean pass, so the population is now the current top 100. A
number measured over a different set of fighters is a different number, not a
worse board. For the same reason, a variant comparison must hold one population
across all of its arms, which is why item 4's table reads 0.6132 and 0.5678 where
this section reads 0.6453 and 0.5144 for the same shipped board.

## Rebuild and verify

A score or board change reads the existing ratings — but it must **re-score the
snapshot first**. `build_boards.py` publishes the `public_legacy_*` columns
already stored in `ratings_current.parquet`; it does not recompute them. Skip the
first line below and the boards publish the old scores while the audit, which
does recompute, publishes the new ones, and the two silently disagree:

```text
python -m ratings.rate_snapshot --snapshot-dir data/snapshots/2026-08-13 --scope majors,pre_unified --career-only
python build_boards.py data/snapshots/2026-08-13 --scope majors,pre_unified --write-readme
python build_top100_audit.py data/snapshots/2026-08-13 --scope majors,pre_unified
python -m pytest -q
python -m ruff check .
```

`--career-only` re-scores against the persisted fit and refuses if the scope does
not match the fit that produced it, so it cannot quietly re-score one scope's
board from another scope's ratings.

A data or rating change needs the full path, and `rate_snapshot` takes about
fifteen minutes:

```text
python build_sherdog_careers.py --report-only
python -c "from loaders.majors_scope import stage_majors_scope; stage_majors_scope('data/snapshots/2026-08-13')"
python -m ratings.rate_snapshot --snapshot-dir data/snapshots/2026-08-13 --scope majors,pre_unified
```

then the board block above. Never hand-edit a generated table. After any change,
re-run the deviant-fighter audit and read `rating_run.json` before claiming
anything about the top of the board.
