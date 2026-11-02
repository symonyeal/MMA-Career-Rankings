//! Glicko-2 per event, with lazy deviation inflation between appearances
//! (Glickman 2012; update order of Heungsub Lee's BSD-licensed `glicko2`).
//!
//! Every fighter carries two ratings: `canonical`, scored {0, ½, 1}, and
//! `method`, where the winner scores the method price (`Bout::score`). An event
//! is one rating period for the fighters on its card; between appearances a
//! fighter's deviation inflates once per elapsed month (365.25/12 days).
//! Constants: centre 1500, φ₀ 350, σ₀ 0.06, τ 0.5, ε 1e-6, scale 173.7178.
//!
//! The C library's `pow`, `exp`, `sqrt` and `log` are called directly: the
//! published ratings were computed with them, and LLVM would otherwise fold
//! `pow(x, 2)` into `x*x`, whose last bit can differ.

use std::collections::HashMap;

use crate::bouts::Bout;
use crate::divisions::normalize;
use crate::frame::{Day, Table};
use crate::stats::kahan_mean;

const MU: f64 = 1500.0;
const PHI: f64 = 350.0;
const SIGMA: f64 = 0.06;
const TAU: f64 = 0.5;
const EPS: f64 = 1e-6;
const RATIO: f64 = 173.7178;
const PI: f64 = std::f64::consts::PI;
const DAYS_PER_MONTH: f64 = 365.25 / 12.0;

#[cfg_attr(windows, link(name = "ucrt"))]
#[cfg_attr(not(windows), link(name = "m"))]
extern "C" {
    #[link_name = "pow"]
    fn c_pow(x: f64, y: f64) -> f64;
    #[link_name = "exp"]
    fn c_exp(x: f64) -> f64;
    #[link_name = "sqrt"]
    fn c_sqrt(x: f64) -> f64;
    #[link_name = "log"]
    fn c_log(x: f64) -> f64;
}

pub(crate) fn pow(x: f64, y: f64) -> f64 {
    unsafe { c_pow(x, std::hint::black_box(y)) }
}

pub(crate) fn exp(x: f64) -> f64 {
    unsafe { c_exp(std::hint::black_box(x)) }
}

pub(crate) fn sqrt(x: f64) -> f64 {
    unsafe { c_sqrt(x) }
}

pub(crate) fn log(x: f64) -> f64 {
    unsafe { c_log(x) }
}

#[derive(Clone, Copy, Debug)]
pub struct Rating {
    pub mu: f64,
    pub phi: f64,
    pub sigma: f64,
}

const PRIOR: Rating = Rating {
    mu: MU,
    phi: PHI,
    sigma: SIGMA,
};

/// New volatility σ′ by the Illinois iteration of Glickman's step 5.
fn volatility(phi: f64, sigma: f64, delta: f64, v: f64) -> f64 {
    let d2 = pow(delta, 2.0);
    let alpha = log(pow(sigma, 2.0));
    let f = |x: f64| {
        let t = pow(phi, 2.0) + v + exp(x);
        exp(x) * (d2 - t) / (2.0 * pow(t, 2.0)) - (x - alpha) / pow(TAU, 2.0)
    };
    let mut a = alpha;
    let mut b = if d2 > pow(phi, 2.0) + v {
        log(d2 - pow(phi, 2.0) - v)
    } else {
        let mut k = 1.0;
        while f(alpha - k * sqrt(pow(TAU, 2.0))) < 0.0 {
            k += 1.0;
        }
        alpha - k * sqrt(pow(TAU, 2.0))
    };
    let (mut fa, mut fb) = (f(a), f(b));
    while (b - a).abs() > EPS {
        let c = a + (a - b) * fa / (fb - fa);
        let fc = f(c);
        if fc * fb < 0.0 {
            a = b;
            fa = fb;
        } else {
            fa /= 2.0;
        }
        b = c;
        fb = fc;
    }
    pow(exp(1.0), a / 2.0)
}

/// One rating period against `(score, opponent)` results.
fn rate(r: Rating, series: &[(f64, Rating)]) -> Rating {
    let (mu, phi) = ((r.mu - MU) / RATIO, r.phi / RATIO);
    let (mut v_inv, mut delta) = (0.0, 0.0);
    for &(s, o) in series {
        let (om, op) = ((o.mu - MU) / RATIO, o.phi / RATIO);
        let g = 1.0 / sqrt(1.0 + (3.0 * pow(op, 2.0)) / pow(PI, 2.0));
        let e = 1.0 / (1.0 + exp(-g * (mu - om)));
        v_inv += 1.0 * pow(g, 2.0) * e * (1.0 - e);
        delta += 1.0 * g * (s - e);
    }
    if v_inv == 0.0 {
        let star = sqrt(pow(phi, 2.0) + pow(r.sigma, 2.0));
        return Rating {
            mu: mu * RATIO + MU,
            phi: star * RATIO,
            sigma: r.sigma,
        };
    }
    delta /= v_inv;
    let v = 1.0 / v_inv;
    let sigma = volatility(phi, r.sigma, delta, v);
    let star = sqrt(pow(phi, 2.0) + pow(sigma, 2.0));
    let phi = 1.0 / sqrt(1.0 / pow(star, 2.0) + 1.0 / v);
    let mu = mu + pow(phi, 2.0) * (delta / v);
    Rating {
        mu: mu * RATIO + MU,
        phi: phi * RATIO,
        sigma,
    }
}

/// `periods` inactive months; μ makes the scale round trip the published code made.
fn inflate(r: Rating, periods: i64) -> Rating {
    let (mut mu, mut phi) = (r.mu, r.phi);
    for _ in 0..periods {
        mu = (mu - MU) / RATIO * RATIO + MU;
        phi = sqrt(pow(phi / RATIO, 2.0) + pow(r.sigma, 2.0)) * RATIO;
    }
    Rating {
        mu,
        phi,
        sigma: r.sigma,
    }
}

/// `predict_win_prob_from_ratings`: P(a beats b), g applied to the combined deviation.
pub fn predict(a: (f64, f64), b: (f64, f64)) -> f64 {
    let (ma, pa, mb, pb) = (
        (a.0 - MU) / RATIO,
        a.1 / RATIO,
        (b.0 - MU) / RATIO,
        b.1 / RATIO,
    );
    let phi = hypot(pa, pb);
    let g = 1.0 / sqrt(1.0 + 3.0 * pow(phi, 2.0) / pow(PI, 2.0));
    let z = g * (ma - mb);
    if z >= 0.0 {
        1.0 / (1.0 + exp(-z))
    } else {
        let e = exp(z);
        e / (1.0 + e)
    }
}

/// √(x² + y²) rounded from its double-double value, as CPython's `math.hypot`.
fn hypot(x: f64, y: f64) -> f64 {
    let (x2, y2) = (x * x, y * y);
    let (ex, ey) = (x.mul_add(x, -x2), y.mul_add(y, -y2));
    let s = x2 + y2;
    let lo = (x2 - s) + y2 + ex + ey;
    let h = s.sqrt();
    h + (h.mul_add(-h, s) + lo) / (2.0 * h)
}

/// One appearance: the canonical rating entering the event and leaving it.
#[derive(Clone, Debug)]
pub struct Row {
    pub fighter: usize,
    pub day: Day,
    pub event: String,
    pub pre: (f64, f64),
    pub post: (f64, f64),
}

struct State {
    c: Rating,
    m: Rating,
    last: Day,
}

pub struct Glicko {
    pub names: Vec<String>,
    /// History rows ordered `(fighter, day, event)`, one per fighter per event.
    pub rows: Vec<Row>,
    /// Per fighter: canonical, method, last event day.
    states: Vec<State>,
}

/// Winner-first score pairs `(canonical, method)` for the two corners; `None` when the bout is unscoreable.
fn scores(x: &Bout) -> Option<([f64; 2], [f64; 2])> {
    if x.draw {
        return Some(([0.5; 2], [0.5; 2]));
    }
    let c = if x.winner == x.a {
        [1.0, 0.0]
    } else if x.winner == x.b && !x.b.is_empty() {
        [0.0, 1.0]
    } else {
        return None;
    };
    let m = if x.score.is_nan() {
        c
    } else if c[0] == 1.0 {
        [x.score, 1.0 - x.score]
    } else {
        [1.0 - x.score, x.score]
    };
    Some((c, m))
}

/// `canonical_engine`: events in `(day, event)` order (stable), each processed atomically.
pub fn engine(bouts: &[&Bout]) -> Glicko {
    let mut order: Vec<&Bout> = bouts.to_vec();
    order.sort_by(|x, y| (x.day, &x.event).cmp(&(y.day, &y.event)));
    let mut id: HashMap<String, usize> = HashMap::new();
    let mut names: Vec<String> = Vec::new();
    let mut states: Vec<State> = Vec::new();
    let mut rows: Vec<Row> = Vec::new();
    let mut i = 0;
    while i < order.len() {
        let (day, event) = (order[i].day, order[i].event.clone());
        let j = i + order[i..]
            .iter()
            .take_while(|x| x.day == day && x.event == event)
            .count();
        let card = &order[i..j];
        let mut on: Vec<usize> = Vec::new();
        for x in card {
            for f in [&x.a, &x.b] {
                let k = *id.entry(f.clone()).or_insert_with(|| {
                    names.push(f.clone());
                    states.push(State {
                        c: PRIOR,
                        m: PRIOR,
                        last: Day::MIN,
                    });
                    names.len() - 1
                });
                if !on.contains(&k) {
                    on.push(k);
                }
            }
        }
        for &k in &on {
            let s = &mut states[k];
            if s.last != Day::MIN {
                let months = ((day - s.last) as f64 / DAYS_PER_MONTH) as i64;
                s.c = inflate(s.c, months);
                s.m = inflate(s.m, months);
            }
        }
        let pre: HashMap<usize, (Rating, Rating)> = on
            .iter()
            .map(|&k| (k, (states[k].c, states[k].m)))
            .collect();
        let mut series: HashMap<usize, (Vec<(f64, Rating)>, Vec<(f64, Rating)>)> = HashMap::new();
        for x in card {
            let Some((c, m)) = scores(x) else { continue };
            let (a, b) = (id[&x.a], id[&x.b]);
            for (f, o, side) in [(a, b, 0), (b, a, 1)] {
                let e = series.entry(f).or_default();
                e.0.push((c[side], pre[&o].0));
                e.1.push((m[side], pre[&o].1));
            }
        }
        for &k in &on {
            if let Some((sc, sm)) = series.get(&k) {
                states[k].c = rate(pre[&k].0, sc);
                states[k].m = rate(pre[&k].1, sm);
            }
            states[k].last = day;
            let p = pre[&k].0;
            rows.push(Row {
                fighter: k,
                day,
                event: event.clone(),
                pre: (p.mu, p.phi),
                post: (states[k].c.mu, states[k].c.phi),
            });
        }
        i = j;
    }
    rows.sort_by(|x, y| {
        (&names[x.fighter], x.day, &x.event).cmp(&(&names[y.fighter], y.day, &y.event))
    });
    Glicko {
        names,
        rows,
        states,
    }
}

/// The published engine over the rated bouts.
pub fn run(rated: &[Bout]) -> Glicko {
    engine(&rated.iter().collect::<Vec<_>>())
}

impl Glicko {
    /// `ratings_current` Glicko columns; `rating_periods` counts history rows.
    pub fn current(&self) -> Table {
        let mut periods = vec![0i64; self.names.len()];
        for r in &self.rows {
            periods[r.fighter] += 1;
        }
        let s = &self.states;
        let col = |g: fn(&State) -> f64| s.iter().map(g).collect::<Vec<_>>();
        Table::default()
            .str("fighter", &self.names)
            .f64("mu_canonical", &col(|x| x.c.mu))
            .f64("phi_canonical", &col(|x| x.c.phi))
            .f64("sigma_canonical", &col(|x| x.c.sigma))
            .f64("mu_method", &col(|x| x.m.mu))
            .f64("phi_method", &col(|x| x.m.phi))
            .f64("sigma_method", &col(|x| x.m.sigma))
            .day(
                "last_event_date",
                &s.iter().map(|x| Some(x.last)).collect::<Vec<_>>(),
            )
            .i64("rating_periods", &periods)
    }

    /// Per (fighter, day, event): the rating after the previous appearance (1500, 350 before any)
    /// and the number of earlier appearances, as `_prefight_history`.
    fn prefight(&self) -> HashMap<(&str, Day, &str), ((f64, f64), usize)> {
        let mut out = HashMap::new();
        let mut k = 0;
        for (i, r) in self.rows.iter().enumerate() {
            let first = i == 0 || self.rows[i - 1].fighter != r.fighter;
            k = if first { 0 } else { k + 1 };
            let prev = if first {
                (MU, PHI)
            } else {
                self.rows[i - 1].post
            };
            out.insert(
                (self.names[r.fighter].as_str(), r.day, r.event.as_str()),
                (prev, k),
            );
        }
        out
    }
}

/// `calibration_residual_rows`, overall and division segments: decided bouts whose
/// corners both have three earlier appearances, each seen from both corners,
/// binned into tenths of the pre-fight probability (right-closed, 0 in the first).
pub fn calibration(g: &Glicko, rated: &[Bout]) -> Table {
    let pre = g.prefight();
    let mut left: Vec<(Option<String>, f64, f64)> = Vec::new();
    for x in rated
        .iter()
        .filter(|x| !x.draw && !x.winner.is_empty() && !x.a.is_empty() && !x.b.is_empty())
    {
        let (a, b) = (
            pre[&(x.a.as_str(), x.day, x.event.as_str())],
            pre[&(x.b.as_str(), x.day, x.event.as_str())],
        );
        if a.1 < 3 || b.1 < 3 {
            continue;
        }
        let p = predict(a.0, b.0);
        left.push((
            normalize(&x.weight_class),
            p,
            if x.winner == x.a { 1.0 } else { 0.0 },
        ));
    }
    let apps: Vec<(Option<String>, f64, f64)> = left
        .iter()
        .cloned()
        .chain(left.iter().map(|(d, p, y)| (d.clone(), 1.0 - p, 1.0 - y)))
        .collect();
    let edges: Vec<f64> = (0..=10)
        .map(|i| if i == 10 { 1.0 } else { i as f64 * 0.1 })
        .collect();
    let bin = |p: f64| {
        if p == 0.0 {
            0
        } else {
            edges.partition_point(|e| *e < p) as i64 - 1
        }
    };
    let mut divisions: Vec<Option<String>> = apps.iter().map(|a| a.0.clone()).collect();
    // pandas groups the missing division last, labelled "nan".
    divisions.sort_by_key(|d| (d.is_none(), d.clone()));
    divisions.dedup();
    let mut segments: Vec<(&str, String, Vec<&(Option<String>, f64, f64)>)> =
        vec![("overall", "all".into(), apps.iter().collect())];
    for d in &divisions {
        let label = d.clone().unwrap_or_else(|| "nan".into());
        segments.push((
            "division",
            label,
            apps.iter().filter(|a| &a.0 == d).collect(),
        ));
    }
    let (mut st, mut sv, mut pb, mut pm, mut ew, mut n) =
        (vec![], vec![], vec![], vec![], vec![], vec![]);
    for (t, v, rows) in segments {
        let mut bins: std::collections::BTreeMap<i64, (Vec<f64>, Vec<f64>)> = Default::default();
        for r in rows {
            let e = bins.entry(bin(r.1)).or_default();
            e.0.push(r.1);
            e.1.push(r.2);
        }
        for (b, (p, y)) in bins {
            st.push(t.to_string());
            sv.push(v.clone());
            pb.push(b);
            pm.push(kahan_mean(&p));
            ew.push(kahan_mean(&y));
            n.push(p.len() as i64);
        }
    }
    Table::default()
        .str("segment_type", &st)
        .str("segment_value", &sv)
        .i64("prob_bin", &pb)
        .f64("predicted_mean", &pm)
        .f64("empirical_win_rate", &ew)
        .i64("n", &n)
}
