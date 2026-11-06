//! The held-out test a rating change must pass (docs/DECISIONS.md, "A rating
//! change passes a held-out prediction test").
//!
//! Rolling origin over every decided UFC card of the chosen years: both the
//! production fit and a candidate are refitted on card-enumerated bouts strictly
//! before the card, each fighter's last rating is carried to the card date
//! along the learned age curve, and a bout is scored when both fighters have
//! at least three earlier appearances. The comparison is paired by bout;
//! its 95% interval resamples whole cards, because bouts on one card are not
//! independent. Negative differences favour the candidate.

use std::collections::{BTreeSet, HashMap};

use crate::bouts::Bout;
use crate::era::year;
use crate::frame::Day;
use crate::stats::{mean, psum, quantile, Pcg64};
use crate::whr::{elo_per_nat, project, Graph, Settings, YEAR_DAYS};

const EPS: f64 = 1e-6;
const MIN_PRIOR: usize = 3;
const BOOT: usize = 2000;
const SEED: u32 = 20260818;
/// The cards the registered test scores (run 2026-10-23).
pub const YEARS: [i32; 2] = [2024, 2025];

/// The registered candidate: the exact posterior solver, without re-centring.
pub fn candidate() -> Settings {
    Settings {
        center: false,
        ..Settings::default()
    }
}

/// One scored bout: P(fighter_a wins) under production and candidate, and the result.
pub struct Forecast {
    pub card: usize,
    pub url: String,
    pub p: [f64; 2],
    pub y: f64,
}

pub struct Delta {
    pub metric: &'static str,
    pub base: f64,
    pub cand: f64,
    pub delta: f64,
    pub lo: f64,
    pub hi: f64,
}

pub struct Report {
    pub cards: Vec<(Day, String)>,
    pub forecasts: Vec<Forecast>,
    pub metrics: Vec<Delta>,
    pub candidate: Settings,
}

fn decided(x: &Bout) -> bool {
    !x.draw() && !x.nc() && !x.winner().is_empty() && (x.winner() == x.a() || x.winner() == x.b())
}

/// Ratings entering `day` from a fit on `train`: last rating per fighter, age-projected.
fn entering(
    train: &[Bout],
    births: &HashMap<String, Day>,
    p: &Settings,
    day: Day,
) -> HashMap<String, f64> {
    let g = Graph::new(train, births, p.graded);
    let (r, dr) = g.fit(p, true);
    let k = elo_per_nat();
    let drift: Vec<f64> = dr.iter().map(|x| x * k * YEAR_DAYS).collect();
    // Nodes are chronological per fighter, so the last node seen is the last appearance;
    // ties within a day resolve to the later event name, as the sorted history does.
    let mut last: HashMap<&str, usize> = HashMap::new();
    for u in 0..r.len() {
        let e = last.entry(&g.fighter()[u]).or_insert(u);
        if (g.day()[u], &g.event()[u]) >= (g.day()[*e], &g.event()[*e]) {
            *e = u;
        }
    }
    last.into_iter()
        .map(|(f, u)| {
            let mu = 1500.0 + r[u] * k;
            (
                f.to_string(),
                project(
                    mu,
                    (g.day()[u] + 10957.0) as Day,
                    day,
                    births.get(f).copied(),
                    &drift,
                ),
            )
        })
        .collect()
}

/// Splits `0..n` jobs over the available cores, keeping result order.
fn parallel<T: Send, F: Fn(usize) -> T + Sync>(n: usize, f: F) -> Vec<T> {
    let w = std::thread::available_parallelism()
        .map_or(1, |x| x.get())
        .min(n.max(1));
    let mut out: Vec<Option<T>> = (0..n).map(|_| None).collect();
    std::thread::scope(|s| {
        let chunks: Vec<_> = out.chunks_mut(n.div_ceil(w).max(1)).enumerate().collect();
        for (c, slot) in chunks {
            let f = &f;
            let size = n.div_ceil(w).max(1);
            s.spawn(move || {
                for (j, x) in slot.iter_mut().enumerate() {
                    *x = Some(f(c * size + j));
                }
            });
        }
    });
    out.into_iter().map(Option::unwrap).collect()
}

/// Paired difference candidate − production of a per-bout loss, with a card-bootstrap 95% interval.
fn paired(metric: &'static str, f: &[Forecast], ncards: usize, loss: fn(f64, f64) -> f64) -> Delta {
    let l = |i: usize| {
        f.iter()
            .map(|x| loss(x.p[i].clamp(EPS, 1.0 - EPS), x.y))
            .collect::<Vec<_>>()
    };
    let (a, b) = (l(0), l(1));
    let d: Vec<f64> = a.iter().zip(&b).map(|(a, b)| b - a).collect();
    let (mut sum, mut size) = (vec![0.0; ncards], vec![0.0; ncards]);
    for (x, d) in f.iter().zip(&d) {
        sum[x.card] += d;
        size[x.card] += 1.0;
    }
    let cards: Vec<usize> = (0..ncards).filter(|c| size[*c] > 0.0).collect();
    // NumPy's `default_rng(SEED).integers(0, k, (BOOT, k))`, row sums pairwise as `sum(axis=1)`.
    let mut rng = Pcg64::new(SEED);
    let boots: Vec<f64> = (0..BOOT)
        .map(|_| {
            let ix: Vec<usize> = (0..cards.len())
                .map(|_| cards[rng.below(cards.len() as u32)])
                .collect();
            psum(&ix.iter().map(|&c| sum[c]).collect::<Vec<_>>())
                / ix.iter().map(|&c| size[c]).sum::<f64>()
        })
        .collect();
    Delta {
        metric,
        base: mean(&a),
        cand: mean(&b),
        delta: mean(&d),
        lo: quantile(&boots, 0.025),
        hi: quantile(&boots, 0.975),
    }
}

/// Production against `candidate` on every decided UFC card of `YEARS`.
pub fn compare(rated: &[Bout], births: &HashMap<String, Day>, candidate: Settings) -> Report {
    // Event-time filtering alone cannot remove retrospectively selected career coverage.
    let history: Vec<Bout> = rated
        .iter()
        .filter(|b| crate::bouts::predictive(b))
        .cloned()
        .collect();
    let rated = history.as_slice();
    let cards: Vec<(Day, String)> = rated
        .iter()
        .filter(|x| decided(x) && x.org == "UFC" && YEARS.contains(&year(x.day)))
        .map(|x| (x.day, x.event.clone()))
        .collect::<BTreeSet<_>>()
        .into_iter()
        .collect();
    let settings = [Settings::default(), candidate];
    let per_card = parallel(cards.len(), |c| {
        let (day, event) = &cards[c];
        let train: Vec<Bout> = rated.iter().filter(|x| x.day < *day).cloned().collect();
        let mut prior: HashMap<&str, usize> = HashMap::new();
        for x in &train {
            *prior.entry(x.a()).or_default() += 1;
            *prior.entry(x.b()).or_default() += 1;
        }
        let mu: Vec<HashMap<String, f64>> = settings
            .iter()
            .map(|p| entering(&train, births, p, *day))
            .collect();
        let n = |f: &str| prior.get(f).copied().unwrap_or(0);
        rated
            .iter()
            .filter(|x| x.day == *day && x.event == *event && x.org == "UFC" && decided(x))
            .filter(|x| n(x.a()) >= MIN_PRIOR && n(x.b()) >= MIN_PRIOR)
            .map(|x| {
                let p = |m: &HashMap<String, f64>| {
                    1.0 / (1.0 + (-(m[x.a()] - m[x.b()]) / elo_per_nat()).exp())
                };
                Forecast {
                    card: c,
                    url: x.url.clone(),
                    p: [p(&mu[0]), p(&mu[1])],
                    y: f64::from(x.winner() == x.a()),
                }
            })
            .collect::<Vec<_>>()
    });
    let forecasts: Vec<Forecast> = per_card.into_iter().flatten().collect();
    let metrics = vec![
        paired("log loss", &forecasts, cards.len(), |p, y| {
            -(y * p.ln() + (1.0 - y) * (1.0 - p).ln())
        }),
        paired("Brier score", &forecasts, cards.len(), |p, y| {
            (p - y) * (p - y)
        }),
    ];
    Report {
        cards,
        forecasts,
        metrics,
        candidate,
    }
}

/// The report as a Markdown table.
pub fn format(r: &Report) -> String {
    let used: BTreeSet<usize> = r.forecasts.iter().map(|f| f.card).collect();
    let mut s = format!(
        "Held-out test: production WHR against {:?}\n\n{} bouts on {} UFC cards of {}–{}; negative favours the candidate.\n\n\
         | Measure | Production | Candidate | Candidate minus production | 95% interval (cards resampled) |\n\
         | --- | ---: | ---: | ---: | --- |\n",
        r.candidate,
        r.forecasts.len(),
        used.len(),
        YEARS[0],
        YEARS[YEARS.len() - 1]
    );
    for m in &r.metrics {
        s += &format!(
            "| {} | {:.4} | {:.4} | {:+.4} | {:+.4} to {:+.4} |\n",
            m.metric, m.base, m.cand, m.delta, m.lo, m.hi
        );
    }
    s
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::bouts::{Corner, Outcome};
    use crate::frame::parse_day;

    #[test]
    fn retrospective_career_rows_cannot_change_heldout_forecasts() {
        let bout = |date: &str, org: &str, source: &str| {
            let mut b = Bout::new(
                "Alice".into(),
                "Bob".into(),
                parse_day(date),
                Outcome::Win(Corner::A),
                1.0,
            )
            .unwrap();
            b.org = org.into();
            b.source = source.into();
            b.event = date.into();
            b.model = true;
            b
        };
        let mut rows = vec![
            bout("2023-01-01", "UFC", "ufc"),
            bout("2023-03-01", "UFC", "ufc"),
            bout("2023-06-01", "UFC", "ufc"),
            bout("2024-02-01", "UFC", "ufc"),
        ];
        let births = HashMap::new();
        let before = compare(&rows, &births, candidate());
        rows.insert(0, bout("2022-01-01", "Regional", "sherdog"));
        let after = compare(&rows, &births, candidate());
        assert_eq!(before.forecasts.len(), 1);
        assert_eq!(after.forecasts.len(), 1);
        assert_eq!(before.forecasts[0].p, after.forecasts[0].p);
    }
}
