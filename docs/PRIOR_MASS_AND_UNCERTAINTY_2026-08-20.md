# Prior mass, retired period scores, and honest rank intervals — 2026-08-20

Second pass over the core, continuing
[Principled Core Evolution](PRINCIPLED_CORE_EVOLUTION_2026-08-20.md). That
document reorganised the estimands. This one reports a defect found by
interrogating the fighters the board placed oddly, removes the last duplicated
scoring machinery, and closes the "public rank uncertainty" item it left open.

## 1. The defect: prior mass scaled with career length

### How it was found

The career board placed Movsar Evloev sixth and Shavkat Rakhmonov ninth, ahead
of several champions. Reading their actual bouts rather than their scores:

| Fighter | UFC record | Best opponent beaten (WHR at the time) | Own rating |
| --- | --- | --- | --- |
| Movsar Evloev | 10-0, all decisions | Aljamain Sterling, 1617 | 1689 → 1713 |
| Shavkat Rakhmonov | 7-0 | Ian Machado Garry, 1662 | 1696 from his **debut** year |

Both sat 70–270 points above every opponent they had ever faced, and Rakhmonov
held ~1696 after a single bout against a 1468-rated opponent. That is not a
résumé being over-credited; it is a rating that never had to be earned.

### The mechanism

An undefeated fighter has no interior maximum-likelihood rating. The
Bradley–Terry gradient

$$\sum_j \left(1-\sigma(r-r_j)\right)$$

is positive at every finite $r$, so the prior alone decides where the climb
stops. The prior was a Gaussian anchor applied **once per appearance**. Its mass
therefore grew with career length at exactly the same rate as the likelihood,
and the equilibrium condition collapsed to a per-appearance balance

$$1-\sigma(r-\bar r_{\text{opp}}) = \frac{r}{\text{prior\_var}},$$

whose solution does not contain $k$, the number of bouts. The stopping point was
a constant independent of both the amount and the quality of the evidence.

### Measured on the full database, before the fix

- 110 undefeated fighters; the 56 at **1-0 averaged 1646**, above the 98th
  percentile of all 2,554 rated fighters.
- The **highest rating in the entire database (1726) belonged to Maiquel
  Falcao**, who has one UFC bout.
- Going from 1-0 to 10-0 moved the average undefeated rating from 1646 to 1713 —
  nine additional wins bought 67 points.
- This was not an iteration artifact. Re-running the smoother at 50, 100, 200,
  400 and 800 coordinate-ascent passes moved every fighter by **0.0** points:
  the estimator had converged to exactly this MAP.

### The fix

Both priors now carry a **fixed mass per fighter**, spread across that fighter's
appearances:

1. the Gaussian anchor is divided by the fighter's appearance count, and
2. `WHR_VIRTUAL_GAMES` bouts of prior evidence are added against an average
   opponent, half won and half lost — Coulom's own remedy in the WHR paper.

Virtual games are logistic rather than quadratic, so they saturate: they bound
an unbeaten record without over-shrinking a genuinely dominant one. For $k$ wins
over average opposition the equilibrium becomes

$$\sigma(r)=\frac{k+v/2}{k+v},$$

which rises with the evidence, as a rating must.

### Measured after the fix

| $v$ | mean percentile of a 1-0 fighter | of a 3-0 fighter | of a 7+-0 fighter | rating gap, 1-0 → 10-0 | top-rated fighter |
| --- | --- | --- | --- | --- | --- |
| 0 | 0.838 | 0.942 | 0.995 | 443 | Jon Jones |
| 1 | 0.826 | 0.937 | 0.994 | 375 | Jon Jones |
| 2 | 0.821 | 0.934 | 0.994 | 321 | Jon Jones |
| 4 | 0.817 | 0.930 | 0.993 | 249 | Jon Jones |
| 6 | 0.816 | 0.927 | 0.992 | 204 | Jon Jones |
| 10 | 0.816 | 0.924 | 0.991 | 151 | Jon Jones |

Note which change did the work: the top of the board is repaired at $v=0$,
because dividing the anchor by appearance count is already enough to restore the
dependence on $k$. The virtual-game mass then controls how large the unbeaten
premium is allowed to be.

### Selecting $v$: measured, and unresolved

`virtual_games` is now a first-class field on the prequential `Variant` (cache
schema bumped to 4, since every previously cached WHR fold predates the prior
change). Rolling-origin evaluation over **60 held-out events, 406 decided
bouts** (2025-03-15 to 2026-08-08), calibrated:

| $v$ | log loss | Brier | accuracy | AUC | calibration error |
| --- | --- | --- | --- | --- | --- |
| 0 | 0.65496 | 0.23152 | 0.594 | 0.652 | 0.033 |
| **2** | **0.65192** | **0.22990** | 0.611 | 0.663 | 0.043 |
| 4 | 0.65379 | 0.23076 | 0.638 | 0.664 | 0.051 |
| 6 | 0.65646 | 0.23207 | 0.631 | 0.659 | 0.061 |
| 10 | 0.66119 | 0.23439 | 0.626 | 0.650 | 0.055 |

Paired event-level deltas against $v=0$, log loss, 95% intervals:

| challenger | delta | interval | verdict |
| --- | --- | --- | --- |
| $v=2$ | -0.00303 | [-0.01191, 0.00518] | unresolved |
| $v=4$ | -0.00117 | [-0.01486, 0.01139] | unresolved |
| $v=6$ | +0.00151 | [-0.01507, 0.01747] | unresolved |
| $v=10$ | +0.00623 | [-0.01391, 0.02598] | unresolved |

**Every interval crosses zero.** Held-out prediction does not resolve this
parameter at this sample size, and the metrics disagree at the point-estimate
level anyway: $v=2$ wins log loss and Brier, $v=4$ wins accuracy and AUC, $v=0$
wins calibration error. No accuracy claim is made for the shipped value.

Production ships $v=2$ on a stated tie-break: **the smallest prior mass that
wins the point estimate**. Prior mass is an assumption rather than evidence, so
the least of it that bounds the pathology is preferred. This is a choice under
an unresolved comparison, recorded as such.

## 2. Retired: the rolling opponent-quality period scores

`ratings/peaks.py` produced `sustained_peak_*` and `five_year_peak_*` for three
streams, each in a raw and a "headline" proven-résumé variant. Those columns
added, on top of a latent rating that already reflects results: an
opponent-quality weight per appearance, a title-fight weight multiplier, a
win-context bonus, a title-ladder mass, an activity bonus, an era/division
normaliser, and a capped résumé bonus — roughly twenty hand-set constants
scoring the same evidence a second time.

They are gone. The module is now `ratings/appearance_context.py` and keeps only
what the **division résumé boards** need, which answer a different question
(how a fighter did *inside one weight class*). The public period views are the
fixed windows in `ratings/symon_score.py`. The notebook's old adjustable-window
control and its three helpers went too: they were a second period-scoring path
with no remaining caller. Sixteen functions, thirteen constants, one
era-normalisation subsystem and about 600 lines of engine code went with them.

## 3. Rank uncertainty: Dirichlet-reweighted events

`ratings/uncertainty.py` refits the whole smoother under perturbed event weights
and recomputes the career functional, so the published interval is the
estimator's own variability under reweighted evidence.

The weights are Dirichlet(1,…,1) scaled to mean one — the Bayesian bootstrap.
The more familiar cluster bootstrap (drawing events with replacement) was tried
first and is **wrong for this statistic**: career skill mass is a sum over years,
a with-replacement draw omits ~37% of events, whole fighter-years vanish, and
every replicate lands below the point estimate. Measured on the first
implementation, Jon Jones's point estimate of 7859 sat entirely outside its own
bootstrap interval of [5204, 6261]. Under Dirichlet weights the total evidence
is constant, every fighter survives every replicate, and the point estimate
returns to the middle of its interval.

The reporting rule is that overlapping intervals are not a ranking.
`rank_is_separated` states it in code.

### What the first full run says about the board

150 replicates over the 8,479-bout snapshot, 95% intervals:

| Fighter | mass | rank | interval | mass sd |
| --- | --- | --- | --- | --- |
| Jon Jones | 6973 | 1 | [1, 2] | 747 |
| Islam Makhachev | 4558 | 2 | [2, 20] | 700 |
| Alexander Volkanovski | 4544 | 3 | [2, 21] | 656 |
| Georges St-Pierre | 4457 | 4 | [2, 20] | 715 |
| Max Holloway | 4432 | 5 | [2, 25] | 791 |
| Charles Oliveira | 3850 | 7 | [2, 43] | 823 |
| Robert Whittaker | 3433 | 13 | [2, 79] | 924 |
| Jose Aldo | 3003 | 16 | [6, 115] | 725 |

Median rank-interval width across the top 50 is **102 places**. Only Jon Jones
is separated from the field, and `rank_is_separated` returns false for every
pair inside the top twenty — including first against eighth, because Poirier's
interval reaches rank 2.

That is a finding about the functional, not a defect in the bootstrap: at the
field-mean bar the masses of ranks 2–15 sit inside roughly one standard
deviation of each other, which is exactly what a score that reduces to *years ×
excess* should do when careers of similar length are compared. **The board
should be read as "Jon Jones, then a large tied group."** Publishing 1 through
25 as an ordering would be claiming precision the evidence does not contain.

### Does a higher bar produce a better-identified board? No.

The natural intuition — that raising the bar sharpens the ranking by keeping
only decisive seasons — is wrong, and the same bootstrap says so. Repeating the
150-replicate run with the yearly bar at the 90th percentile:

| bar | median rank width, top 25 | top 50 | median `mass_sd / mass`, top 25 |
| --- | --- | --- | --- |
| field mean | **64** | **102** | **0.20** |
| 90th percentile | 101 | 157 | 0.38 |

Raising the bar makes the board **less** identified, not more, and nearly
doubles the relative spread of the score. The mechanism is straightforward once
measured: a higher bar discards contributing years, so each career total rests
on fewer terms and inherits more variance from each of them.

This settles what the bar decision is and is not. It is **not** a
precision-versus-noise trade where one option is technically better. Both bars
describe a real quantity; the higher one measures time spent genuinely
dominating the field, and it costs identification to do so. Choosing it means
accepting a noisier ordering in exchange for a different estimand — which is a
product judgement, made in view of that price, and not something the evidence
decides.

### Cost

The 90th-percentile run took **793 s wall for 150 replicates** (~5.3 s each) on
an idle machine. The first run's recorded 10,434 s was measured while the
virtual-game sweep was saturating the same cores; treat ~5 s per replicate as
the real figure and anything above it as contention.

## 4. The bar is now an explicit parameter

Career skill mass is $\sum_a [\bar\theta_{ia}-m_a]_+$. Two measurements about
the choice of $m_a$:

- **At the field mean the positive part never binds.** 97.4% of the top fifty's
  active years clear it, so the functional degenerates to *active years × mean
  excess* — the clip is decoration and the board is a longevity board. At the
  90th percentile that share falls to 81.8%, and at a top-ten reference to 55.9%.
- **The mean is the least robust choice available.** Perturbing the field
  composition by dropping every single-appearance fighter-year (48% of all
  fighter-years) moves the mean bar by 25.3 points on average, the median by
  22.0, the 75th percentile by 13.1, and the 90th by 7.6.

The choice is consequential: top-100 overlap against the production board is
96/100 at the median, 63/100 at the 90th percentile, and 21/100 at a top-ten
reference. Rather than assert one bar, `career_mass_family` recomputes the same
functional across the range and the notebook plots the rank ladder, so a reader
sees which fighters the choice decides. The production default remains the field
mean; changing it is a product decision that should be made in daylight, and the
evidence above is what it should be made from.

An early attempt to fix the thin-record problem *inside* the functional — an
empirical-Bayes shrink of each fighter-year mean — was measured and discarded:
the pooled within-fighter-year appearance variance is only 17.4 (sd 4.2 rating
points), because WHR appearances inside one year barely spread, so the shrinkage
factor was 0.998 at $n=1$ and did nothing. The real uncertainty about a thin
record lives in the estimator, not in the within-year scatter, which is why it
is handled by the prior and reported by the bootstrap.

## 5. Still open

| Item | State |
| --- | --- |
| Virtual-game mass | Measured and **unresolved** — all paired intervals cross zero. Ships at $v=2$ by the stated tie-break, not by a demonstrated lift. A larger held-out sample, or an evaluation restricted to bouts involving a thin record (where the prior actually bites), is the way to resolve it. |
| Cross-organization scope | Still quarantined. Its weights use eventual UFC careers, so no predictive claim is available until they are fold-local. |
| Bar default | Field mean retained; the family and its sensitivity are published rather than a silent choice. |
| Bootstrap cost | ~7.7 s per replicate, so 200 replicates is a ~25 minute offline build, not a notebook-time computation. |
