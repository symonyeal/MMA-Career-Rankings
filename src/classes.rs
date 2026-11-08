//! The All-time score by weight class, counted over UFC bouts.
//!
//! Each part X ∈ {T, K, R} of the All-time score earns points 1000 w_X (X/n_X)^p; the class
//! score S_d gives class d the share X_d/X of those points, so Σ_d S_d = S exactly. Items of a
//! non-UFC bout sit under no class. A capped résumé year is split pro rata,
//! w ↦ w·min(1, cap/Σw); a career year's excess is split by its share of bouts in each class.

use std::collections::{HashMap, HashSet};
use std::sync::OnceLock;

use regex::Regex;

use crate::appearances::Appearance;
use crate::bouts::Bout;
use crate::divisions::{normalize, womens, MEN_LIMIT_LB};
use crate::era::year;
use crate::frame::{Frame, Table};
use crate::legacy::{points, resume_rows, title_rows, Pricing};
use crate::orgs::Org;
use crate::policy::is_ufc;
use crate::skill::Year;
use crate::stats::kahan_sum;

/// `public_legacy_eligibility_override`: proven UFC title resumes rank before the 13-period floor.
pub fn eligibility_override(cur: &Frame) -> Vec<bool> {
    let n0 = |c: &str| {
        cur.f64(c)
            .into_iter()
            .map(|x| if x.is_nan() { 0.0 } else { x })
            .collect::<Vec<_>>()
    };
    let (periods, score, wins, defences, ufc) = (
        n0("rating_periods"),
        n0("public_legacy_score"),
        n0("public_legacy_title_wins"),
        n0("public_legacy_title_defenses"),
        n0("public_legacy_ufc_bouts"),
    );
    (0..cur.len())
        .map(|i| {
            periods[i] >= 8.0
                && ufc[i] >= 8.0
                && score[i] > 0.0
                && (wins[i] >= 3.0 || wins[i] >= 2.0 && defences[i] >= 1.0)
        })
        .collect()
}

/// The class a bout counts toward: women's billings folded, a men's catchweight to the lightest
/// class that holds it, open weight and unknown billings to none.
fn weight_class(division: &str, gender: &str) -> Option<String> {
    if gender == "F" {
        return womens(division).filter(|d| d != "Women's Openweight");
    }
    if let Some(d) = normalize(division).filter(|d| MEN_LIMIT_LB.iter().any(|m| m.0 == d)) {
        return Some(d);
    }
    static LB: OnceLock<Regex> = OnceLock::new();
    let lb: u32 = LB
        .get_or_init(|| Regex::new(r"(?i)(\d{2,3})\s*lb").unwrap())
        .captures(division)?[1]
        .parse()
        .unwrap();
    MEN_LIMIT_LB
        .iter()
        .find(|m| lb <= m.1)
        .map(|m| m.0.to_string())
}

/// One (fighter, class) row in ledger units, then in All-time points.
#[derive(Clone, Debug)]
struct Class {
    fighter: String,
    division: Option<String>,
    part: [f64; 3],
}

/// `class_ledger`: title, skill and résumé totals split by class. `p` is the era pricing,
/// `years` the career receipt (`skill::years`), `ctx` the bout promotions.
fn ledger(
    cur: &Frame,
    pools: &HashMap<String, Option<String>>,
    app: &[Appearance],
    rated: &[Bout],
    p: &Pricing,
    ctx: &HashMap<String, Org>,
    years: &[Year],
) -> Vec<Class> {
    let gender: HashMap<String, String> = cur
        .str("fighter")
        .into_iter()
        .zip(cur.str("gender"))
        .collect();
    let g = |f: &str| gender.get(f).map_or("", String::as_str);
    let ufc: HashSet<&str> = rated
        .iter()
        .filter(|b| is_ufc(b))
        .map(|b| b.url.as_str())
        .collect();
    let mut billed: HashMap<&str, &str> = HashMap::new();
    for b in rated {
        billed.entry(&b.url).or_insert(&b.weight_class);
    }
    let classes: Vec<Option<String>> = app
        .iter()
        .map(|a| {
            if ufc.contains(a.url.as_str()) {
                weight_class(&a.division, g(&a.fighter))
            } else {
                None
            }
        })
        .collect();
    let mut bout: HashMap<(&str, &str), &Option<String>> = HashMap::new();
    for (a, c) in app.iter().zip(&classes) {
        bout.entry((&a.url, &a.fighter)).or_insert(c);
    }
    let of = |u: &str, f: &str| -> Option<String> {
        if !ufc.contains(u) {
            return None;
        }
        match bout.get(&(u, f)) {
            Some(Some(c)) => Some(c.clone()),
            _ => weight_class(billed.get(u).copied().unwrap_or(""), g(f)),
        }
    };
    let mut rows: Vec<Class> = Vec::new();
    for w in title_rows(rated, p, pools, ctx, None) {
        rows.push(Class {
            division: of(&w.url, &w.fighter),
            fighter: w.fighter,
            part: [w.weight, f64::NAN, f64::NAN],
        });
    }
    // Each career year's excess, split by that year's share of appearances in each class.
    let mut share: HashMap<(&str, i32), Vec<(Option<String>, usize)>> = HashMap::new();
    for (a, c) in app.iter().zip(&classes) {
        let v = share.entry((&a.fighter, year(a.day))).or_default();
        match v.iter_mut().find(|x| x.0 == *c) {
            Some(x) => x.1 += 1,
            None => v.push((c.clone(), 1)),
        }
    }
    for y in years {
        match share.get(&(y.fighter.as_str(), y.year)) {
            None => rows.push(Class {
                fighter: y.fighter.clone(),
                division: None,
                part: [f64::NAN, y.excess, f64::NAN],
            }),
            Some(v) => {
                let n: usize = v.iter().map(|x| x.1).sum();
                for (c, k) in v {
                    let s = y.excess * (*k as f64 / n as f64);
                    rows.push(Class {
                        fighter: y.fighter.clone(),
                        division: c.clone(),
                        part: [f64::NAN, s, f64::NAN],
                    });
                }
            }
        }
    }
    let r = resume_rows(rated, p, None);
    let mut total: HashMap<(&str, i32), Vec<f64>> = HashMap::new();
    for w in &r {
        total
            .entry((&w.fighter, year(w.day)))
            .or_default()
            .push(w.weight);
    }
    let total: HashMap<(&str, i32), f64> =
        total.into_iter().map(|(k, v)| (k, kahan_sum(&v))).collect();
    for w in &r {
        let cap = (1.0 / total[&(w.fighter.as_str(), year(w.day))]).min(1.0);
        rows.push(Class {
            fighter: w.fighter.clone(),
            division: of(&w.url, &w.fighter),
            part: [f64::NAN, f64::NAN, w.weight * cap],
        });
    }
    // Group by (fighter, class) in first-appearance order, NaN parts skipped.
    let mut at: HashMap<(String, Option<String>), usize> = HashMap::new();
    let mut parts: Vec<(Class, [Vec<f64>; 3])> = Vec::new();
    for c in rows {
        let k = (c.fighter.clone(), c.division.clone());
        let i = *at.entry(k).or_insert_with(|| {
            parts.push((
                Class {
                    part: [0.0; 3],
                    ..c.clone()
                },
                Default::default(),
            ));
            parts.len() - 1
        });
        for j in 0..3 {
            parts[i].1[j].push(c.part[j]);
        }
    }
    parts
        .into_iter()
        .map(|(c, v)| Class {
            part: std::array::from_fn(|j| kahan_sum(&v[j])),
            ..c
        })
        .collect()
}

/// `class_scores`: ledger units to All-time points, X_d · 1000 w (X/n)^p / X.
fn scores(cur: &Frame, ledger: Vec<Class>) -> Vec<(Class, f64)> {
    let f = cur.str("fighter");
    let n0 = |c: &str| {
        cur.f64(c)
            .into_iter()
            .map(|x| if x.is_nan() { 0.0 } else { x })
            .collect::<Vec<_>>()
    };
    let e: Vec<f64> = cur
        .f64("public_legacy_exposure_factor")
        .into_iter()
        .map(|x| if x.is_nan() { 1.0 } else { x })
        .collect();
    let x = [
        n0("public_legacy_title_score"),
        n0("public_legacy_skill_score"),
        n0("public_legacy_resume_score"),
    ];
    let p = points(&x[0], &x[1], &x[2]);
    let mut unit: HashMap<&str, [f64; 3]> = HashMap::new();
    for i in 0..f.len() {
        let u = [1000.0, e[i], 1000.0 * e[i]];
        unit.entry(&f[i]).or_insert(std::array::from_fn(|j| if x[j][i] > 0.0 { p[j][i] / x[j][i] } else { 0.0 } * u[j]));
    }
    ledger
        .into_iter()
        .map(|c| {
            let u = unit.get(c.fighter.as_str()).copied().unwrap_or([0.0; 3]);
            let part: [f64; 3] = std::array::from_fn(|j| c.part[j] * u[j]);
            let s = part[0] + part[1] + part[2];
            (Class { part, ..c }, s)
        })
        .collect()
}

/// `class_board`: each class ranked among the All-time-eligible fighters with credit in it.
///
/// `cur` needs `fighter, gender, career_division` and the `public_legacy_*` columns; `eligible`
/// holds the fighters ranked on the All-time boards. Panics unless every fighter's class
/// scores sum to the All-time score within 1e-6.
pub fn board(
    cur: &Frame,
    pools: &HashMap<String, Option<String>>,
    app: &[Appearance],
    rated: &[Bout],
    p: &Pricing,
    ctx: &HashMap<String, Org>,
    years: &[Year],
    eligible: &HashSet<String>,
) -> Table {
    let s = scores(cur, ledger(cur, pools, app, rated, p, ctx, years));
    let (f, gender, all) = (
        cur.str("fighter"),
        cur.str("gender"),
        cur.f64("public_legacy_score"),
    );
    let mut sum: HashMap<&str, f64> = HashMap::new();
    for (c, v) in &s {
        *sum.entry(&c.fighter).or_insert(0.0) += v;
    }
    let mut gap = 0.0_f64;
    for i in 0..f.len() {
        let want = if all[i].is_nan() { 0.0 } else { all[i] };
        gap = gap.max((sum.get(f[i].as_str()).copied().unwrap_or(0.0) - want).abs());
    }
    assert!(
        gap <= 1e-6,
        "class scores do not sum to the All-time score (max gap {gap:e})"
    );
    let row: HashMap<&str, usize> = f.iter().enumerate().map(|(i, x)| (x.as_str(), i)).collect();
    let mut b: Vec<(Class, f64, String, f64, i64)> = s
        .into_iter()
        .filter(|(c, v)| c.division.is_some() && eligible.contains(&c.fighter) && *v > 0.0)
        .map(|(c, v)| {
            let i = row[c.fighter.as_str()];
            let g = gender[i].clone();
            (c, v, g, v / all[i], 0)
        })
        .collect();
    // Rank within (gender, class) by score, ties in ledger order.
    let mut order: Vec<usize> = (0..b.len()).collect();
    order.sort_by(|&x, &y| {
        (&b[x].2, &b[x].0.division)
            .cmp(&(&b[y].2, &b[y].0.division))
            .then(b[y].1.total_cmp(&b[x].1))
    });
    let mut k = 0;
    for (n, &i) in order.iter().enumerate() {
        let same = n > 0
            && (&b[order[n - 1]].2, &b[order[n - 1]].0.division) == (&b[i].2, &b[i].0.division);
        k = if same { k + 1 } else { 1 };
        b[i].4 = k;
    }
    let b: Vec<&(Class, f64, String, f64, i64)> = order.iter().map(|&i| &b[i]).collect();
    let col = |g: &dyn Fn(&(Class, f64, String, f64, i64)) -> f64| {
        b.iter().map(|x| g(x)).collect::<Vec<f64>>()
    };
    Table::default()
        .str(
            "fighter",
            &b.iter().map(|x| x.0.fighter.as_str()).collect::<Vec<_>>(),
        )
        .str(
            "division",
            &b.iter()
                .map(|x| x.0.division.as_deref().unwrap())
                .collect::<Vec<_>>(),
        )
        .f64("title", &col(&|x| x.0.part[0]))
        .f64("skill", &col(&|x| x.0.part[1]))
        .f64("resume", &col(&|x| x.0.part[2]))
        .f64("score", &col(&|x| x.1))
        .str(
            "gender",
            &b.iter().map(|x| x.2.as_str()).collect::<Vec<_>>(),
        )
        .f64("share", &col(&|x| x.3))
        .i64("rank", &b.iter().map(|x| x.4).collect::<Vec<_>>())
}
