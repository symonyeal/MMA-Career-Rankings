# Mathematical Audit - 2026-05-14

## Executive Judgment

The production headline should remain the WHR sustained-peak surface:

```text
sustained_peak_headline_mu_whr
```

The method plus sleeves period stream is useful as a forensic surface, but it
is not a principled all-time ranking. It still overreacts to title-run windows
and method/context bonuses, which is why Daniel Cormier, Kamaru Usman, and
Chris Weidman rise too high while Georges St-Pierre and Demetrious Johnson
fall too low. The notebook now leads with WHR and keeps sleeve effects in an
attribution dashboard.

Mixed-gender all-time ordering is not identifiable from fight results because
there are no bridge bouts between men's and women's divisions. The build now
emits `gender` and `recent_division`; reporting should split these cohorts
instead of inventing an arbitrary cross-gender penalty.

## Glicko-2 Core

For a fighter with internal-scale rating \(r\), deviation \(\phi\), and
opponent \(j\), the standard Glicko-2 update uses:

\[
g(\phi_j)=\frac{1}{\sqrt{1+3\phi_j^2/\pi^2}},
\qquad
E_j=\frac{1}{1+\exp\{-g(\phi_j)(r-r_j)\}}.
\]

\[
v=\left[\sum_j g(\phi_j)^2E_j(1-E_j)\right]^{-1},
\qquad
\Delta=v\sum_j g(\phi_j)(S_j-E_j).
\]

Strict canonical Glicko-2 cannot punish a win in a one-bout period because
\(S_j=1\) and \(E_j<1\). The champion's paradox appears only when the method
stream replaces \(S_j\) with a continuous score below 1.

## Championship Defense Floor

Implemented in the build-time quality-method score:

\[
S^*_j =
\begin{cases}
\max(S_j, 0.990), & \text{undisputed champion successfully defends},\\
\max(S_j, 0.985), & \text{interim champion successfully defends},\\
S_j, & \text{otherwise}.
\end{cases}
\]

This is a floor, not a bonus. It prevents a narrow title defense from entering
the method stream as a sub-expectation result. It does not alter
`mu_canonical`.

## Dominance Scalar

Implemented as a direct score modifier, not a sleeve:

\[
d_j=\frac{1}{1+\exp(-D_j / c_D)}, \qquad
S^{**}_j=\operatorname{clip}\left(S^*_j+
\lambda_D\max(0,2d_j-1),\,0.975,\,1.000\right),
\]

where \(D_j\) is the winner-perspective dominance z-score from damage,
submission attempts, and control, \(c_D=2.0\), and \(\lambda_D=0.010\).
Finishes already score 1.0, so this mainly separates dominant decisions from
ordinary decisions.

## Sleeve Collinearity

The performance sleeve treats opponent quality as one latent signal. Opponent
mu, divisional rank, championship status, and P4P status are deduplicated via:

\[
Q_i=\max(Q_{\mu}, Q_{\text{rank}}, Q_{\text{champ}}, Q_{\text{p4p}}).
\]

The per-fight performance signal is then:

\[
S_i=\log F_{\text{dec}}+\log F_Q+\log F_{\text{upset}}
     +\log F_{\text{streak}}+\log F_{\text{weight}}.
\]

\[
w_{\text{winner}}=1+0.20\tanh(S_i / 0.20),
\qquad
w_{\text{loser}}=1-0.20\tanh(S_i / 0.20).
\]

Market odds are retained for audit and only confirm an already-open rank upset
gate. A pure "market underdog" bonus is rejected because it double-counts the
same expectation shock as rank-gated upset and opponent quality.

## Era and Division Normalization

The peak window score normalizes raw \(\mu\) by year and division using
empirical-Bayes shrinkage. For year \(t\):

\[
\hat\delta_t = (\bar\mu_t-\bar\mu)
\frac{\tau_t^2}{\tau_t^2+s_t^2/n_t}
B_t,
\]

where \(B_t\) is the bridge fraction: the share of fighters in that year who
also appear in another year. The normalized rating is then blended toward the
division-rescaled value:

\[
\mu^{\text{period}}_i=(1-\alpha)\mu_i+\alpha
\left[\bar\mu+\sigma
\frac{\mu_i-\hat\delta_t-\bar\mu_{d(i)}}{\sigma_{d(i)}}\right],
\qquad
\alpha\le 0.50.
\]

This is preferable to a hand-picked "2005 penalty" because early eras with few
bridges receive little correction.

## Activity Penalty

Canonical Glicko inactivity inflation remains uncertainty-only. For current
rank-camping diagnostics, the build emits post-rating current-view columns:

\[
m_i=\frac{\text{snapshot date}-\text{last fight date}}{30.4375},
\qquad
a_i=\operatorname{clip}\left(
\frac{m_i-15}{30-15},0,1\right).
\]

\[
\pi_i = 75\,a_i^2\left(1-\min(\phi_i/350,1)\right),
\qquad
\mu^{\text{active}}_i=\mu_i-\pi_i.
\]

This should be used for current active rankings only. It should not be used
for all-time greatness because retirement is not rank camping.

## Diagnostic Artifacts

The build now emits:

```text
calibration_residuals.parquet
sleeve_attribution.parquet
division_entropy.parquet
```

The notebook reads these directly and has three dashboards:

1. Calibration residuals by division or stance.
2. Sleeve attribution waterfall for a selected fighter.
3. Division entropy and top-10 density over time.

## Archival Candidates

Mark for archival, not production:

- `ratings/replacement_framework.py`: a separate research ranking framework,
  not wired into the Glicko-2 plus sleeve engine.
- `_diagnostics/*.py`: one-off exploratory scripts superseded by the three
  build-time diagnostic artifacts.
- `scripts/top25_sleeve.py`: superseded by the WHR headline top table and
  sleeve attribution dashboard.

Do not delete source/provenance loaders (`datalab_loader`, `fightmatrix_loader`,
`odds_ingest_mdabbert`) because they feed staged comparison artifacts.
