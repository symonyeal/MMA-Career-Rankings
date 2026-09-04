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

   **What an unlabelled bout is worth is now settled.** Shipped 2026-09-02. 64.5%
   of rated bouts carry no promotion, and the rule this replaced read every one of
   them as the lowest tier, 0.20 — the same number a genuinely small show gets.
   An unlabelled bout is missing evidence, not evidence of a weak promotion, so it
   is now left out of the two averages, and the identified-bout factor is shrunk
   back toward the pooled mean of every identified bout by `n / (n + k)` with
   `k = 5` bouts. Reading unlabelled bouts at the floor is the `k -> inf` limit of
   that estimator with the floor as its prior; dropping them outright is `k = 0`,
   which reads a career identified on two bouts at those two bouts' level with
   full confidence.

   Measured on one fixed population against the shipped board:

   | unlabelled bout treated as | top 100 with no UFC bout | top 100 zero on titles | agreement, elite wins | agreement, Prime |
   |---|---:|---:|---:|---:|
   | lowest tier, 0.20 — the rule replaced | 2 | 14 | 0.6067 | 0.5629 |
   | left out, no shrinkage (`k = 0`) | 2 | 15 | 0.6075 | **0.5740** |
   | recognised regional, 0.42 | 2 | 14 | 0.6093 | 0.5732 |
   | left out, `k = 1` | 2 | 15 | 0.6094 | 0.5722 |
   | left out, `k = 3` | 2 | **13** | 0.6110 | 0.5707 |
   | **left out, `k = 5` — shipped** | **2** | **13** | **0.6132** | 0.5678 |
   | left out, `k = 10` | **3** | 12 | 0.6143 | 0.5628 |

   `k = 10` is the bound above: it breaks the failure that refuted removing
   exposure altogether on 2026-08-27, putting a third fighter with no UFC bout in
   the top 100. Every lighter arm holds that guard at 2.

   **The outside check could not detect any of this.** For the shipped arm,
   The 100 Greatest +0.0052 (p 0.36), FightMatrix +0.0090 (p 0.34), Tapology
   −0.0121 (p 0.64), ESPN unchanged. Every sign test across every arm came back
   p >= 0.23. This ships on mechanism, which is what a score change ships on, and
   no claim is made that the outside lists chose it.

   **Two corrections to what this item used to say.** The three-way table it
   carried was measured against the *pre-floor* board — baseline elite wins
   0.5911, Prime 0.5312 — so its numbers are not comparable with anything
   measured since, and they are replaced above rather than extended. On that
   pre-floor population, leaving unlabelled bouts out moved FightMatrix −0.0272
   (p 0.052); re-measured against the shipped board the same arm moves it
   +0.0050. The direction reversed with the population, which is why the earlier
   run cannot be read as evidence either way.

   **What the change does not fix.** Sean Strickland rises 20 to 17, and he is
   this project's named symptom of paying for exposure rather than contention.
   That movement is common to every arm that changes anything at all except the
   0.42 arm, so it does not separate the shipped rule from its alternatives — but
   it is not answered by it either. A career identified from a handful of bouts
   still receives an estimate rather than an admission that it cannot be told
   apart. Harness:
   `Claude Func Folder\ufc-rank-engine\py\exposure_unknown_shapes.py`;
   the shipped ledger is verified equal to the `shrink5` arm by
   `Claude Func Folder\ufc-rank-engine\py\verify_shrinkage_ship.py`.
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

**A win over a fighter returning from a long absence is priced lower.** Shipped
2026-09-03, in the ledgers, after the rating-layer version was built and
refused.

The rating charges age but cannot distinguish active time from idle time. Stipe
Miocic was 35 and active when Daniel Cormier fought him, then 42 and 44 months
out when Jon Jones did; the rating alone separates the Stipe Cormier beat from
the one Jones beat by 34 points, while the Jones win is priced 232 points below
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

## Remaining data work

7. **Four eligible fighter careers are still unmerged, and all four are identity
   failures.** Leonardo Mafra, Thiago Perpetuo, Marcos Vinicius and Ozzy Diaz
   have three or four UFC bouts each and no resolvable Sherdog id, so the corpus
   holds only their UFC record. Merged coverage is 1,821 of 1,825 eligible
   careers, 99.8%. Sherdog's fightfinder search cannot separate these names from
   other fighters carrying them, and the builder has no way to be handed an id:
   it uses ids that already appear in the corpus, or ids its own search finds.
   Fixing these four therefore means adding a hand-checked-id entry point, not
   crawling harder. `identity_overrides.csv` does not help — it maps a Sherdog
   *name* to a canonical name, which presupposes the page was already found.
   Four careers of 1,825 cannot move a published rank, which is why this is the
   point at which crawling stopped.

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
C:\Python314\python.exe -m ratings.rate_snapshot --snapshot-dir data/snapshots/2026-08-13 --scope majors,pre_unified --career-only
C:\Python314\python.exe build_boards.py data/snapshots/2026-08-13 --scope majors,pre_unified --write-readme
C:\Python314\python.exe build_top100_audit.py data/snapshots/2026-08-13 --scope majors,pre_unified
C:\Python314\python.exe -m pytest -q
C:\Python314\python.exe -m ruff check .
```

`--career-only` re-scores against the persisted fit and refuses if the scope does
not match the fit that produced it, so it cannot quietly re-score one scope's
board from another scope's ratings.

A data or rating change needs the full path, and `rate_snapshot` takes about
fifteen minutes:

```text
C:\Python314\python.exe build_sherdog_careers.py --report-only
C:\Python314\python.exe -c "from loaders.majors_scope import stage_majors_scope; stage_majors_scope('data/snapshots/2026-08-13')"
C:\Python314\python.exe -m ratings.rate_snapshot --snapshot-dir data/snapshots/2026-08-13 --scope majors,pre_unified
```

then the board block above. Never hand-edit a generated table. After any change,
re-run the deviant-fighter audit and read `rating_run.json` before claiming
anything about the top of the board.
