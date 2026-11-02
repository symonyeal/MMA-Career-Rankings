//! Leak-free pre-fight forecasts for UFC bouts, scored against the no-vig betting price.
//!
//! Each calendar year Y ≥ 2012 is forecast by models fitted on bouts dated
//! before 1 January Y, and every feature reads only earlier dates. Features
//! read only bouts from promotions the corpus enumerates card by card
//! (`ROSTER`), so a fighter's recorded past does not depend on their future;
//! Glicko-2 is re-run on that history unchanged. Every model is antisymmetric
//! in the corners (docs/DECISIONS.md).
//!
//! Legend: a, b the corners, d_x = x_a − x_b; y = 1 if a won; p_g Glicko-2,
//! p_m market (no-vig), p_1 L2 logistic regression without intercept on the
//! d_x features (C = 1, rows mirrored), p_3 p_1's design plus logit(p_m),
//! fitted on bouts with odds; ll, br log loss and Brier score. Intervals are
//! 95% event-cluster bootstraps, B = 2000, NumPy `default_rng(20261027)`.

use std::collections::{BTreeMap, HashMap};
use std::path::Path;

use serde_json::{json, Value};

use crate::bouts::Bout;
use crate::era::year;
use crate::frame::{parse_day, Day, Frame};
use crate::glicko::{engine, predict};
use crate::stats::{kahan_mean, psum, py_round, quantile_sorted, Pcg64};

const ROSTER: [&str; 9] = [
    "UFC",
    "UFC (pre-unified)",
    "Ultimate Fighting Championship (UFC)",
    "PRIDE",
    "WEC",
    "Strikeforce",
    "Affliction",
    "Bellator",
    "RIZIN",
];
const Y0: i32 = 2012;
const SEED: u32 = 20261027;
const B: usize = 2000;
const EPS: f64 = 1e-6;
const M15: f64 = 900.0;
const JULIAN_YEAR_DAYS: f64 = 365.25;

fn logit(p: f64) -> f64 {
    let p = p.clamp(EPS, 1.0 - EPS);
    (p / (1.0 - p)).ln()
}

/// Earlier record at (fighter, day): bouts, wins, streak, days since last bout, KO losses in 730 days.
#[derive(Clone, Copy)]
struct Rec {
    n: f64,
    w: f64,
    streak: f64,
    lay: f64,
    ko2: f64,
}

fn records(cb: &[&Bout]) -> HashMap<(String, Day), Rec> {
    let mut d: BTreeMap<(&str, Day), (f64, f64, f64, f64)> = BTreeMap::new();
    for side in 0..2 {
        for x in cb {
            let f = if side == 0 { &x.a } else { &x.b };
            if f.is_empty() {
                continue;
            }
            let w = if x.draw {
                0.5
            } else {
                f64::from(u8::from(&x.winner == f))
            };
            let kol = f64::from(u8::from(&x.loser == f && x.method == "KO/TKO"));
            let e = d
                .entry((f, x.day))
                .or_insert((0.0, 0.0, 0.0, f64::INFINITY));
            *e = (e.0 + 1.0, e.1 + w, e.2 + kol, e.3.min(w));
        }
    }
    let mut out = HashMap::new();
    let (mut cur, mut n, mut w, mut st, mut prev, mut kd): (
        &str,
        f64,
        f64,
        i64,
        Option<Day>,
        Vec<Day>,
    ) = ("", 0.0, 0.0, 0, None, vec![]);
    for (i, (&(f, t), &(dn, dw, dk, wl))) in d.iter().enumerate() {
        if i == 0 || f != cur {
            (cur, n, w, st, prev, kd) = (f, 0.0, 0.0, 0, None, vec![]);
        }
        let lo = kd.partition_point(|&k| k < t - 730);
        out.insert(
            (f.to_string(), t),
            Rec {
                n,
                w,
                streak: st as f64,
                lay: prev.map_or(f64::NAN, |p| (t - p) as f64),
                ko2: (kd.len() - lo) as f64,
            },
        );
        (n, w, prev) = (n + dn, w + dw, Some(t));
        st = if wl == 1.0 {
            if st >= 0 {
                st + 1
            } else {
                1
            }
        } else if wl == 0.0 {
            if st <= 0 {
                st - 1
            } else {
                -1
            }
        } else {
            0
        };
        kd.extend(std::iter::repeat_n(t, dk as usize));
    }
    out
}

/// UFC in-fight rates per (fighter, day) from strictly earlier bouts, each shrunk
/// toward the pre-2012 population rate with 15 minutes (or the matching attempt count) of prior weight;
/// also the debut means (fighters with no earlier UFC bout) that fill unseen fighters.
fn ufc_rates(
    snapshot: &Path,
    secs: &HashMap<String, (Day, f64)>,
) -> (HashMap<(String, Day), ([f64; 11], f64)>, [f64; 11]) {
    let rd = Frame::read(&snapshot.join("canonical_rounds.parquet"));
    let q = [
        "sig_str_landed",
        "sig_str_attempted",
        "td_landed",
        "td_attempted",
        "sub_att",
        "ctrl_seconds",
        "kd",
    ];
    let cols: Vec<Vec<f64>> = q.iter().map(|c| rd.f64(c)).collect();
    let (url, fighter) = (rd.str("fight_url"), rd.str("fighter"));
    let mut g: BTreeMap<(&str, &str), [f64; 7]> = BTreeMap::new();
    for i in 0..rd.len() {
        let e = g.entry((&url[i], &fighter[i])).or_insert([0.0; 7]);
        for (k, c) in cols.iter().enumerate() {
            if !c[i].is_nan() {
                e[k] += c[i];
            }
        }
    }
    // Own totals, opponent totals and seconds, summed per (fighter, day): 15 columns.
    let mut by: BTreeMap<(String, Day), [f64; 15]> = BTreeMap::new();
    let keys: Vec<_> = g.keys().copied().collect();
    let mut i = 0;
    while i < keys.len() {
        let j = i + keys[i..].iter().take_while(|k| k.0 == keys[i].0).count();
        if let Some(&(day, s)) = secs.get(keys[i].0) {
            for x in &keys[i..j] {
                for o in &keys[i..j] {
                    if x.1 == o.1 {
                        continue;
                    }
                    let e = by.entry((x.1.to_string(), day)).or_insert([0.0; 15]);
                    for k in 0..7 {
                        e[k] += g[x][k];
                        e[7 + k] += g[o][k];
                    }
                    e[14] += s;
                }
            }
        }
        i = j;
    }
    let y0 = parse_day(&format!("{Y0}-01-01"));
    let mut pre = [0.0; 15];
    for ((_, d), v) in &by {
        if *d < y0 {
            for k in 0..15 {
                pre[k] += v[k];
            }
        }
    }
    // Column indices: sl sa tl ta sub ctrl kd, then o-, then s.
    let (sl, sa, tl, ta, sub, ctrl, kd, s) = (0, 1, 2, 3, 4, 5, 6, 14);
    let o = |k: usize| 7 + k;
    let wsa = pre[sa] / pre[s] * M15;
    let wta = pre[ta] / pre[s] * M15;
    let wosa = pre[o(sa)] / pre[s] * M15;
    let wota = pre[o(ta)] / pre[s] * M15;
    let mut out = HashMap::new();
    let (mut cur, mut acc, mut n): (&str, [f64; 15], f64) = ("", [0.0; 15], 0.0);
    for ((f, d), v) in &by {
        if f != cur {
            (cur, acc, n) = (f, [0.0; 15], 0.0);
        }
        let u = acc;
        let rate =
            |num: usize, den: usize, w: f64| (u[num] + pre[num] / pre[den] * w) / (u[den] + w);
        let r = [
            rate(sl, s, M15) * 60.0,
            rate(o(sl), s, M15) * 60.0,
            rate(sl, sa, wsa),
            1.0 - rate(o(sl), o(sa), wosa),
            rate(tl, s, M15) * 900.0,
            rate(tl, ta, wta),
            1.0 - rate(o(tl), o(ta), wota),
            rate(sub, s, M15) * 900.0,
            rate(ctrl, s, M15),
            rate(kd, s, M15) * 900.0,
            rate(o(kd), s, M15) * 900.0,
        ];
        out.insert((f.clone(), *d), (r, n));
        for k in 0..15 {
            acc[k] += v[k];
        }
        n += 1.0;
    }
    let mut debut = [0.0; 11];
    for (k, x) in debut.iter_mut().enumerate() {
        let v: Vec<f64> = by
            .keys()
            .map(|key| &out[key])
            .filter(|(_, n)| *n == 0.0)
            .map(|(r, _)| r[k])
            .collect();
        *x = psum(&v) / v.len() as f64;
    }
    (out, debut)
}

/// NumPy `std(axis=0)` of the rows `a` and their mirror `−a`, summed row by row.
fn mirrored_sd(a: &[Vec<f64>]) -> Vec<f64> {
    let k = a[0].len();
    let n = 2.0 * a.len() as f64;
    let rows = || {
        a.iter()
            .map(|r| (r, 1.0))
            .chain(a.iter().map(|r| (r, -1.0)))
    };
    let mut m = vec![0.0; k];
    for (r, s) in rows() {
        for j in 0..k {
            m[j] += s * r[j];
        }
    }
    m.iter_mut().for_each(|x| *x /= n);
    let mut v = vec![0.0; k];
    for (r, s) in rows() {
        for j in 0..k {
            let d = s * r[j] - m[j];
            v[j] += d * d;
        }
    }
    v.iter().map(|x| (x / n).sqrt() + 1e-12).collect()
}

/// w minimising C·Σ log loss + ½‖w‖² over rows a and their mirror −a, by Newton steps.
fn fit(a: &[Vec<f64>], y: &[f64]) -> Vec<f64> {
    let k = a[0].len();
    let rows: Vec<(Vec<f64>, f64)> = a
        .iter()
        .zip(y)
        .map(|(r, &y)| (r.clone(), y))
        .chain(
            a.iter()
                .zip(y)
                .map(|(r, &y)| (r.iter().map(|x| -x).collect(), 1.0 - y)),
        )
        .collect();
    let mut w = vec![0.0; k];
    for _ in 0..50 {
        let mut g = w.clone();
        let mut h = vec![vec![0.0; k]; k];
        let mut gs = vec![0.0; k];
        for (r, y) in &rows {
            let z: f64 = r.iter().zip(&w).map(|(x, w)| x * w).sum();
            let p = 1.0 / (1.0 + (-z).exp());
            let c = p * (1.0 - p);
            for i in 0..k {
                gs[i] += r[i] * (p - y);
                for j in 0..k {
                    h[i][j] += r[i] * c * r[j];
                }
            }
        }
        for i in 0..k {
            g[i] += gs[i];
            h[i][i] += 1.0;
        }
        let step = solve(h, g);
        for i in 0..k {
            w[i] -= step[i];
        }
        if step.iter().fold(0.0f64, |m, s| m.max(s.abs())) < 1e-10 {
            break;
        }
    }
    w
}

/// Hx = g by Gaussian elimination with partial pivoting.
fn solve(mut h: Vec<Vec<f64>>, mut g: Vec<f64>) -> Vec<f64> {
    let k = g.len();
    for c in 0..k {
        let p = (c..k)
            .max_by(|&i, &j| h[i][c].abs().total_cmp(&h[j][c].abs()))
            .unwrap();
        h.swap(c, p);
        g.swap(c, p);
        for r in c + 1..k {
            let f = h[r][c] / h[c][c];
            for j in c..k {
                h[r][j] -= f * h[c][j];
            }
            g[r] -= f * g[c];
        }
    }
    let mut x = vec![0.0; k];
    for c in (0..k).rev() {
        let s: f64 = (c + 1..k).map(|j| h[c][j] * x[j]).sum();
        x[c] = (g[c] - s) / h[c][c];
    }
    x
}

fn prob(r: &[f64], sd: &[f64], w: &[f64]) -> f64 {
    let z: f64 = r.iter().zip(sd).zip(w).map(|((x, s), w)| x / s * w).sum();
    1.0 / (1.0 + (-z).exp())
}

/// One decided UFC bout with its forecasts.
struct Test {
    event: String,
    day: Day,
    y: f64,
    p_g: f64,
    p_m: Option<f64>,
    f: Vec<f64>,
    p_1: f64,
    p_3: f64,
}

fn bout_frame(snapshot: &Path, staged: &[Bout], births: &HashMap<String, Day>) -> Vec<Test> {
    let cf = Frame::read(&snapshot.join("canonical_fights.parquet"));
    let (url, event, a, b, winner) = (
        cf.str("fight_url"),
        cf.str("event_name"),
        cf.str("fighter_a"),
        cf.str("fighter_b"),
        cf.str("winner"),
    );
    let day: Vec<Day> = cf
        .day("event_date")
        .into_iter()
        .map(Option::unwrap)
        .collect();
    let (excl, draw, nc) = (cf.bool("is_excluded"), cf.bool("is_draw"), cf.bool("is_nc"));
    let (er, et) = (cf.f64("end_round"), cf.f64("end_time_seconds"));
    let secs: HashMap<String, (Day, f64)> = (0..cf.len())
        .map(|i| (url[i].clone(), (day[i], (er[i] - 1.0) * 300.0 + et[i])))
        .collect();

    let cb: Vec<&Bout> = staged
        .iter()
        .filter(|x| x.model && !x.nc && (x.source == "ufc" || ROSTER.contains(&x.org.as_str())))
        .collect();
    let rec = records(&cb);
    let (rates, debut) = ufc_rates(snapshot, &secs);
    let g = engine(&cb);
    let mut gl: HashMap<(&str, Day), (f64, f64)> = HashMap::new();
    for r in &g.rows {
        gl.entry((g.names[r.fighter].as_str(), r.day))
            .or_insert(r.pre);
    }
    let fi = Frame::read(&snapshot.join("canonical_fighters.parquet"));
    let mut body: HashMap<String, (f64, f64)> = HashMap::new();
    for ((f, h), r) in fi
        .str("fighter")
        .into_iter()
        .zip(fi.f64("height_inches"))
        .zip(fi.f64("reach_inches"))
    {
        body.entry(f).or_insert((h, r));
    }
    let od = Frame::read(&snapshot.join("odds_lines.parquet"));
    let mut odds: HashMap<String, (String, f64)> = HashMap::new();
    for (((u, q), fa), p) in od
        .str("fight_url")
        .into_iter()
        .zip(od.str("odds_data_quality"))
        .zip(od.str("fighter_a"))
        .zip(od.f64("implied_prob_a_no_vig"))
    {
        if q == "ok" && (0.001..=0.999).contains(&p) {
            odds.insert(u, (fa, p));
        }
    }

    let d = |x: f64, y: f64| if (x - y).is_nan() { 0.0 } else { x - y };
    // np.maximum keeps NaN.
    let over32 = |v: f64| if v.is_nan() { v } else { (v - 32.0).max(0.0) };
    let mut out = Vec::new();
    for i in (0..cf.len()).filter(|&i| !excl[i] && !draw[i] && !nc[i] && !winner[i].is_empty()) {
        let side = |f: &str| {
            let r = rec.get(&(f.to_string(), day[i])).copied().unwrap_or(Rec {
                n: 0.0,
                w: 0.0,
                streak: 0.0,
                lay: f64::NAN,
                ko2: 0.0,
            });
            let (u, nufc) = rates
                .get(&(f.to_string(), day[i]))
                .copied()
                .unwrap_or((debut, 0.0));
            let (mu, phi) = gl.get(&(f, day[i])).copied().unwrap_or((1500.0, 350.0));
            let age = births
                .get(f)
                .map_or(f64::NAN, |dob| (day[i] - dob) as f64 / JULIAN_YEAR_DAYS);
            let (ht, rch) = body.get(f).copied().unwrap_or((f64::NAN, f64::NAN));
            (r, u, nufc, (mu, phi), age, ht, rch)
        };
        let (ra, ua, na, ga, aa, ha, ca) = side(&a[i]);
        let (rb, ub, nb, gb, ab, hb, cb_) = side(&b[i]);
        let p_g = predict(ga, gb);
        let wr = |r: &Rec| (r.w + 2.0) / (r.n + 4.0);
        let lay = |r: &Rec| if r.lay.is_nan() { 0.0 } else { r.lay };
        let mut f = vec![
            logit(p_g),
            d(ga.1, gb.1),
            d(aa, ab),
            d(over32(aa), over32(ab)),
            d(ha, hb),
            d(ca, cb_),
            d(lay(&ra).ln_1p(), lay(&rb).ln_1p()),
            d(
                f64::from(u8::from(ra.lay > 365.0)),
                f64::from(u8::from(rb.lay > 365.0)),
            ),
            d(ra.n.ln_1p(), rb.n.ln_1p()),
            wr(&ra) - wr(&rb),
            d(ra.streak, rb.streak),
            d(ra.ko2, rb.ko2),
            d(na.ln_1p(), nb.ln_1p()),
        ];
        f.extend((0..11).map(|k| d(ua[k], ub[k])));
        let p_m = odds.get(&url[i]).map(|(fa, p)| {
            assert_eq!(fa, &a[i], "odds corner order differs");
            *p
        });
        f.push(logit(p_m.unwrap_or(0.5)));
        out.push(Test {
            event: event[i].clone(),
            day: day[i],
            y: f64::from(u8::from(winner[i] == a[i])),
            p_g,
            p_m,
            f,
            p_1: f64::NAN,
            p_3: f64::NAN,
        });
    }
    out
}

/// p_1 and p_3: each test year forecast by fits on bouts dated before that year.
fn walk_forward(x: &mut [Test]) {
    let last = x.iter().map(|t| year(t.day)).max().unwrap();
    let m = x[0].f.len() - 1;
    for yy in Y0..=last {
        for three in [false, true] {
            let cols = |t: &Test| -> Vec<f64> {
                if three {
                    std::iter::once(t.f[m])
                        .chain(t.f[..m].iter().copied())
                        .collect()
                } else {
                    t.f[..m].to_vec()
                }
            };
            let train: Vec<&Test> = x
                .iter()
                .filter(|t| year(t.day) < yy && (!three || t.p_m.is_some()))
                .collect();
            let a: Vec<Vec<f64>> = train.iter().map(|t| cols(t)).collect();
            let sd = mirrored_sd(&a);
            let scaled: Vec<Vec<f64>> = a
                .iter()
                .map(|r| r.iter().zip(&sd).map(|(x, s)| x / s).collect())
                .collect();
            let w = fit(&scaled, &train.iter().map(|t| t.y).collect::<Vec<_>>());
            for t in x.iter_mut().filter(|t| year(t.day) == yy) {
                let p = prob(&cols(t), &sd, &w);
                if three {
                    t.p_3 = p
                } else {
                    t.p_1 = p
                }
            }
        }
    }
}

/// Per bout: log loss, Brier, winner picked (a coin's ½ counts as half).
fn score(p: f64, y: f64) -> [f64; 3] {
    let p = p.clamp(EPS, 1.0 - EPS);
    [
        -(y * p.ln() + (1.0 - y) * (1.0 - p).ln()),
        (p - y) * (p - y),
        if p == 0.5 {
            0.5
        } else {
            f64::from(u8::from((p > 0.5) == (y == 1.0)))
        },
    ]
}

/// 95% cluster-bootstrap interval of mean(v), resampling whole events.
fn interval(v: &[f64], ev: &[&str], rng: &mut Pcg64) -> [f64; 2] {
    let mut code: HashMap<&str, usize> = HashMap::new();
    let (mut sv, mut sn) = (Vec::<f64>::new(), Vec::<i64>::new());
    for (x, e) in v.iter().zip(ev) {
        let n = code.len();
        let k = *code.entry(e).or_insert(n);
        if k == sv.len() {
            sv.push(0.0);
            sn.push(0);
        }
        sv[k] += x;
        sn[k] += 1;
    }
    let n = sv.len();
    let mut mm: Vec<f64> = (0..B)
        .map(|_| {
            let ix: Vec<usize> = (0..n).map(|_| rng.below(n as u32)).collect();
            psum(&ix.iter().map(|&i| sv[i]).collect::<Vec<_>>())
                / ix.iter().map(|&i| sn[i]).sum::<i64>() as f64
        })
        .collect();
    mm.sort_by(f64::total_cmp);
    [
        quantile_sorted(&mm, 2.5 / 100.0),
        quantile_sorted(&mm, 97.5 / 100.0),
    ]
}

fn r4(x: f64) -> Value {
    json!(py_round(x, 4))
}

/// `[bin, mean forecast, win rate, n]` over both corners, ten bins.
fn cal(p: &[f64], y: &[f64]) -> Value {
    let mut bins: BTreeMap<i64, (Vec<f64>, Vec<f64>)> = BTreeMap::new();
    for (pp, yy) in p
        .iter()
        .copied()
        .chain(p.iter().map(|p| 1.0 - p))
        .zip(y.iter().copied().chain(y.iter().map(|y| 1.0 - y)))
    {
        let e = bins.entry(((pp * 10.0) as i64).min(9)).or_default();
        e.0.push(pp);
        e.1.push(yy);
    }
    Value::Array(
        bins.into_iter()
            .map(|(b, (p, y))| json!([b, r4(kahan_mean(&p)), r4(kahan_mean(&y)), p.len()]))
            .collect(),
    )
}

/// The site's `market` block: the forecast benchmark on test bouts with odds, beside
/// the count, favourite win rate and years of every priced UFC bout in the whole table.
pub fn market(snapshot: &Path, staged: &[Bout], births: &HashMap<String, Day>) -> Value {
    let mut x = bout_frame(snapshot, staged, births);
    walk_forward(&mut x);
    let e: Vec<&Test> = x
        .iter()
        .filter(|t| year(t.day) >= Y0 && t.p_m.is_some())
        .collect();
    let y: Vec<f64> = e.iter().map(|t| t.y).collect();
    let ev: Vec<&str> = e.iter().map(|t| t.event.as_str()).collect();
    let forecasts: [(&str, &str, Vec<f64>); 5] = [
        ("p_0", "Coin flip", vec![0.5; e.len()]),
        ("p_g", "Rating alone", e.iter().map(|t| t.p_g).collect()),
        ("p_1", "Stats model", e.iter().map(|t| t.p_1).collect()),
        (
            "p_m",
            "Betting market",
            e.iter().map(|t| t.p_m.unwrap()).collect(),
        ),
        (
            "p_3",
            "Market + stats model",
            e.iter().map(|t| t.p_3).collect(),
        ),
    ];
    let sc: Vec<Vec<[f64; 3]>> = forecasts
        .iter()
        .map(|(_, _, p)| p.iter().zip(&y).map(|(&p, &y)| score(p, y)).collect())
        .collect();
    let mut rng = Pcg64::new(SEED);
    let rows: Vec<Value> = forecasts
        .iter()
        .zip(&sc)
        .map(|((c, label, _), s)| {
            // Column means of an (n, 3) array accumulate row by row.
            let mean = |k: usize| s.iter().fold(0.0, |a, r| a + r[k]) / s.len() as f64;
            let gap: Vec<f64> = s.iter().zip(&sc[3]).map(|(r, m)| r[0] - m[0]).collect();
            let ci = if *c == "p_m" {
                [0.0, 0.0]
            } else {
                interval(&gap, &ev, &mut rng)
            };
            json!([
                label,
                r4(mean(0)),
                r4(mean(1)),
                r4(mean(2)),
                r4(psum(&gap) / gap.len() as f64),
                r4(ci[0]),
                r4(ci[1])
            ])
        })
        .collect();

    // Every priced UFC bout of the whole table with a known winner.
    let mut won: HashMap<&str, Vec<&str>> = HashMap::new();
    for b in staged
        .iter()
        .filter(|b| !b.excluded && !b.draw && !b.nc && !b.winner.is_empty())
    {
        won.entry(&b.url).or_default().push(&b.winner);
    }
    let od = Frame::read(&snapshot.join("odds_lines.parquet"));
    let (ou, oq, oa, op, od_day) = (
        od.str("fight_url"),
        od.str("odds_data_quality"),
        od.str("fighter_a"),
        od.f64("implied_prob_a_no_vig"),
        od.day("event_date"),
    );
    let (mut fav, mut years) = (Vec::new(), Vec::new());
    for i in 0..od.len() {
        if oq[i] != "ok" || !(0.001..=0.999).contains(&op[i]) {
            continue;
        }
        for w in won.get(ou[i].as_str()).into_iter().flatten() {
            let yy = f64::from(u8::from(*w == oa[i]));
            fav.push(if op[i] >= 0.5 { yy } else { 1.0 - yy });
            years.push(year(od_day[i].unwrap()));
        }
    }
    let mut events: Vec<&str> = ev.clone();
    events.sort_unstable();
    events.dedup();
    let iso = |d: Day| crate::frame::iso(d);
    json!({
        "n": e.len(),
        "events": events.len(),
        "span": [iso(e.iter().map(|t| t.day).min().unwrap()), iso(e.iter().map(|t| t.day).max().unwrap())],
        "first_test_year": Y0,
        "odds_bouts": fav.len(),
        "fav": psum(&fav) / fav.len() as f64,
        "years": [years.iter().min(), years.iter().max()],
        "rows": rows,
        "cal_market": cal(&forecasts[3].2, &y),
        "cal_model": cal(&forecasts[2].2, &y),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn numpy_stream() {
        // np.random.default_rng(20261027).integers(0, 572, 8)
        let mut r = Pcg64::new(SEED);
        let v: Vec<usize> = (0..8).map(|_| r.below(572)).collect();
        assert_eq!(v, [417, 564, 124, 550, 344, 19, 5, 253]);
    }
}
