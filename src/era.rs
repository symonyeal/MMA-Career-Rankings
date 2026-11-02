//! Era-adjusted ratings: every rating read against its own year's contender line.
//!
//! Let E_g(y) be the contender line of gender g in year y (`contender_bar`
//! with n = 60 over g's fighter-year mean ratings) and
//! E_g* = Σ_y n_g(y) E_g(y) / Σ_y n_g(y) its mean over g's n_g(y) fighter-years. Then
//!
//! `mu_era = mu_whr − (E_g(y) − E_g*)`.
//!
//! Adding c(y) to every rating of g in year y moves mu_era by a constant, so a
//! drift of the scale over time cannot reach a board that reads mu_era
//! (docs/DECISIONS.md, "The score reads era-adjusted ratings").

use std::collections::{BTreeMap, HashMap};

use crate::frame::civil;
use crate::history::History;
use crate::stats::{kahan_mean, psum};

/// `DEFAULT_CAREER_REFERENCE = "contender:60"`.
pub const CAREER_N: usize = 60;

/// `year_reference("contender:n")` of one year: the k-th largest value,
/// k = min(n, max(1, ⌈0.10·len⌉)); NaN for an empty year.
pub fn contender_bar(v: &[f64], n: usize) -> f64 {
    let mut s: Vec<f64> = v.iter().copied().filter(|x| !x.is_nan()).collect();
    if s.is_empty() {
        return f64::NAN;
    }
    s.sort_by(|a, b| b.total_cmp(a));
    let k = n.min(((0.10 * v.len() as f64).ceil() as usize).max(1));
    s[k - 1]
}

pub fn year(day: crate::frame::Day) -> i32 {
    civil(day).0
}

/// Fighter-year means of `value(row)` (pandas `groupby([fighter, year]).mean()`, Kahan),
/// grouped by year: `year -> [(fighter, mean)]` in fighter order.
pub fn annual<F: Fn(&crate::history::Row) -> f64>(
    rows: &[&crate::history::Row],
    value: F,
) -> BTreeMap<i32, Vec<(String, f64)>> {
    let mut g: BTreeMap<(i32, &str), Vec<f64>> = BTreeMap::new();
    for r in rows {
        g.entry((year(r.day), &r.fighter))
            .or_default()
            .push(value(r));
    }
    let mut out: BTreeMap<i32, Vec<(String, f64)>> = BTreeMap::new();
    let mut keys: Vec<_> = g.into_iter().collect();
    keys.sort_by(|a, b| (a.0 .1, a.0 .0).cmp(&(b.0 .1, b.0 .0)));
    for ((y, f), v) in keys {
        out.entry(y)
            .or_default()
            .push((f.to_string(), kahan_mean(&v)));
    }
    out
}

/// Sets `era` on every row: mu − (E_g(y) − E_g*), genders split by `female(fighter)`.
pub fn apply<F: Fn(&str) -> bool>(h: &mut History, female: F) {
    let mut shift: HashMap<(bool, i32), f64> = HashMap::new();
    for g in [false, true] {
        let rows: Vec<&crate::history::Row> =
            h.rows.iter().filter(|r| female(&r.fighter) == g).collect();
        let a = annual(&rows, |r| r.mu);
        let e: Vec<(i32, f64, f64)> = a
            .iter()
            .map(|(y, v)| {
                (
                    *y,
                    contender_bar(&v.iter().map(|p| p.1).collect::<Vec<_>>(), CAREER_N),
                    v.len() as f64,
                )
            })
            .collect();
        let en: Vec<f64> = e.iter().map(|(_, b, n)| b * n).collect();
        let n: Vec<f64> = e.iter().map(|(_, _, n)| *n).collect();
        let star = psum(&en) / psum(&n);
        for (y, b, _) in e {
            shift.insert((g, y), b - star);
        }
    }
    for i in 0..h.rows.len() {
        let g = female(&h.rows[i].fighter);
        let r = &mut h.rows[i];
        r.era = r.mu - shift[&(g, year(r.day))];
    }
}
