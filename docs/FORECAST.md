# Pre-fight forecast benchmark

`ratings/forecast.py` builds forecasts of UFC bouts from information available before each fight. They are scored
against the no-vig betting price and the actual result. The site's Forecast accuracy section draws these numbers
through `analysis/build_site.py`. To print them, run `python -m ratings.forecast data/snapshots/<date>`.

## Design

- **Walk-forward validation.** Each test year Y (2012 onward) is forecast by models fitted on bouts dated before
  1 January Y. Every feature for a bout reads only bouts on strictly earlier dates.
- **Test set.** Decided UFC bouts with a usable line in `odds_lines.parquet`, where `odds_data_quality` is "ok".
  These lines come from the mdabbert Ultimate UFC dataset, which does not record whether they are opening or closing
  lines.
- **Antisymmetry.** The source lists the winner first in about 62% of bouts. Every model is fitted on both corner
  orders, has no intercept, and gives P(a beats b) + P(b beats a) = 1. Corner order therefore carries no signal.
- **Metrics.** Log loss, Brier score and the share of winners picked. Each forecast's log loss gap to the market has a
  95% interval from an event-cluster bootstrap with 2,000 resamples and seed 20261027.

## Forecasts

| Forecast | Definition |
| --- | --- |
| Coin flip | 0.5 |
| Rating alone | Glicko-2 predictive probability (Glickman 2012) from the production `RatingEngine`, re-run on the leak-free history below |
| Stats model | L2 logistic regression (C = 1, no intercept) on corner differences in the features listed below |
| Betting market | No-vig implied probability |
| Market + stats model | The stats model with logit(market) added as a feature, fitted only on earlier bouts that have odds |

The stats model's features are each corner's value minus the other's:

- **Rating:** the rating's logit, and its deviation φ.
- **Age:** age, and age beyond 32.
- **Body:** height and reach.
- **Activity:** log days since the previous bout, and whether that gap exceeded a year.
- **Record:** log pro bouts, shrunk win rate (W + 2)/(N + 4), current streak, knockout losses in the last two years,
  and log UFC bouts.
- **UFC in-fight rates:** taken from earlier UFC bouts and shrunk toward the pre-2012 population rate with 15 minutes of
  prior weight:
  - significant strikes landed and absorbed per minute, accuracy and defence;
  - takedowns per 15 minutes, takedown accuracy and takedown defence;
  - submission attempts per 15 minutes;
  - share of control time;
  - knockdowns scored and suffered per 15 minutes.

The fit is Newton's method on the L2-penalised log likelihood. A gradient-boosted-tree variant was also tried in the
development study. It scored worse than the logistic model (log loss 0.664) and is not shipped.

## The selection leak

`build_sherdog_careers.py` crawled whole careers, regional bouts included, only for fighters who had three or more UFC
bouts when it ran. That is the right rule for career rankings. For a forecast test it is a leak: a deep recorded
pre-UFC history reveals that the fighter went on to last in the UFC. For example, Derek Brunson's 2010 regional bouts
are in the corpus, but the pre-UFC bouts of Brian Houston, who had two UFC bouts, are not.

On the repository's rating history, the market-plus-stats model appeared to beat the market. The apparent gain was a
log loss gap of −0.006 and a +10.5% betting return over 3,597 bets. After the leak was removed, the log loss gain
disappeared.

The forecast history therefore keeps only UFC bouts and the promotions the corpus enumerates card by card: PRIDE, WEC,
Strikeforce, Affliction, Bellator and RIZIN. In those promotions a fighter's recorded past does not depend on their
future. The same leak affects any forecast check built on `ratings_history.parquet`.

## Results, snapshot 2026-10-24

6,068 bouts across 572 events, 2012-01-14 to 2026-03-28.

| Forecast | Log loss | Brier | Winners picked | Log loss minus market (95% interval) |
| --- | --- | --- | --- | --- |
| Coin flip | 0.693 | 0.250 | 50.0% | +0.086 (+0.077 to +0.095) |
| Rating alone | 0.695 | 0.249 | 56.4% | +0.088 (+0.079 to +0.098) |
| Stats model | 0.651 | 0.229 | 61.8% | +0.044 (+0.036 to +0.052) |
| Betting market | 0.607 | 0.210 | 66.4% | |
| Market + stats model | 0.609 | 0.211 | 66.8% | +0.002 (−0.003 to +0.008) |

Findings:

- **No forecast beats the market.** The stats model closes about half the gap from a coin flip to the market.
- **The stats add nothing measurable to the price.** Adding them to the market leaves log loss unchanged within the
  interval.
- **The rating alone is overconfident.** It picks 56% of winners, but its log loss is slightly worse than a coin flip's.

## Limits

- **The betting result is unconfirmed.** Betting the market-plus-stats model at the quoted odds whenever its expected
  return exceeded 5% gave +6.2% over 3,148 bets, with a 95% interval of +2.3% to +9.8%.
  - It does not count as an edge: the proper score shows no gain, and the rule was examined after the leak fix.
  - The odds come from one dataset with undocumented timing.
  - Most of the return came from underdog bets: +10.5% on underdogs against +1.8% on favourites.

  A forward test on lines with known timing would settle it.
- **Forecast inputs are limited.** The forecasts do not use short-notice replacements, weight cuts, injuries or camp
  changes.
- **Related work.** Holmes, McHale and Zychaluk, "A Markov chain model for forecasting results of mixed martial arts
  contests", *International Journal of Forecasting* 39(2), 623–640 (doi 10.1016/j.ijforecast.2022.01.007), simulate
  bouts round by round. Only their abstract was read: it reports forecasts comparable to bookmakers. This benchmark
  does not implement their model.
