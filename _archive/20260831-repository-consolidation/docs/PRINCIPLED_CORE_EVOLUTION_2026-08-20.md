# Principled core evolution — 2026-08-20

> **Historical design record.** The decision and implementation table below
> describe the 2026-08-20 state. Later work made the whole-sport scope and
> Public Legacy Score the live defaults, and retired the public Peak output.
> Use the repository `README.md` and
> [Rating layer and ledger](RATING_LAYER_AND_LEDGER_2026-08-28.md) for the
> current contract.
>
> **Amended 2026-08-28.** The line below that neither estimator "receives a
> second credit for title labels, rankings, streaks, opponent quality, or the
> same bout's method" is still true for the first four and is **no longer true
> for method**. Method of victory is now the winner's score `y_b` itself, which
> is not a second credit but a change to what the single posting says: it was
> measured at -0.00332 calibrated held-out log loss [-0.00503, -0.00161], with a
> mean-matched constant score as the control scoring nothing. The *precision*
> route for method, and for title and five-round status, was measured at the
> same time and failed.

## Decision

The production engine is now one small skill model with two temporal views of
the same W/L/D evidence:

- **Canonical** is the causal Glicko-2 filter used for a fighter's state before
  the next bout.
- **WHR** is the retrospective smoother used to compare complete careers.
- **Symon Career Skill Mass** was the public career functional over the
  era-neutral WHR trajectory at this stage. Prime was a fixed-window diagnostic;
  the separate Peak output was later retired as redundant.

Method, dominance, title status, opponent rank, market odds, integrity policy,
and data completeness no longer accumulate inside the public skill number.
They remain diagnostics or separately labelled boards. This is a reduction in
claims as well as code: the core estimates skill from results; the other layers
answer different questions.

## Implementation status

| Status | Change | Repository contract |
| --- | --- | --- |
| Fixed | Reciprocal forecasts use both fighters' uncertainty | [`predict_win_prob_from_ratings`](../ratings/glicko2_engine.py) uses the root-sum-square of the two rating deviations; swapping fighters complements the probability. |
| Fixed | Pure binary core | Canonical Glicko and base WHR consume only win, loss, or draw in production. A WHR fractional winner score is inert unless its column is explicitly requested in [`run_whr`](../ratings/whr.py). |
| Fixed | One WHR likelihood weight per bout | WHR repeats one positive scalar on the paired appearances and rejects unequal `weight_a`/`weight_b`. |
| Fixed | Sleeves retired from production and public ranking | The side-specific integrity/performance Glicko and WHR passes are gone from [`rate_snapshot`](../ratings/rate_snapshot.py); rebuilds remove their stale history artifacts. |
| Fixed | Era-neutral default | No era premium is applied to the WHR history that feeds Career Skill Mass. Old era helpers and legacy period columns are compatibility code, not the public core. |
| Fixed | Cross-organization data quarantined | Production rating is UFC-only. A staged `crossorg_fights.parquet` is ignored unless `include_experimental_crossorg=True` is explicitly supplied. |
| Fixed | Drawn title bouts preserve lineage | Missing or invalid winners cannot replace or vacate the incumbent in [`prefight_ranking_context`](../ratings/performance_adjustment.py). |
| Fixed | Career, Prime, and Peak have explicit units and gates | Their definitions live in [`symon_score.py`](../ratings/symon_score.py) and are attached by the snapshot builder. |
| Fixed | Policy and coverage are separate outputs | [`build_boards.py`](../build_boards.py) emits an integrity ledger, a direct-debit integrity board, and a completeness-gated board without changing latent skill. |
| Unresolved | Predictive evidence must be regenerated | Existing prequential scores were produced with the old forecast equation and confounded variants. They are not evidence for the new core. |
| Unresolved | Cross-org reliability needs a causal definition | The existing bridge weights use eventual UFC careers and whole-graph opponent information. Cross-org predictive claims remain quarantined until weights are outcome-independent or recomputed inside every historical fold. |
| Resolved | Public rank uncertainty | [`ratings/uncertainty.py`](../ratings/uncertainty.py) refits the smoother under Dirichlet-reweighted events and recomputes the career functional; `build_uncertainty.py` persists the intervals. See [Prior Mass and Uncertainty](PRIOR_MASS_AND_UNCERTAINTY_2026-08-20.md). |
| Superseded | "Legacy period columns remain for compatibility" | The rolling opponent-quality period scores were retired outright, not kept: they scored opponent quality, titles, activity and era a second time. |
| Corrected | Prior specification | The anchor prior was applied once per appearance, so its mass grew with career length and an undefeated record stopped climbing at a constant independent of the evidence. Prior mass is now fixed per fighter, plus virtual games. |

## One outcome model, two temporal estimators

For bout $b$, let $y_b\in\{0,\tfrac12,1\}$ be fighter $i$'s result against
fighter $j$, and let $d_b=\theta_i(t_b)-\theta_j(t_b)$. A coherent weighted
Bradley--Terry contribution is

\[
\ell_b=\omega_b\left[y_b\log\sigma(d_b)
 +(1-y_b)\log\sigma(-d_b)\right],
\qquad \sigma(x)=\frac{1}{1+e^{-x}}.
\]

The reliability $\omega_b>0$ belongs to the **bout likelihood**, so it is the
same for both paired appearances. Giving the winner weight $\omega_{bi}$ and
the loser a different weight $\omega_{bj}$ makes the two score gradients
non-opposite; they can no longer be the derivative of one joint bout
likelihood. That is why `whr_integrity_performance` and its sibling sleeves
were not merely simplified but retired.

At the UFC production scope, $\omega_b=1$. Canonical Glicko and WHR therefore
share the same pure result evidence and reciprocal pairwise-logit contract.
They are deliberately different estimators:

- Glicko-2 filters forward and carries a rating deviation and volatility.
- WHR smooths the whole observed trajectory with a Gaussian random-walk prior,
  schematically

\[
\theta_{i,k+1}-\theta_{i,k}
  \sim \mathcal N(0,w^2\Delta t_{i,k}).
\]

The filter is appropriate for a prediction made at time $t$; the smoother is
appropriate for retrospective career description. Neither receives a second
credit for title labels, rankings, streaks, opponent quality, or the same bout's
method.

This use of established models follows the official [Glicko technical
paper](https://www.glicko.net/glicko/glicko.pdf) and Remi Coulom's
[Whole-History Rating](https://www.remi-coulom.fr/WHR/). The project-specific
contribution is the estimand and product contract below, not a claim to have
invented either estimator.

### Reciprocal forecast

On the internal Glicko scale, define

\[
\phi_* = \sqrt{\phi_i^2+\phi_j^2},\qquad
g(\phi_*)=\left(1+\frac{3\phi_*^2}{\pi^2}\right)^{-1/2},
\]

\[
P(i>j)=\sigma\!\left(g(\phi_*)(\mu_i-\mu_j)\right).
\]

Both uncertainty terms now enter symmetrically. Consequently
$P(i>j)+P(j>i)=1$, equal ratings imply $0.5$, and increasing joint
uncertainty moves a non-even forecast toward $0.5$. These metamorphic
properties are pinned in [`test_glickman_example.py`](../tests/test_glickman_example.py).

## Public career functional

For fighter $i$ and calendar year $a$, average the fighter's qualifying WHR
appearance ratings:

\[
\bar\theta_{ia}=\frac{1}{n_{ia}}
\sum_{k:\,\operatorname{year}(t_{ik})=a}\theta_{ik}.
\]

Let $m_a$ be the mean of those fighter-year means across the contemporaneous
field, counting each fighter once in that year. A year with fewer than five
qualifying fighters falls back to the global qualifying fighter-year mean. The
Career Skill Mass is

\[
C_i=\sum_{a\in A_i}\left[\bar\theta_{ia}-m_a\right]_+,
\qquad [x]_+=\max(x,0).
\]

The default annual gate is one observed appearance. Each active calendar year
can contribute once, so six bouts in a year do not create six units of career
credit. Extra appearances can improve the annual mean's evidence, but cannot
pad the number of terms. $C_i$ is measured in **rating-point-years** (a sum of
one rating-point excess per yearly unit), not Glicko points and not a win
probability. Its audit columns expose active years, positive-contribution years,
peak annual excess, and first/last qualifying year.

This functional rewards sustained superiority relative to the field actually
present while avoiding title bonuses, fight-volume multiplication, and a
hand-tuned era slope. It does not prove that fields from different eras are
identical; it states the comparison being made.

### Fixed Prime and Peak diagnostics

Prime and Peak search only fixed spans over actual appearances:

\[
R_i(W,K)=\max_{I:\,\operatorname{span}(I)\le W,\ |I|\ge K}
\frac{1}{|I|}\sum_{k\in I}\theta_{ik}.
\]

- **Prime:** $W=3652$ days and $K=13$ appearances.
- **Peak:** $W=1826$ days and $K=8$ appearances.

The selected raw mean is empirical-Bayes shrunk toward the cohort mean:

\[
S_i=\bar R+B_i(R_i-\bar R),\qquad
B_i=\frac{\tau^2}{\tau^2+s_i^2},
\]

where $s_i^2$ is the selected window's mean-sampling variance and
$\tau^2=\max(0,\operatorname{Var}(R)-\operatorname{mean}(s^2))$. These are
diagnostics for a best sustained period. They do not override Career Skill
Mass, and their fixed horizons prevent the notebook from turning window choice
into rank shopping.

## Era, integrity, and completeness are not latent skill

A common era term cannot be learned from same-era bout outcomes:

\[
(\theta_i+\eta_a)-(\theta_j+\eta_a)=\theta_i-\theta_j.
\]

An era premium is therefore a normative scenario, not an identified model
parameter. The production default is zero. Any future era sensitivity must be
labelled as such and reported beside, never silently inside, the neutral board.

Integrity is also a policy judgement. The integrity ledger identifies every
discounted result and its reason; the direct-debit board applies an explicit
cost to a base-WHR point score. That debit is not subtracted from Career Skill
Mass because rating points and rating-point-years are different units.
Completeness is an abstention rule: fighters below the evidence floor remain
visible but unranked instead of being assigned a plausible-looking default
seat.

## Evidence boundary and next proof

[`compute_fight_weights`](../loaders/sherdog_loader.py) currently derives a
historical non-UFC bout's weight from participants' eventual full-career UFC
ratings, with one-hop inference over the completed cross-org graph. That uses
information unavailable at the bout date. Selection controls do not repair the
leak, and a rolling-origin harness that reuses the persisted weight also leaks.
The artifact is useful for exploration only.

Before making any performance claim, the project must:

1. bump or invalidate the prequential cache schema;
2. regenerate rolling-origin predictions after the reciprocal forecast fix;
3. compare pure UFC-only canonical Glicko and pure UFC-only WHR under the same
   W/L/D evidence contract;
4. report log loss, Brier score, calibration, paired event-level uncertainty,
   scope, dates, and sample counts; and
5. test any future cross-org design only with outcome-independent weights or
   weights fitted inside each training fold.

Until that run exists, this evolution is justified by coherence, auditability,
and reduced degrees of freedom—not by a claimed held-out lift.

WHR's optional `return_variance` is likewise not a rank interval. The current
calculation inverts each fighter's temporal Hessian block while holding every
opponent trajectory fixed. The joint Hessian has cross-fighter likelihood
terms, so a block inverse is not the corresponding block of the full inverse.
Public uncertainty needs either a sparse joint-Hessian/Laplace calculation or
an event-cluster bootstrap that reruns the estimator and career functional.

## Why this is distinct

The engine is not distinct because Glicko, Bradley--Terry, WHR, or empirical
Bayes are new mathematics. It is distinct because their composition follows a
strict separation of estimands:

- one result likelihood, viewed causally and retrospectively;
- one public career aggregate with at most one field-relative contribution per
  year;
- fixed Prime and Peak diagnostics instead of adjustable headline windows;
- integrity debits and completeness abstention as explicit product policy; and
- external ranks and cross-org assumptions used for validation or labelled
  research, never as hidden ingredients in the score being validated.

That makes the platform individual without becoming arbitrary: every term has
one job, one unit, and one place where it may affect the result.
