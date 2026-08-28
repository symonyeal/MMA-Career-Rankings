# Research Recommendations

This document turns the model-selection notes into concrete research tracks for
the UFC Rank Engine. The current production baseline remains event-period
Glicko-2 with `tau = 0.5`, strict canonical scoring, and method-only sleeves.

## 1. Calibrate `tau` Instead Of Guessing It

Recommendation: keep `tau = 0.5` as the production default, then backtest
`tau` values across a conservative range such as `0.30, 0.40, 0.50, 0.60,
0.70`.

Research idea: run rolling-origin backtests by event date. For each candidate
`tau`, predict each fight from pre-fight canonical ratings and record Brier
score, log loss, calibration slope/intercept, upset sensitivity, and rank
turnover after major events.

Decision rule: prefer the smallest `tau` whose predictive metrics are not
materially worse than the best candidate. That keeps the system resistant to
short hype cycles while allowing real skill changes to register.

## 2. Validate The Finish-Versus-Decision Score Gap

Recommendation: treat all finishes as one method rank at `1.00`, with decisions
in the narrow `0.82-0.86` band unless backtesting shows a better split.

Research idea: compare three method-score schedules:

- Flat method stream: all wins score `1.00`.
- Current schedule: finishes `1.00`, decisions `0.82-0.86`, DQ `0.70`.
- Aggressive schedule: finishes `1.00`, submissions/KO split, decisions lower.

Measure whether method scoring improves future win prediction or merely
reorders leaderboards in a way that over-rewards finish-heavy styles. Report
style bias by division and era, since heavyweight and flyweight finish rates
are structurally different.

## 3. Market-Odds Calibration And Upset Weighting

Recommendation: keep signed moneyline normalization as an audit-friendly
performance sleeve, not part of canonical ratings.

Research idea: compare the current signed-moneyline factor against probability
residual factors:

- Signed moneyline: largest plus-money winner maps to `1.15`, largest
  minus-money winner maps to `0.90`.
- Probability residual: actual outcome minus no-vig implied probability.
- Bucketed residual: underdog tiers, pick'em, and favorite tiers.

Evaluate by market bucket: favorites, small underdogs, large underdogs, title
fights, short-notice fights, and late-career fights. The risk to watch is
double-counting: odds already include public knowledge of injuries, age, and
recent form, so the sleeve should remain bounded.

## 4. Integrity Penalty Sensitivity

Recommendation: keep integrity penalties restricted to tainted wins. Do not
dampen PED-confirmed losses, because that makes the loss less punitive.

Research idea: produce alternate integrity streams with PED win factors of
`0.70, 0.80, 0.90`, DQ win factors of `0.85, 0.92, 1.00`, and missed-weight
win factors of `0.80, 0.88, 0.95`.

Evaluation should focus less on prediction and more on audit behavior:
affected fighters, rank deltas, whether repeated flags compound reasonably,
and whether the penalty remains explainable to a reader.

## 5. Activity-Weighted Volatility And Aging

Recommendation: model inactivity uncertainty more carefully before adopting a
full Kalman filter or Sequential Monte Carlo engine.

Research idea: replace the current month-count lazy inflation with an
activity-weighted function:

```text
phi_increase = base_inactivity(years_idle)
             * age_multiplier(age_at_return, division)
             * heavyweight_multiplier(weight_class)
             * recent_activity_multiplier(fights_last_24_months)
```

Start with deterministic multipliers, then compare against a Kalman-filter
prototype where latent skill drifts between fights. A useful test case is
older heavyweights after long layoffs versus young prospects after equivalent
layoffs.

## 6. Heavy-Tailed Upset Robustness

Recommendation: treat heavy-tailed or skewed-t likelihoods as an experimental
branch, not a production change.

Research idea: build a sidecar robust-rating prototype where the update
influence of extreme upsets is bounded by a Student-t style residual. Compare
the champion-collapse behavior after large underdog wins against the current
Glicko-2 update.

Success criteria: the robust model should reduce single-fight overreaction
without hiding genuine regime changes. Use historical cases with immediate
rematches or follow-up fights to test whether the damped update was justified.

## 7. OpenSkill And TrueSkill-Style Bayesian Graphs

Recommendation: consider OpenSkill or TrueSkill 2-style models only after
defining which extra observed variables belong in the graph.

Research idea: prototype a Bayesian graph with fighter skill, division era,
age, inactivity, short-notice status, betting market, and method-of-victory
nodes. Keep the output comparable to current `mu_canonical` and `phi_canonical`
so old and new systems can be evaluated side by side.

Potential benefit: covariates can explain why two wins with the same W/L result
should not move ratings equally. Main risk: the model becomes less transparent
and harder to audit.

## 8. Cross-Organization And FightMatrix Expansion

Recommendation: do not merge non-UFC bouts into canonical ratings until fighter
identity resolution and source confidence are stronger.

Research idea: create a staged external-strength stream using FightMatrix and
non-UFC fight histories. Keep it separate from canonical until cross-source
name matching, event chronology, and organization-strength priors are tested.

Useful outputs:

- UFC-only rank.
- External-adjusted rank.
- Rank delta and explanation.
- Source-confidence score.

## 9. State-Space Skill Model (Time-Varying Latent Skill)

**Status (2026-05-14): shipped and extended.** `ratings/whr.py` implements
Whole-History Rating (Coulom 2008) as a Bayesian smoother with a dynamic
Bradley-Terry likelihood and a Wiener-process skill prior. WHR is the
default headline ranking surface. Three sleeved variants
(`whr_integrity`, `whr_performance`, `whr_integrity_performance`) now also
run — the sleeve weight scales each fight's BT likelihood contribution; priors
are unweighted. WHR is substantially more resistant to sleeve amplification
than Glicko-2 (max delta +19 mu vs hundreds of mu on Glicko-2 sleeved).
Open follow-ups: (a) tune `WHR_W2_PER_DAY` by predictive backtest; (b) the
heavier Kalman / SMC / OU variants remain unbuilt; (c) WHR vs Glicko-2
Brier/log-loss comparison not yet run.

Recommendation: prototype a state-space rating model as a sidecar to the
production canonical Glicko-2 stream; do not replace canonical until the
sidecar's calibration and audit story is at parity.

Research idea: model fighter skill as a latent time-varying process. The
observed fight outcome (and method) is a noisy projection of the latent
skill difference. Inference candidates, in order of increasing complexity:

- Kalman filter with locally linear skill drift, Gaussian observation noise.
- Sequential Monte Carlo / particle filter when likelihood is heavy-tailed
  or when uncertainty should fan out smoothly during long layoffs.
- Continuous-time state-space (Ornstein-Uhlenbeck drift) so calendar time
  matters, not just the next bout's index.

This is the most natural fix for two-related concerns: inactive heavyweights
re-emerging years later, and young prospects whose true skill is moving
fast. The Glicko-2 mechanism collapses both into a single `phi` inflation
parameter; a state-space model can parameterize them separately. Reference:
arXiv 2308.02414, JRSS-C 73(5) 2024.

Success criteria: improved Brier/log-loss over Glicko-2 specifically on
post-layoff fights and on the first 5 UFC bouts of debuting prospects; no
regression on the broader test set.

## 10. Continuous Decisiveness Scoring

Recommendation: replace the current "dominance + finish-speed + 5-round"
trio with a single calibrated decisiveness score before the method-stream
re-tunes again.

Research idea: define a continuous decisiveness score `d ∈ [0, 1]` per
result:

- First-round KO/sub > later finish > unanimous decision sweep > unanimous
  decision narrow > majority decision > split decision.
- Inputs: method, end round, end seconds within round, scheduled rounds,
  scorecard margin.
- Calibrate so the score's mean predicts the next-fight win probability of
  the winner against opponents of comparable rating.

The current sleeve gives dominance + finish-speed + 5-round amplitudes
0.06 + 0.04 + 0.04 = 0.14. The decisiveness score should fold these into a
single ≤ 0.14 amplitude and avoid the current saturation where every KO
trips the dominance ceiling on the dominance factor.

## 11. Heavy-Tailed Upset Robustness

(Building on §6 above.) Beyond the rank-gated upset factor in the production
sleeve, the canonical stream still uses a Gaussian-like Glicko-2 update that
overreacts to a single fluke KO. A robust-rating prototype with a Student-t
residual or Huber-style influence function would damp the single-fight
overreaction without changing the population behavior.

## 12. Hierarchical / Informative Priors For Cross-Org Imports

(Building on §8 above.) Once non-UFC fight histories are loaded, the debut
UFC fighter should not start at the same 1500/350 prior as everyone else.
Build a hierarchical model where the prior on debut skill draws from the
feeder organization's strength distribution. Useful covariates:

- Feeder organization (Bellator, ONE, PFL, Pride, regional).
- Pre-UFC record and title status in feeder.
- Opponent quality in feeder, propagated via the same skill-rating engine
  on the feeder graph.

Blocked on data: cross-organization fight history with verified fighter
identity. See `SOURCE_MATRIX.md`.

## Suggested Research Order

1. Run `tau` and method-score backtests.
2. Validate odds sleeve variants and integrity penalty sensitivity.
3. Fix activity/inactivity decay with deterministic age/division multipliers.
4. Prototype heavy-tailed robustness (§6 / §11).
5. Prototype state-space sidecar (§9) and continuous decisiveness score
   (§10).
6. Prototype OpenSkill/TrueSkill-style graph only after the simpler
   experiments have clear benchmark results.
7. Hierarchical priors for cross-org imports (§12) — gated on feeder-org
   ingestion.
