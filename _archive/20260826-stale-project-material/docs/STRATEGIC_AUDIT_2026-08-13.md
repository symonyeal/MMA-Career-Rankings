# Strategic audit — 2026-08-13

## Outcome

The main top-30 problem was not one bad fighter constant. The product was
presenting a best-window Glicko skill estimate as its default all-time list,
while the more suitable whole-history estimator was a secondary lens. The
notebook now defaults to **All-time + Prime**, calls the forward Glicko view
**Skill peak**, and puts an external all-time disagreement chart directly below
the leaderboard.

The data was refreshed through UFC Fight Night: Gamrot vs. Salkilld: 754
events, 8,479 rated fights, and 2,554 fighters. FightMatrix's all-time absolute
table is now a separately persisted reference artifact. It is diagnostic only;
it never enters the rating calculation.

## Why the old top 30 looked anomalous

1. **Question/estimator mismatch.** A forward-only filter permanently banks a
   fighter's best run. This explains high Skill-peak placements for Chris
   Weidman, Benson Henderson, and Junior dos Santos even when a broad greatness
   discussion would price career decline or longevity differently.
2. **Source-scope mismatch.** The standard snapshot is UFC-only, while common
   MMA greatness lists include WEC, PRIDE, Strikeforce, and ONE. Jose Aldo, BJ
   Penn, Matt Hughes, and other older careers therefore do not line up cleanly
   with whole-career references.
3. **Era premium too strong.** The WHR curve inherited 100% of the Glicko
   year-mean rise. That rise can contain genuine field depth, but also rating
   system and roster-composition effects. It pushed short modern title runs too
   far above older complete careers.
4. **Title-effective eligibility.** A title-dense career can qualify below the
   nominal 13-fight Prime floor. This is defensible, but it is why Alex Pereira
   can rank with far longer careers and must be surfaced as a high-uncertainty
   placement rather than treated as an ordinary 10-year résumé.
5. **Résumé bonus saturation.** The headline add-on can reach 180 points, and
   many established greats hit the cap. The raw and headline columns remain
   available, but the notebook should next expose their decomposition per
   fighter so users can see whether rating, opposition, or title mass drove a
   placement.

## Era-premium sensitivity

The premium was re-run at five strengths. Agreement is Spearman correlation
against matched names in the FightMatrix all-time top 35; mean absolute gap is
in rank places. This is an external sanity check, not a fitting target.

| Strength | Spearman | Mean absolute gap | Read |
|--:|--:|--:|---|
| 0.00 | 0.73 | 4.81 | Best gap, but asserts no modern-depth effect. |
| 0.25 | **0.74** | 5.09 | Best rank-order agreement while retaining the era shape. |
| 0.50 | 0.74 | 5.05 | Similar, but more recency pressure. |
| 0.75 | 0.72 | 5.36 | Modern careers begin crowding out older greats. |
| 1.00 | 0.60 | 5.62 | Full transfer materially overstates recency. |

`WHR_ERA_PREMIUM_STRENGTH` is therefore 0.25. The change is based on an
ablation, not on manually moving individual fighters.

## Notebook changes

- Default: All-time + Prime, top 30.
- Public labels now describe the question: Wins, Skill peak, All-time.
- External all-time dumbbell chart appears immediately after the leaderboard.
- Model Tuning moved below the audit trail, so users see evidence before knobs.
- Tuning recomputes use `data/model_tuning/` instead of a disappearing system
  temp directory.
- The historical four-board table remains collapsed in the README for audit
  history; the current recommended board is shown first.

## Next priorities

1. **Make source scope a first-class product choice.** Build and maintain a
   licensed, reproducible whole-career snapshot. Until then, label every
   headline board UFC-only and keep cross-organization comparisons diagnostic.
2. **Add uncertainty to all-time ranks.** Bootstrap bouts and reasonable model
   constants, then show rank bands. A fighter whose plausible interval is
   #5–#18 should not be displayed with false single-rank precision.
3. **Decompose the headline score.** Show raw WHR, opposition/title mass,
   résumé bonus, era adjustment, and integrity/performance sleeve side by side.
4. **Validate with multiple references.** Add at least one fan/expert consensus
   list with compatible licensing and keep FightMatrix separate. Do not tune to
   one external list.
5. **Automate freshness.** The live UFCStats incremental scraper works; add a
   scheduled refresh check, snapshot manifest diff, and a hard failure when the
   newest completed event is missing.
6. **Prune the dashboard.** Keep the opening narrative to Rankings → Sanity
   Check → Résumé/Rating → Career Arcs. Move specialist diagnostics into a
   clearly marked analysis appendix.
