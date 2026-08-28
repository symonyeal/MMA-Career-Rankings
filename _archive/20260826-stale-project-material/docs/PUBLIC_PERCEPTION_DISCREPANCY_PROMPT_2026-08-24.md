# Public-perception discrepancy prompt

Use this as the next repair prompt. The current top 100 is internally coherent
but fails the common-sense MMA smell test. Do not defend it as "the model says
so." Treat every major disagreement with public perception as either a model
bug, a missing feature, a missing data-quality check, or a claim that must be
explained in plain English.

## Public anchors to compare against

Use at least these anchors before changing the model:

* Tapology fan-voted all-time list, checked 2026-08-24:
  https://www.tapology.com/rankings/top-ten-all-time-greatest-mma-and-ufc-fighters
  Top 10 shown by the source: GSP, Demetrious Johnson, Islam Makhachev, Jon
  Jones, Alexander Volkanovski, Daniel Cormier, Khabib Nurmagomedov, Anderson
  Silva, Ilia Topuria, Jose Aldo.
* ESPN men's MMA fighters of the 21st century, checked 2026-08-24:
  https://www.espn.com/mma/story/_/id/40588557/ranking-top-10-men-mma-fighters-2000
  Top 10: Jon Jones, GSP, Anderson Silva, Demetrious Johnson, Khabib, Fedor,
  Randy Couture, Chuck Liddell, BJ Penn, Kamaru Usman.
* The 100 Greatest MMA list, checked 2026-08-24:
  https://www.the100greatest.com/2025/02/14/the-100-greatest-mixed-martial-artists-of-all-time/
  It is not gospel, but it gives a complete external top 100 for discrepancy
  accounting.

Public perception is not the target function by itself. It is the guardrail. If
the model says something wildly different, the burden is on the model.

## Current model top 10 failure

Current top 10 from `data/model_tuning/top100-audit/top100_audit.csv`:

| Model rank | Fighter | Why this is a red flag |
|---:|---|---|
| 1 | Jon Jones | Fine. |
| 2 | Georges St-Pierre | Fine. |
| 3 | Fedor Emelianenko | Defensible. |
| 4 | Islam Makhachev | High but currently defensible against some public lists. |
| 5 | Daniel Cormier | Defensible. |
| 6 | Usman Nurmagomedov | Severe failure. Public all-time top-10 perception is not there; he has no UFC record and is being treated like a proven all-time great. |
| 7 | Yaroslav Amosov | Severe failure. Respected unbeaten/high-record fighter, not public top-10 all-time. |
| 8 | Josh Barnett | Severe failure. The 100 Greatest places him 72nd; model has him 8th. |
| 9 | Alexander Volkanovski | Fine. |
| 10 | Cristiane Justino | Mixed. Cyborg is an all-time women's great, but #10 mixed all-time must be explicitly justified against Nunes, Silva, DJ, Aldo, Stipe, etc. |

The top 10 should not contain Usman Nurmagomedov, Yaroslav Amosov, or Josh
Barnett unless the model can produce a human-readable argument stronger than
every mainstream GOAT list. It currently cannot.

## Severe overplacements to audit one by one

These fighters are ranked far above public perception, absent from common
all-time lists, or placed much higher than a complete external top-100 anchor.
For each name: inspect opponent quality, title/championship signal, promotion
strength, division strength, undefeated-record inflation, and whether the score
is mostly mean excess accumulated against a shallow field.

| Fighter | Model rank | Public anchor | Required audit question |
|---|---:|---|---|
| Usman Nurmagomedov | 6 | Not a mainstream mixed all-time top-10 name | Is Bellator/PFL lightweight connectivity overpromoting an undefeated record without a title-defense or schedule-strength penalty? |
| Yaroslav Amosov | 7 | Not a mainstream mixed all-time top-10 name | Is undefeated Bellator dominance being treated as equivalent to UFC/Pride championship dominance? |
| Josh Barnett | 8 | The 100 Greatest: 72 | Is the career-mass functional overpaying longevity and heavyweight era paths? |
| Cristiane Justino | 10 | Publicly elite, but usually women's GOAT tier rather than consensus mixed #10 | Is the women's field-size / opponent-depth adjustment missing? Why is she above Nunes? |
| A.J. McKee | 13 | Not in The 100 Greatest top 100 | Is a low-loss Bellator record getting too much credit from cross-org paths? |
| Patricio Freire | 14 | Publicly strong, but not consensus top 15 mixed | Does Bellator longevity overpower title/schedule context? |
| Vadim Nemkov | 16 | The 100 Greatest: 62 | Why is PFL/Bellator light-heavyweight success worth top-20 mixed all-time? |
| Johnny Eblen | 17 | Not in The 100 Greatest top 100 | Same Bellator undefeated/low-loss inflation pattern. |
| Kyoji Horiguchi | 21 | Not in The 100 Greatest top 100 | Is multi-promotion excellence too high relative to UFC/Pride championship legacy? |
| Sean Sherk | 22 | Not in The 100 Greatest top 100 | Is early lightweight field depth/schedule being mis-scaled? |
| Ryan Bader | 26 | The 100 Greatest: 63 | Is two-division Bellator success and name-value opponent age being overpaid? |
| Ben Askren | 28 | Not in The 100 Greatest top 100 | Is pre-UFC undefeated dominance not penalized enough for later UFC evidence? |
| Michael Page | 29 | Not in The 100 Greatest top 100 | Opponent-quality and highlight-record inflation likely. |
| Rajabali Shaidullaev | 30 | Not in public all-time top-100 perception | Prospect/active-record inflation. |
| Seika Izawa | 33 | Not in public mixed top-100 perception | Women's field-size and recency inflation. |
| Timur Khizriev | 36 | Not in public all-time top-100 perception | Prospect/active-record inflation. |
| Vladimir Matyushenko | 39 | Not in The 100 Greatest top 100 | Early-era graph position and longevity likely overpaid. |
| Phil Davis | 40 | The 100 Greatest: 64 | Probably high; audit name wins, losses to elite, Bellator paths. |
| Paulo Filho | 41 | Not in The 100 Greatest top 100 | Short peak/PRIDE-WEC bridge may be overpaid. |
| Andrey Koreshkov | 42 | Not in The 100 Greatest top 100 | Bellator longevity likely too high. |
| Ramazan Kuramagomedov | 45 | Not in public all-time top-100 perception | Prospect/active-record inflation. |
| Renato Sobral | 46 | Not in The 100 Greatest top 100 | Early-era and schedule-path inflation. |
| Benson Henderson | 48 | The 100 Greatest: 97 | Model is nearly 50 places high; audit career mass vs peak/title legacy. |
| Igor Vovchanchyn | 53 | Publicly important pioneer; placement may be defensible | Verify early tournament/opponent treatment rather than assume. |
| Jon Fitch | 56 | Not in The 100 Greatest top 100 | Strong contender career, but public top-60 all-time is dubious. |
| Gilbert Melendez | 58 | Not in The 100 Greatest top 100 | Strikeforce/WEC lightweight paths may be too generous. |
| Joseph Benavidez | 60 | Not in The 100 Greatest top 100 | Elite contender, no undisputed title; model may underweight titles. |
| Archie Colgan | 62 | Not in public all-time top-100 perception | Prospect/active-record inflation. |
| Vitaly Minakov | 65 | Not in The 100 Greatest top 100 | Undefeated/low-loss heavyweight inflation. |
| Pedro Rizzo | 67 | Not in The 100 Greatest top 100 | Early-heavyweight schedule scaling. |
| Tim Sylvia | 69 | Not in The 100 Greatest top 100 | UFC heavyweight title reign may justify top 100, but rank still needs audit. |
| Miguel Torres | 71 | Not in The 100 Greatest top 100 | WEC/bantamweight era treatment. |
| Shinya Aoki | 78 | Not in The 100 Greatest top 100 | Whole-career volume vs elite mixed all-time perception. |
| Diego Sanchez | 79 | Not in The 100 Greatest top 100 | Longevity/name recognition should not equal all-time rank. |
| Vitor Ribeiro | 81 | Not in The 100 Greatest top 100 | Short/older lightweight peak likely overpaid. |
| Vladyslav Rudniev | 85 | Not in public all-time top-100 perception | Prospect/active-record inflation. |
| Ricco Rodriguez | 88 | Not in The 100 Greatest top 100 | Early heavyweight title signal may be under/over depending feature choice. |
| Ronda Rousey | 90 | Publicly much higher as a greatness/impact fighter | If this is "best" only, say so; if "greatest", the model is missing impact. |
| Oleg Popov | 95 | Not in public all-time top-100 perception | Prospect/active-record inflation. |
| Patchy Mix | 97 | Not in The 100 Greatest top 100 | Active lower-weight Bellator/PFL inflation. |

## Severe underplacements or missing public names

These are the names a public reader expects to see much higher, or at least see
inside the top 100. For each, explain whether the model intentionally rejects
public perception or is missing a real signal.

| Fighter | Model rank | Public anchor | Required audit question |
|---|---:|---|---|
| Anderson Silva | 20 | Tapology: 8; ESPN: 3; The 100 Greatest: 3 | Why is one of the canonical GOAT candidates below multiple Bellator/PFL names? |
| Demetrious Johnson | 35 | Tapology: 2; ESPN: 4; The 100 Greatest: 24 | Does the model underweight title defenses and technical divisional dominance? |
| Jose Aldo | 18 | Tapology: 10; common top-10/15 perception | Still probably low relative to fan/expert perception. Audit featherweight/WEC treatment. |
| Stipe Miocic | 25 | The 100 Greatest: 9 | Heavyweight UFC title achievements are underweighted. |
| Kamaru Usman | 37 | ESPN: 10; The 100 Greatest: 16 | UFC welterweight title run is not receiving enough championship/defense credit. |
| Max Holloway | 66 | The 100 Greatest: 17 | Severe underplacement; volume against elite UFC opposition is under-rewarded. |
| Amanda Nunes | 77 | Public women's GOAT; should be compared directly with Cyborg | Model likely misses two-division title dominance and women's field context. |
| Charles Oliveira | 91 | The 100 Greatest: 34 | UFC lightweight elite wins/title run underweighted. |
| Dustin Poirier | 94 | The 100 Greatest: 35 | Elite lightweight schedule and wins underweighted. |
| Frankie Edgar | 96 | The 100 Greatest: 65 | Publicly respected champion/contender career, still too low. |
| BJ Penn | 99 | ESPN: 9; The 100 Greatest: 80 | Severe if the board claims greatness; model likely punishes late-career decline too much or ignores prime/context. |
| Randy Couture | Missing | ESPN: 7; The 100 Greatest: 31 | Missing top-100 public staple. Audit pre-unified/UFC title-era handling. |
| Henry Cejudo | Missing | The 100 Greatest: 26 | Two-division UFC champion absent. Title signal is missing or too weak. |
| Alex Pereira | Missing | The 100 Greatest: 11 | If current data includes 2026 names, Pereira missing is a major modern-era failure. |
| Israel Adesanya | Missing | The 100 Greatest: 12 | UFC middleweight title run absent from top 100 is not credible. |
| Conor McGregor | Missing | The 100 Greatest: 36 | If "greatest" includes impact, missing is impossible; if "best", document that exclusion. |
| Alistair Overeem | Missing | The 100 Greatest: 33 | Long elite heavyweight career missing. |
| Frank Shamrock | Missing | The 100 Greatest: 38 | Early all-time great absent. |
| Bas Rutten | Missing | The 100 Greatest: 54 | Early great absent. |
| Ken Shamrock | Missing | The 100 Greatest: 53 | Early great absent. |
| Robbie Lawler | Missing | The 100 Greatest: 98 | Borderline, but expected in many top-100 discussions. |
| Tony Ferguson | Missing | The 100 Greatest: 95 | Lightweight prime streak absent. |
| Tyron Woodley | Missing | The 100 Greatest: 81 | UFC welterweight champion absent. |
| Robert Whittaker | Missing | The 100 Greatest: 45 | Modern middleweight elite absent. |
| TJ Dillashaw | Missing | The 100 Greatest: 71 | Bantamweight title run absent. |
| Petr Yan | Missing | The 100 Greatest: 52 | Modern bantamweight elite absent. |
| Ilia Topuria | Missing | Tapology: 9; The 100 Greatest: 10 | If using future/current 2026 data, missing is inconsistent with public/current elite perception. |
| Leon Edwards | Missing | The 100 Greatest: 25 | UFC welterweight champion absent. |
| Dricus Du Plessis | Missing | The 100 Greatest: 15 | Current champion-era omission. |
| Tom Aspinall | Missing | The 100 Greatest: 100 | Borderline but should be investigated if the model elevates lower-public-profile heavyweights. |
| Alexandre Pantoja | Missing | The 100 Greatest: 29 | UFC flyweight champion absent. |
| Glover Teixeira | Missing | The 100 Greatest: 60 | Late-career UFC title signal absent. |

## Model defects this discrepancy pattern suggests

Audit these as hypotheses, not conclusions:

1. **Titles and title defenses are nearly invisible.** Public GOAT lists heavily
   weight championship reigns, multi-division belts, and long title-defense
   streaks. Current career mass mostly sees rating-above-bar over time.
2. **Opponent quality is too endogenous.** Whole-graph rating can promote a
   closed external ecosystem if its best fighters mostly beat each other and
   cross over through a few favorable paths.
3. **Undefeated and low-loss records are over-rewarded.** The model appears to
   prefer clean records in weaker or less-tested circuits over messy elite UFC
   resumes.
4. **Late-career decline may still erase public prime memory.** BJ Penn,
   Anderson Silva, Tony Ferguson, and others need explicit prime-vs-twilight
   handling if the public product is "greatest."
5. **Women's MMA is not calibrated as its own historical field.** Cyborg over
   Nunes is not impossible, but the model must handle field depth, era depth,
   and two-division title dominance explicitly.
6. **Promotion strength must be inferred but bounded.** "No organisation
   weight" is clean philosophically, but the current output says the bridge is
   strong enough to put Bellator/PFL names over UFC/Pride legends. That claim
   needs stress tests.
7. **The output label is confused: best, greatest, career value, or resume?**
   A model can disagree with fans, but the product cannot call itself a public
   top 100 if it ignores impact, titles, defenses, and divisional legacy.

## Required next output

The next pass must produce:

1. A table of all model top-100 names with columns:
   `model_rank`, `public_anchor_rank`, `delta`, `outlier_class`,
   `model_reason`, `public_reason`, `recommended_fix_or_explanation`.
2. A second table of public top-100 anchor names missing from the model top 100.
3. A top-25 sanity gate:
   * no more than two names absent from every mainstream/public top-100 anchor;
   * no external-only active fighter in the top 10 without a written
     schedule-strength defense;
   * Anderson Silva, Demetrious Johnson, Aldo, Stipe, Kamaru Usman, Max
     Holloway, Amanda Nunes, Charles Oliveira, and Dustin Poirier must each
     have a named explanation if placed below rank 40.
4. A model-change plan that separates:
   * data bugs;
   * missing features;
   * scoring-functional changes;
   * product-label changes.

Do not tune blindly until the top 10 "sounds right." The point is to explain
why the model thinks public perception is wrong, and then decide whether that
explanation is credible. Right now, for the biggest discrepancies, it is not.
