# Open decisions and settled ground

The one register. What is still wrong, what has already been tried and refused,
and the rules a change has to meet. Two separate registers were kept until
2026-09-01 and repeated six of seven refusals word for word; they are in
`_archive/20260901-lean-pass/docs/` with the analysis that produced them.

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

## Open

1. **Title pricing, not the cliff, is the case that is clearly wrong.** Jiri
   Prochazka sits at 139 and no weighting reaches him: 139 at achievement weight
   0.30, 140 at 0.50. Both his title wins are over opponents below their
   division's bar (Lawal 1679 against 1827, weight 0.008; Teixeira 1855 against
   1868, weight 0.054) while all three title losses are against opponents above
   it (0.229 / 0.215 / 0.206). His losses price at ten times his wins and the
   résumé counts only wins. On top of that, 19 of his 40 rated fights carry no
   promotion label and drop to the lowest tier factor of 0.20, giving him an
   exposure factor of 0.730 against a top-100 median of 0.87. Forcing that to 1.0
   moves him to 110. A former champion pricing at 0.008 is the defect; zero for
   someone who never won a title is what a championship term should say.
2. **The ratings themselves are the largest error, and nothing here fixes them.**
   Seika Izawa is rated 319 points above the best fighter she has ever faced;
   Khabib Nurmagomedov 206. Every board reads that error, and a higher bar reads
   it more sensitively, not less.
3. **A single upset can still climb.** Matt Serra moved 77 to 60 on one contender
   win, and keeps rising as the achievement weight rises — 60 / 49 / 43 / 40 at
   0.30 / 0.40 / 0.50 / 0.60. The weights are owner policy, but this is what
   raising the achievement weight buys.
4. **The promotion table is typed in by hand** and multiplies both quality
   components. It is not fitted to anything. A measurement on 2026-09-01 found no
   *further* promotion term is needed — after the +54 correction a UFC title win
   prices at 0.119 against Bellator's 0.059, difference +0.061, CI95 [+0.044,
   +0.078] — but the table itself was never justified.
5. **Two contender bars, not one.** The résumé uses the absolute contender line;
   the title résumé uses a division-year quantile. Unifying them was measured and
   reverted on 2026-08-26 for reasons that still hold: fix the rating first.
6. **`WHR_W2_PER_DAY` is an assumption, not a fitted value.** 0.0002 was measured
   and did not resolve.
7. **The rank-context window is live in the model fit, and its ceiling is small.**
   Across 161,196 appearances the factor does nothing on 94.02% and is the
   largest of four factors on 3.28%. The clip to fifteen places binds on 92.82%
   of rows with a known division size, and the division size is unknown on 47.64%
   of appearances, so the share rule cannot fire on nearly half the table at any
   value. Repairing it changes window membership on 2,830 rows and is the largest
   factor on 1,214 — 0.75% of appearances. Budget any re-rate against that.
8. **77 fighters are still truncated** because Sherdog's search could not resolve
   their name. The builder's report lists them. A name-matching problem, not a
   crawling one.
9. **About 17% of filled weight classes are wrong for that particular fight.**
   That is the price of the 2026-08-28 schedule repair, paid knowingly.
10. **Three duplicate-date pairs are recorded, not fixed.** One is a genuine
    same-night tournament pair (Sakuraba against Silveira, UFC Ultimate Japan).
    The other two sit inside the `majors` source with no UFC record on either
    side, so nothing says which date is right. Two rows in 80,896.
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
Prime, currently 0.722 and 0.637; and agreement with all three outside lists,
each with its confidence interval and a statement of what that check can detect.

## Rebuild and verify

A score or board change reads the existing ratings:

```text
C:\Python314\python.exe build_boards.py data/snapshots/2026-08-13 --scope majors,pre_unified --write-readme
C:\Python314\python.exe build_top100_audit.py data/snapshots/2026-08-13 --scope majors,pre_unified
C:\Python314\python.exe -m pytest -q
C:\Python314\python.exe -m ruff check .
```

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
