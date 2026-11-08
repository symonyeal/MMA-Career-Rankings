//! Prime and Career Skill Mass: the two scores read straight off the WHR rating path.
//!
//! Prime (`symon_prime_score`) is the best mean rating over a fixed 3,652-day
//! window holding at least 13 appearances, shrunk toward its cohort by
//! empirical Bayes: with raw window means m_f, sampling variances v_f and
//! τ² = max(0, var(m) − mean(v)), the score is m̄ + τ²/(τ² + v_f)·(m_f − m̄).
//! Men and women are separate cohorts, since no bout joins the two graphs.
//!
//! Career Skill Mass (`career_skill_mass`) sums, over a fighter's calendar
//! years, the softened excess of the year's mean era rating over the year's
//! bar: the division-year contender line (5th best of a division-year with at
//! least 30 fighter-years), else the sport-wide one (`contender_bar` with 60),
//! else the whole-sample bar for a year of fewer than five fighters. The
//! softness is 0.175 times the year's population spread of annual means.
//! Policy and evidence: docs/DECISIONS.md.

use std::collections::HashMap;

use crate::divisions::female;
use crate::era::{contender_bar, year, CAREER_N};
use crate::frame::{Day, Frame, Table};
use crate::history::{History, Row};
use crate::policy::MIN_PERIODS;
use crate::stats::{kahan_mean, kahan_sum, mean, var, welford_std};

const WINDOW_DAYS: Day = 3652;
const MIN_FIGHTS: usize = MIN_PERIODS as usize;
const DIVISION_N: usize = 5;
const DIVISION_MIN_POPULATION: usize = 30;
const FIELD_MIN_POPULATION: usize = 5;
const SPREAD_FRACTION: f64 = 0.175;

/// The best window of one fighter's rows (path order): (raw mean, n, start, end, lo, hi).
///
/// A window ends only after the last bout of its end date, so a same-day loss cannot be cut off;
/// ties go to more appearances, then the earlier start.
fn best_window(rows: &[Row]) -> Option<(f64, usize, Day, Day, usize, usize)> {
    let d: Vec<Day> = rows.iter().map(|r| r.day).collect();
    let mut cs = vec![0.0];
    for r in rows {
        cs.push(cs.last().unwrap() + r.mu);
    }
    let mut best: Option<(f64, usize, Day, Day, usize, usize)> = None;
    let mut i = 0;
    for j in 0..d.len() {
        if j + 1 < d.len() && d[j + 1] == d[j] {
            continue;
        }
        while d[i] < d[j] - WINDOW_DAYS {
            i += 1;
        }
        let n = j - i + 1;
        if n < MIN_FIGHTS {
            continue;
        }
        let m = (cs[j + 1] - cs[i]) / n as f64;
        let better = match best {
            None => true,
            Some((bm, bn, bs, ..)) => m > bm || m == bm && (n > bn || n == bn && d[i] < bs),
        };
        if better {
            best = Some((m, n, d[i], d[j], i, j));
        }
    }
    best
}

/// `symon_prime_score` per gender cohort of `cur` (`fighter`, `gender`), on raw `mu_whr`.
pub fn prime(h: &History, cur: &Frame) -> Table {
    let (names, gender) = (cur.str("fighter"), cur.str("gender"));
    let mut out: Vec<(String, f64, f64, f64, usize, Day, Day, f64, f64)> = Vec::new();
    for g in [false, true] {
        let mut cohort: Vec<&String> = names
            .iter()
            .zip(&gender)
            .filter(|(_, x)| female(x) == g)
            .map(|p| p.0)
            .collect();
        cohort.sort();
        let mut rows = Vec::new();
        for f in cohort {
            let path = h.of(f);
            if path.len() < MIN_FIGHTS {
                continue;
            }
            if let Some((m, n, start, end, lo, hi)) = best_window(path) {
                let mu: Vec<f64> = path[lo..=hi].iter().map(|r| r.mu).collect();
                let within = if n > 1 { var(&mu, 1) } else { 0.0 };
                rows.push((f.clone(), m, n, start, end, within, within / n as f64));
            }
        }
        let raw: Vec<f64> = rows.iter().map(|r| r.1).collect();
        let sampling: Vec<f64> = rows.iter().map(|r| r.6).collect();
        let pooled = mean(&raw);
        let tau2 = if rows.len() < 2 {
            f64::NAN
        } else {
            (var(&raw, 1) - mean(&sampling)).max(0.0)
        };
        for (f, m, n, start, end, within, v) in rows {
            let k = if tau2.is_nan() {
                1.0
            } else if tau2 == 0.0 {
                if v == 0.0 {
                    1.0
                } else {
                    0.0
                }
            } else {
                tau2 / (tau2 + v)
            };
            out.push((f, pooled + k * (m - pooled), m, k, n, start, end, within, v));
        }
    }
    let col = |g: fn(&(String, f64, f64, f64, usize, Day, Day, f64, f64)) -> f64| {
        out.iter().map(g).collect::<Vec<_>>()
    };
    Table::default()
        .str(
            "fighter",
            &out.iter().map(|r| r.0.as_str()).collect::<Vec<_>>(),
        )
        .f64("symon_prime_score", &col(|r| r.1))
        .f64("symon_prime_raw_mean", &col(|r| r.2))
        .f64("symon_prime_shrinkage", &col(|r| r.3))
        .f64("symon_prime_window_fights", &col(|r| r.4 as f64))
        .day(
            "symon_prime_window_start",
            &out.iter().map(|r| Some(r.5)).collect::<Vec<_>>(),
        )
        .day(
            "symon_prime_window_end",
            &out.iter().map(|r| Some(r.6)).collect::<Vec<_>>(),
        )
        .f64("symon_prime_within_var", &col(|r| r.7))
        .f64("symon_prime_sampling_var", &col(|r| r.8))
}

/// One fighter-year of the career receipt.
#[derive(Clone, Debug)]
pub struct Year {
    pub fighter: String,
    pub year: i32,
    pub annual: f64,
    pub field: f64,
    pub excess: f64,
}

/// `positive_part`: s·log(1 + exp(x/s)), exact in both tails; the hard hinge at s = 0.
pub fn softplus(x: f64, s: f64) -> f64 {
    if s <= 0.0 {
        return x.max(0.0);
    }
    let z = x / s;
    s * if z > 30.0 {
        z
    } else if z < -30.0 {
        z.exp()
    } else {
        z.exp().ln_1p()
    }
}

/// `career_skill_years` on `rating(row)` (the era rating in production), `pools` from `divisions::pool`.
/// Fighter-year means of `rating(row)` (pandas `groupby([fighter, year]).mean()`), in path order.
pub fn annual(h: &History, rating: fn(&Row) -> f64) -> Vec<(&str, i32, f64)> {
    let mut out = Vec::new();
    let mut i = 0;
    while i < h.rows().len() {
        let (f, y) = (&h.rows()[i].fighter, year(h.rows()[i].day));
        let j = i + h.rows()[i..]
            .iter()
            .take_while(|r| &r.fighter == f && year(r.day) == y)
            .count();
        let v: Vec<f64> = h.rows()[i..j].iter().map(rating).collect();
        out.push((f.as_str(), y, kahan_mean(&v)));
        i = j;
    }
    out
}

/// `career_skill_years` on `rating(row)` (the era rating in production), `pools` from `pools`.
pub fn years(
    h: &History,
    rating: fn(&Row) -> f64,
    pools: &HashMap<String, Option<String>>,
) -> Vec<Year> {
    let mut out: Vec<Year> = annual(h, rating)
        .into_iter()
        .map(|(f, y, a)| Year {
            fighter: f.to_string(),
            year: y,
            annual: a,
            field: f64::NAN,
            excess: 0.0,
        })
        .collect();
    let all: Vec<f64> = out.iter().map(|x| x.annual).collect();
    let mut global = contender_bar(&all, CAREER_N);
    if global.is_nan() {
        global = all.iter().copied().fold(f64::NAN, f64::max);
    }
    let mut by_year: HashMap<i32, Vec<f64>> = HashMap::new();
    let mut by_division: HashMap<(&str, i32), Vec<f64>> = HashMap::new();
    for x in &out {
        by_year.entry(x.year).or_default().push(x.annual);
        if let Some(Some(d)) = pools.get(&x.fighter) {
            by_division
                .entry((d.as_str(), x.year))
                .or_default()
                .push(x.annual);
        }
    }
    let bar: HashMap<i32, (f64, f64)> = by_year
        .iter()
        .map(|(y, v)| {
            let b = contender_bar(v, CAREER_N);
            let b = if v.len() < FIELD_MIN_POPULATION || b.is_nan() {
                global
            } else {
                b
            };
            (*y, (b, SPREAD_FRACTION * welford_std(v, 0)))
        })
        .collect();
    let local: HashMap<(&str, i32), f64> = by_division
        .into_iter()
        .filter(|(_, v)| v.len() >= DIVISION_MIN_POPULATION)
        .map(|(k, v)| (k, contender_bar(&v, DIVISION_N)))
        .collect();
    for x in &mut out {
        let (b, s) = bar[&x.year];
        let d = pools.get(&x.fighter).and_then(|d| d.as_deref());
        x.field = d
            .and_then(|d| local.get(&(d, x.year)))
            .copied()
            .filter(|v| !v.is_nan())
            .unwrap_or(b);
        x.excess = softplus(x.annual - x.field, if s.is_nan() { 0.0 } else { s });
    }
    out
}

/// `career_skill_mass`: per-fighter sums of `years` with their shape, as the `symon_career_*` columns.
pub fn career(years: &[Year]) -> Table {
    let mut groups: Vec<&[Year]> = Vec::new();
    let mut i = 0;
    while i < years.len() {
        let j = i + years[i..]
            .iter()
            .take_while(|x| x.fighter == years[i].fighter)
            .count();
        groups.push(&years[i..j]);
        i = j;
    }
    let excess: Vec<Vec<f64>> = groups
        .iter()
        .map(|g| g.iter().map(|x| x.excess).collect())
        .collect();
    let score: Vec<f64> = excess.iter().map(|e| kahan_sum(e)).collect();
    let mut sorted = score.clone();
    sorted.sort_by(|a, b| b.total_cmp(a));
    let rank: Vec<i64> = score
        .iter()
        .map(|s| 1 + sorted.partition_point(|x| x > s) as i64)
        .collect();
    let ints = |g: &dyn Fn(&[Year]) -> i64| groups.iter().map(|x| g(x)).collect::<Vec<i64>>();
    Table::default()
        .str(
            "fighter",
            &groups
                .iter()
                .map(|g| g[0].fighter.as_str())
                .collect::<Vec<_>>(),
        )
        .i64("symon_career_rank", &rank)
        .f64("symon_career_skill_mass", &score)
        .i64("symon_career_active_years", &ints(&|g| g.len() as i64))
        .i64(
            "symon_career_contributing_years",
            &ints(&|g| g.iter().filter(|x| x.annual >= x.field).count() as i64),
        )
        .f64(
            "symon_career_peak_year_excess",
            &excess
                .iter()
                .map(|e| e.iter().copied().fold(f64::NAN, f64::max))
                .collect::<Vec<_>>(),
        )
        .f64(
            "symon_career_mean_year_excess",
            &excess.iter().map(|e| kahan_mean(e)).collect::<Vec<_>>(),
        )
        .i64(
            "symon_career_first_year",
            &ints(&|g| g.iter().map(|x| x.year).min().unwrap() as i64),
        )
        .i64(
            "symon_career_last_year",
            &ints(&|g| g.iter().map(|x| x.year).max().unwrap() as i64),
        )
}

/// Fighter → career pool (`division_labels`) from `cur` (`fighter`, `career_division`, `gender`).
pub fn pools(cur: &Frame) -> HashMap<String, Option<String>> {
    let (f, d, g) = (
        cur.str("fighter"),
        cur.str("career_division"),
        cur.str("gender"),
    );
    let mut out = HashMap::new();
    for i in 0..f.len() {
        out.entry(f[i].clone())
            .or_insert_with(|| crate::divisions::pool(&d[i], &g[i]));
    }
    out
}
