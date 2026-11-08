//! Whole-History Rating: the retrospective production skill estimator.
//!
//! Coulom (2008), "Whole-History Rating: A Bayesian Rating System for Players
//! of Time-Varying Strength". Each appearance carries a latent rating r on the
//! logistic scale; a bout scores the fighter s ∈ [0, 1] with expectation
//! σ(r − r_opp). Consecutive appearances of one fighter are joined by a Wiener
//! prior N(0, w2·Δt); an anchor N(0, 1/ip) and `vg` virtual games against an
//! average opponent carry a fixed mass per fighter, spread over the career, so
//! an unbeaten record still has an interior maximum. Inference is Gauss–Seidel
//! coordinate ascent: one clipped Newton step per fighter per pass on the
//! tridiagonal block, re-centring the appearance mean after every pass as every
//! published fit has. With age drift a neutral fit first estimates the mean
//! change per day in eight age buckets (relative to under-24), and the model
//! is refit under that fixed curve. Output is mapped to `1500 + r·400/ln 10`.
//!
//! Legend
//!   r    rating of each appearance node, natural scale
//!   o    opponent node of each node; node 2i is fighter_a of bout i, 2i+1 fighter_b
//!   s    score of each node (1, ½, 0, or a graded win)
//!   ix   node ids grouped by fighter, chronological; fighter f owns ix[pt[f]..pt[f+1]]
//!   gp   days to the fighter's next node, aligned with ix (≥ 1)
//!   bn   age bucket of that transition, aligned with ix; −1 = unknown
//!   dr   drift per day per age bucket

use std::collections::HashMap;

use crate::bouts::{Bout, Corner, Outcome};
use crate::frame::{Day, Table};
use crate::history::{History, Row};
use crate::stats::psum;

/// Fit settings; `Settings::default()` is the published fit.
#[derive(Clone, Copy, Debug)]
pub struct Settings {
    /// Wiener variance per day, natural scale.
    pub w2: f64,
    /// Anchor prior variance.
    pub prior_var: f64,
    /// Virtual games per fighter.
    pub vg: f64,
    pub passes: usize,
    /// Newton step clip, natural units.
    pub clip: f64,
    /// Re-centre the appearance mean after every pass.
    pub center: bool,
    /// Grade the winner by the staged method score (else binary).
    pub graded: bool,
}

impl Default for Settings {
    fn default() -> Settings {
        Settings {
            w2: 0.0004,
            prior_var: 8.0,
            vg: 1.0,
            passes: 50,
            clip: 1.5,
            center: true,
            graded: true,
        }
    }
}

pub const ELO_ANCHOR: f64 = 1500.0;
pub const YEAR_DAYS: f64 = 365.2425;
/// 2000-01-01 as days since 1970; the fit's day origin.
const EPOCH: f64 = 10957.0;
/// `AGE_BIN_EDGES`: buckets <24, 24–27, …, 39–42, 42+.
const EDGES: [f64; 7] = [24.0, 27.0, 30.0, 33.0, 36.0, 39.0, 42.0];
const NB: usize = EDGES.len() + 1;

pub fn elo_per_nat() -> f64 {
    400.0 / 10f64.ln()
}

/// `np.digitize(x, EDGES)`: the number of edges ≤ x.
fn bucket(x: f64) -> usize {
    EDGES.iter().filter(|e| **e <= x).count()
}

/// Symmetric tridiagonal solve with `b` as both off-diagonals; `c`, `d` are scratch.
fn thomas(a: &[f64], b: &[f64], y: &[f64], x: &mut [f64], c: &mut [f64], d: &mut [f64]) {
    let n = a.len();
    if n == 1 {
        x[0] = if a[0] != 0.0 { y[0] / a[0] } else { 0.0 };
        return;
    }
    let mut be = a[0];
    c[0] = b[0] / be;
    d[0] = y[0] / be;
    for i in 1..n - 1 {
        be = a[i] - b[i - 1] * c[i - 1];
        c[i] = b[i] / be;
        d[i] = (y[i] - b[i - 1] * d[i - 1]) / be;
    }
    be = a[n - 1] - b[n - 2] * c[n - 2];
    d[n - 1] = (y[n - 1] - b[n - 2] * d[n - 2]) / be;
    x[n - 1] = d[n - 1];
    for i in (0..n - 1).rev() {
        x[i] = d[i] - c[i] * x[i + 1];
    }
}

/// The appearance graph of a bout list.
pub struct Graph {
    fighter: Vec<String>,
    event: Vec<String>,
    /// Days since 2000-01-01.
    day: Vec<f64>,
    o: Vec<usize>,
    s: Vec<f64>,
    pt: Vec<usize>,
    ix: Vec<usize>,
    gp: Vec<f64>,
    bn: Vec<i64>,
}

impl Graph {
    pub fn fighter(&self) -> &[String] {
        &self.fighter
    }
    pub fn event(&self) -> &[String] {
        &self.event
    }
    pub fn day(&self) -> &[f64] {
        &self.day
    }

    /// `_build_appearances`; `bouts` must be in `(day, event)` order, as `bouts::rated` returns them.
    /// Draws and no-contests have neutral WHR evidence; decided outcomes are participant wins.
    pub fn new(bouts: &[Bout], births: &HashMap<String, Day>, graded: bool) -> Graph {
        assert!(
            bouts
                .windows(2)
                .all(|b| (b[0].day, &b[0].event) <= (b[1].day, &b[1].event)),
            "WHR bouts must be ordered by day and event"
        );
        let n = 2 * bouts.len();
        let (mut fighter, mut event, mut day, mut o, mut s) = (
            Vec::with_capacity(n),
            Vec::with_capacity(n),
            Vec::with_capacity(n),
            Vec::with_capacity(n),
            Vec::with_capacity(n),
        );
        for (i, x) in bouts.iter().enumerate() {
            let w = if graded && !x.score().is_nan() {
                x.score()
            } else {
                1.0
            };
            let (sa, sb) = match x.outcome() {
                Outcome::Win(Corner::A) => (w, 1.0 - w),
                Outcome::Win(Corner::B) => (1.0 - w, w),
                Outcome::Draw | Outcome::NoContest => (0.5, 0.5),
            };
            for (f, sc, opp) in [(x.a(), sa, 2 * i + 1), (x.b(), sb, 2 * i)] {
                fighter.push(f.clone());
                event.push(x.event.clone());
                day.push(x.day as f64 - EPOCH);
                o.push(opp);
                s.push(sc);
            }
        }
        // Fighters in order of first appearance, nodes ascending: the Gauss–Seidel update order.
        let mut code: HashMap<&str, usize> = HashMap::new();
        let mut nodes: Vec<Vec<usize>> = Vec::new();
        for (u, f) in fighter.iter().enumerate() {
            let c = *code.entry(f.as_str()).or_insert_with(|| {
                nodes.push(Vec::new());
                nodes.len() - 1
            });
            nodes[c].push(u);
        }
        let mut age = vec![f64::NAN; n];
        let (mut pt, mut ix, mut gp, mut bn) = (
            vec![0],
            Vec::with_capacity(n),
            Vec::with_capacity(n),
            Vec::with_capacity(n),
        );
        for nd in &nodes {
            let birth = births.get(&fighter[nd[0]]).map(|b| *b as f64 - EPOCH);
            if let Some(b) = birth {
                for &u in nd {
                    age[u] = (day[u] - b) / YEAR_DAYS;
                }
            }
            for j in 0..nd.len() {
                ix.push(nd[j]);
                let (g, q) = if j + 1 < nd.len() {
                    let mid = (age[nd[j + 1]] + age[nd[j]]) / 2.0;
                    let q = if birth.is_some() && (14.0..=65.0).contains(&mid) {
                        bucket(mid) as i64
                    } else {
                        -1
                    };
                    ((day[nd[j + 1]] - day[nd[j]]).max(1.0), q)
                } else {
                    (0.0, -1)
                };
                gp.push(g);
                bn.push(q);
            }
            pt.push(ix.len());
        }
        Graph {
            fighter,
            event,
            day,
            o,
            s,
            pt,
            ix,
            gp,
            bn,
        }
    }

    /// Node ratings and the drift per day of each age bucket (all zero without age drift).
    pub fn fit(&self, p: &Settings, age_drift: bool) -> (Vec<f64>, Vec<f64>) {
        let (r, dr, _) = self.fit_traced(p, age_drift);
        (r, dr)
    }

    /// `fit` plus the largest change of any node rating over the last pass, natural units: the
    /// fit has converged when it is near zero, and nothing else in the loop tests for that.
    /// (The Newton step itself stays nonzero under re-centring, so it is no test.)
    pub fn fit_traced(&self, p: &Settings, age_drift: bool) -> (Vec<f64>, Vec<f64>, f64) {
        let (o, s, pt, ix, gp, bn) = (&self.o, &self.s, &self.pt, &self.ix, &self.gp, &self.bn);
        let n = o.len();
        let nf = pt.len() - 1;
        let (w2, ip, vg, cl) = (p.w2, 1.0 / p.prior_var, p.vg, p.clip);
        let lim = 25.0 / (elo_per_nat() * YEAR_DAYS);
        let mut r = vec![0.0f64; n];
        let mut dr = vec![0.0f64; NB];
        let tot = p.passes * if age_drift { 2 } else { 1 };
        let iw: Vec<f64> = gp.iter().map(|&q| 1.0 / (w2 * q)).collect();
        let km = (0..nf).map(|f| pt[f + 1] - pt[f]).max().unwrap_or(0);
        let z = || vec![0.0f64; km];
        let (mut rk, mut ok, mut pr, mut g, mut h, mut a, mut b, mut x) =
            (z(), z(), z(), z(), z(), z(), z(), z());
        let (mut e, mut c, mut d) = (z(), z(), z());
        let mut shift = 0.0f64;
        let mut before = r.clone();
        for pass in 0..tot {
            before.copy_from_slice(&r);
            for f in 0..nf {
                let lo = pt[f];
                let nd = &ix[lo..pt[f + 1]];
                let k = nd.len();
                for j in 0..k {
                    rk[j] = r[nd[j]];
                    ok[j] = r[o[nd[j]]];
                }
                for j in 0..k {
                    pr[j] = 1.0 / (1.0 + (-(rk[j] - ok[j])).exp());
                    g[j] = s[nd[j]] - pr[j];
                    h[j] = -pr[j] * (1.0 - pr[j]);
                }
                let an = ip / k as f64;
                for j in 0..k {
                    g[j] -= rk[j] * an;
                    h[j] -= an;
                }
                if vg > 0.0 {
                    let v = vg / k as f64;
                    for j in 0..k {
                        let p0 = 1.0 / (1.0 + (-rk[j]).exp());
                        g[j] += v * (0.5 - p0);
                        h[j] -= v * p0 * (1.0 - p0);
                    }
                }
                if k > 1 {
                    // numpy applied g[:-1] += … to the whole slice before g[1:] -= …,
                    // so each interior entry adds its own transition first.
                    let iv = &iw[lo..lo + k - 1];
                    for j in 0..k - 1 {
                        let mut res = rk[j + 1] - rk[j];
                        if age_drift && bn[lo + j] >= 0 {
                            res -= dr[bn[lo + j] as usize] * gp[lo + j];
                        }
                        e[j] = res * iv[j];
                    }
                    for j in 0..k - 1 {
                        g[j] += e[j];
                    }
                    for j in 0..k - 1 {
                        g[j + 1] -= e[j];
                    }
                    for j in 0..k - 1 {
                        h[j] -= iv[j];
                    }
                    for j in 0..k - 1 {
                        h[j + 1] -= iv[j];
                    }
                    for j in 0..k - 1 {
                        b[j] = -iv[j];
                    }
                }
                for j in 0..k {
                    a[j] = -h[j];
                }
                thomas(
                    &a[..k],
                    &b[..k.saturating_sub(1)],
                    &g[..k],
                    &mut x[..k],
                    &mut c,
                    &mut d,
                );
                for j in 0..k {
                    r[nd[j]] = rk[j] + x[j].clamp(-cl, cl);
                }
            }
            if p.center {
                let m = psum(&r) / n as f64;
                for v in r.iter_mut() {
                    *v -= m;
                }
            }
            shift = r
                .iter()
                .zip(&before)
                .fold(0.0, |m, (a, b)| m.max((a - b).abs()));
            if age_drift && pass == p.passes - 1 {
                dr = self.drift(&r, lim);
                r.fill(0.0);
            }
        }
        (r, dr, shift)
    }

    /// Mean rating change per day in each age bucket, relative to the first, clipped to ±25 Elo/yr.
    fn drift(&self, r: &[f64], lim: f64) -> Vec<f64> {
        let (pt, ix, gp, bn) = (&self.pt, &self.ix, &self.gp, &self.bn);
        let (mut cs, mut ds) = (vec![0.0f64; NB], vec![0.0f64; NB]);
        for f in 0..pt.len() - 1 {
            let lo = pt[f];
            let nd = &ix[lo..pt[f + 1]];
            if nd.len() < 2 {
                continue;
            }
            for q in 0..NB {
                let (mut ch, mut dy) = (vec![], vec![]);
                for j in 0..nd.len() - 1 {
                    if bn[lo + j] == q as i64 {
                        ch.push(r[nd[j + 1]] - r[nd[j]]);
                        dy.push(gp[lo + j]);
                    }
                }
                if !ch.is_empty() {
                    cs[q] += psum(&ch);
                    ds[q] += psum(&dy);
                }
            }
        }
        let raw: Vec<f64> = (0..NB)
            .map(|q| if ds[q] > 0.0 { cs[q] / ds[q] } else { 0.0 })
            .collect();
        let bl = if ds[0] > 0.0 { raw[0] } else { 0.0 };
        (0..NB)
            .map(|q| if ds[q] == 0.0 { 0.0 } else { raw[q] - bl }.clamp(-lim, lim))
            .collect()
    }
}

/// `project_age_rating`: a last rating carried through an inactive gap along the drift curve,
/// integrated piecewise across bucket edges over ages 14–65. Neutral without a birth date
/// or for a backward gap.
pub fn project(mu: f64, last: Day, target: Day, birth: Option<Day>, drift: &[f64]) -> f64 {
    let Some(birth) = birth else { return mu };
    if target <= last || drift.len() != NB || !drift.iter().all(|x| x.is_finite()) {
        return mu;
    }
    let (start, end) = (
        (last - birth) as f64 / YEAR_DAYS,
        (target - birth) as f64 / YEAR_DAYS,
    );
    let (mut out, mut cursor, stop) = (mu, start.max(14.0), end.min(65.0));
    while cursor < stop {
        let q = bucket(cursor);
        let seg = stop.min(EDGES.get(q).copied().unwrap_or(65.0));
        if seg <= cursor {
            break;
        }
        out += drift[q] * (seg - cursor);
        cursor = seg;
    }
    out
}

pub struct Whr {
    /// One row per appearance; `era` is NaN until `era::apply`.
    pub history: History,
    /// fighter, whr_last_event_date, mu_whr, mu_whr_age_activity_adjusted, whr_age_inactivity_adjustment.
    pub current: Table,
    /// Age drift per bucket, Elo per year.
    pub drift: Vec<f64>,
    /// Largest node rating change of the last pass, natural units (`Graph::fit_traced`).
    pub shift: f64,
}

/// The published fit: graded winners, age drift from `births`, projected to the last rated date.
pub fn run(rated: &[Bout], births: &HashMap<String, Day>) -> Whr {
    let graph = Graph::new(rated, births, true);
    let (r, dr, shift) = graph.fit_traced(&Settings::default(), true);
    let k = elo_per_nat();
    let drift: Vec<f64> = dr.iter().map(|x| x * k * YEAR_DAYS).collect();
    let history = History::new(
        (0..r.len())
            .map(|u| Row {
                fighter: graph.fighter[u].clone(),
                day: (graph.day[u] + EPOCH) as Day,
                event: graph.event[u].clone(),
                mu: ELO_ANCHOR + r[u] * k,
                era: f64::NAN,
            })
            .collect(),
    );
    let target = rated.iter().map(|x| x.day).max().unwrap_or(0);
    let last: Vec<&Row> = history
        .rows()
        .chunk_by(|x, y| x.fighter == y.fighter)
        .map(|c| c.last().unwrap())
        .collect();
    let adjusted: Vec<f64> = last
        .iter()
        .map(|x| project(x.mu, x.day, target, births.get(&x.fighter).copied(), &drift))
        .collect();
    let current = Table::default()
        .str(
            "fighter",
            &last.iter().map(|x| x.fighter.as_str()).collect::<Vec<_>>(),
        )
        .day(
            "whr_last_event_date",
            &last.iter().map(|x| Some(x.day)).collect::<Vec<_>>(),
        )
        .f64("mu_whr", &last.iter().map(|x| x.mu).collect::<Vec<_>>())
        .f64("mu_whr_age_activity_adjusted", &adjusted)
        .f64(
            "whr_age_inactivity_adjustment",
            &adjusted
                .iter()
                .zip(&last)
                .map(|(a, x)| a - x.mu)
                .collect::<Vec<_>>(),
        );
    Whr {
        history,
        current,
        drift,
        shift,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn admitted_outcomes_have_explicit_whr_evidence() {
        for (outcome, expected) in [
            (Outcome::Win(Corner::A), [0.9, 0.1]),
            (Outcome::Win(Corner::B), [0.1, 0.9]),
            (Outcome::Draw, [0.5, 0.5]),
            (Outcome::NoContest, [0.5, 0.5]),
        ] {
            let bout = Bout::new("Alice".into(), "Bob".into(), 1, outcome, 0.9).unwrap();
            let graph = Graph::new(&[bout], &HashMap::new(), true);
            for (actual, expected) in graph.s.iter().zip(expected) {
                assert!((actual - expected).abs() < 1e-15);
            }
        }
    }

    #[test]
    #[should_panic(expected = "WHR bouts must be ordered")]
    fn rejects_backward_appearance_paths() {
        let b =
            |day| Bout::new("Alice".into(), "Bob".into(), day, Outcome::Draw, f64::NAN).unwrap();
        Graph::new(&[b(2), b(1)], &HashMap::new(), true);
    }

    #[test]
    fn tridiagonal_known_solution() {
        let mut x = [0.0; 3];
        thomas(
            &[2.0, 3.0, 2.0],
            &[1.0, 1.0],
            &[1.0, 0.0, 3.0],
            &mut x,
            &mut [0.0; 3],
            &mut [0.0; 3],
        );
        for (actual, expected) in x.iter().zip([1.0, -1.0, 2.0]) {
            assert!((actual - expected).abs() < 1e-12);
        }
    }

    /// Eight fighters with strengths 0, 0.4, … 2.8 (natural scale), every pair meeting 30 times
    /// in a fixed pseudo-random order; the winner follows the logistic chance.
    fn synthetic() -> (Vec<Bout>, Vec<f64>) {
        let truth: Vec<f64> = (0..8).map(|i| 0.4 * i as f64).collect();
        let (mut state, mut day) = (12345u64, 0);
        let mut bouts = Vec::new();
        for _ in 0..30 {
            for i in 0..8 {
                for j in i + 1..8 {
                    state = state
                        .wrapping_mul(6364136223846793005)
                        .wrapping_add(1442695040888963407);
                    let u = (state >> 11) as f64 / (1u64 << 53) as f64;
                    let p = 1.0 / (1.0 + (-(truth[i] - truth[j])).exp());
                    let win = if u < p { Corner::A } else { Corner::B };
                    day += 1;
                    let name = |k: usize| format!("F{k}");
                    bouts.push(
                        Bout::new(name(i), name(j), day, Outcome::Win(win), f64::NAN).unwrap(),
                    );
                }
            }
        }
        (bouts, truth)
    }

    #[test]
    fn fit_converges_at_published_passes() {
        let (bouts, _) = synthetic();
        let g = Graph::new(&bouts, &HashMap::new(), false);
        let p = Settings::default();
        let (r, _, shift) = g.fit_traced(&p, false);
        let (long, _, _) = g.fit_traced(
            &Settings {
                passes: 10 * p.passes,
                ..p
            },
            false,
        );
        let gap = r
            .iter()
            .zip(&long)
            .map(|(a, b)| (a - b).abs())
            .fold(0.0, f64::max);
        assert!(
            shift < 1e-9,
            "ratings still move {shift:e} in pass {}",
            p.passes
        );
        assert!(gap < 1e-9, "ratings move {gap:e} when passes grow tenfold");
        let (_, _, early) = g.fit_traced(&Settings { passes: 5, ..p }, false);
        assert!(
            early > 1e-6,
            "five passes should not have converged: {early:e}"
        );
    }

    #[test]
    fn fit_recovers_simulated_strengths() {
        let (bouts, truth) = synthetic();
        let g = Graph::new(&bouts, &HashMap::new(), false);
        let (r, _, _) = g.fit_traced(&Settings::default(), false);
        let mut mean = [0.0; 8];
        let mut count = [0.0; 8];
        for (f, x) in g.fighter().iter().zip(&r) {
            let k: usize = f[1..].parse().unwrap();
            mean[k] += x;
            count[k] += 1.0;
        }
        let m: Vec<f64> = mean.iter().zip(&count).map(|(s, c)| s / c).collect();
        let (mt, mm) = (truth.iter().sum::<f64>() / 8.0, m.iter().sum::<f64>() / 8.0);
        let cov: f64 = truth.iter().zip(&m).map(|(t, x)| (t - mt) * (x - mm)).sum();
        let vt: f64 = truth.iter().map(|t| (t - mt).powi(2)).sum();
        let vm: f64 = m.iter().map(|x| (x - mm).powi(2)).sum();
        let corr = cov / (vt * vm).sqrt();
        assert!(corr > 0.95, "correlation {corr}: {m:?}");
    }
}
