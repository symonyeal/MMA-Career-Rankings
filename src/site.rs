//! `site/data.js`: every frame the static site draws, from one snapshot.
//!
//! The page only filters, sorts and draws; each key here is computed from the
//! ratings, boards and bouts the published tables use, so the site and the
//! README cannot disagree. `market` (the forecast benchmark) arrives finished from `forecast`.
//!
//! Where pandas sorted on one key with numpy's unstable quicksort, rows that
//! tie keep their input order here: a fighter's last rating of a day is the
//! one after the day's last bout in path order.

use std::collections::{BTreeMap, BTreeSet, HashMap, HashSet};
use std::path::Path;

use regex::Regex;

use crate::appearances::Appearance;
use crate::bouts::Bout;
use crate::divisions::{display, pool, SHORT};
use crate::era::year;
use crate::error::Error;
use crate::frame::{iso, Day, Frame};
use crate::history::{History, Row};
use crate::names::Names;
use crate::policy::{is_ufc, CONTENDER, DAYS_PER_MONTH, MIN_PERIODS};
use crate::pyjson::{ints, num, opt, opt_s, s, J};
use crate::skill::Year;
use crate::stats::{np_round, psum, var};

/// Legacy weights: achievement share a, skill share s of the quality term, display scale.
const A: f64 = 0.30;
const S: f64 = 0.25;
const SCALE: f64 = 1000.0;
const TOP_N: usize = 100;
const JULIAN_YEAR_DAYS: f64 = 365.25;
const METHODS: [&str; 7] = [
    "KO/TKO",
    "Submission",
    "Decision - Unanimous",
    "Decision - Split",
    "Decision - Majority",
    "DQ",
    "Other",
];
const TOP_NS: [usize; 4] = [5, 10, 15, 25];
const AGE_BANDS: [(f64, f64, &str); 7] = [
    (0.0, 25.0, "under 25"),
    (25.0, 28.0, "25–27"),
    (28.0, 31.0, "28–30"),
    (31.0, 34.0, "31–33"),
    (34.0, 37.0, "34–36"),
    (37.0, 40.0, "37–39"),
    (40.0, 99.0, "40+"),
];
const LAYOFF_BANDS: [(f64, f64, &str); 6] = [
    (0.0, 4.0, "under 4"),
    (4.0, 8.0, "4–8"),
    (8.0, 12.0, "8–12"),
    (12.0, 18.0, "12–18"),
    (18.0, 24.0, "18–24"),
    (24.0, 999.0, "24+"),
];

/// Inputs of `data`; boards are (men, women) pairs as `build_boards` writes them.
pub struct Inputs<'a> {
    pub snapshot: &'a Path,
    pub rated_bouts: i64,
    pub fighters: i64,
    pub current: &'a Frame,
    pub all_time: [&'a Frame; 2],
    pub prime: [&'a Frame; 2],
    pub current_board: [&'a Frame; 2],
    pub class: &'a Frame,
    pub integrity: &'a Frame,
    pub ledger: &'a Frame,
    pub dominance: &'a Frame,
    pub calib: &'a Frame,
    pub history: &'a History,
    pub apps: &'a [Appearance],
    pub staged: &'a [Bout],
    pub names: &'a Names,
    pub births: &'a HashMap<String, Day>,
    pub years: &'a [Year],
    pub market: &'a serde_json::Value,
}

/// Per-year career receipt of each listed fighter: `[year, annual mean, field line, excess]`, rounded.
fn receipt(years: &[Year], set: &HashSet<&str>) -> J {
    let mut out: Vec<(String, J)> = Vec::new();
    for y in years.iter().filter(|y| set.contains(y.fighter.as_str())) {
        if out.last().is_none_or(|(f, _)| *f != y.fighter) {
            out.push((y.fighter.clone(), J::Arr(Vec::new())));
        }
        if let Some((_, J::Arr(v))) = out.last_mut() {
            v.push(J::Arr(
                [y.year as f64, y.annual, y.field, y.excess]
                    .iter()
                    .map(|&x| num(x, 0))
                    .collect(),
            ));
        }
    }
    J::Obj(out)
}

/// The full text of `site/data.js`.
pub fn data(x: &Inputs) -> Result<String, Error> {
    let rc = x.current;
    let fighter = rc.str("fighter")?;
    let periods = rc.i64("rating_periods")?;
    let score = rc.f64("public_legacy_score")?;
    let mut e: Vec<usize> = (0..rc.len())
        .filter(|&i| periods[i] >= MIN_PERIODS)
        .collect();
    e.sort_by(|&i, &j| desc(score[i], score[j]));
    let names: Vec<String> = e.iter().map(|&i| fighter[i].clone()).collect();
    let set: HashSet<&str> = names.iter().map(String::as_str).collect();

    let ufc: Vec<&Bout> = x.staged.iter().filter(|b| is_ufc(b)).collect();
    let (traj, n) = trajectories(&names, &set, x.history, x.apps);
    let through = x
        .staged
        .iter()
        .map(|b| b.day)
        .max()
        .ok_or_else(|| Error::at("site", "no bouts"))?;
    let years = count_years(x.staged.iter().collect::<Vec<_>>().as_slice(), 100);
    let uyears = count_years(&ufc, 30);
    let eoy = year_end(x.history);
    let long = division_appearances(&ufc);
    let whr_e: Vec<&Row> = x
        .history
        .rows()
        .iter()
        .filter(|r| set.contains(r.fighter.as_str()))
        .collect();
    let (vs, upsets, age, layoff) = market(x)?;

    let obj = |v: Vec<(&str, J)>| J::Obj(v.into_iter().map(|(k, v)| (k.to_string(), v)).collect());
    let data = obj(vec![
        (
            "meta",
            obj(vec![
                (
                    "snapshot",
                    s(&x.snapshot
                        .file_name()
                        .map_or_else(String::new, |n| n.to_string_lossy().into_owned())),
                ),
                ("through", s(&iso(through))),
                ("rated_bouts", J::Int(x.rated_bouts)),
                ("fighters", J::Int(x.fighters)),
                ("established", J::Int(names.len() as i64)),
                ("min_periods", J::Int(MIN_PERIODS)),
                ("contender", J::Num(CONTENDER)),
                ("a", J::Num(A)),
                ("s", J::Num(S)),
                ("scale", J::Num(SCALE)),
                ("methods", J::Arr(METHODS.iter().map(|m| s(m)).collect())),
                (
                    "peak",
                    J::Arr(vec![J::Int(1825), J::Int(8), s("5-Yr Period")]),
                ),
            ]),
        ),
        ("divisions", J::Arr(SHORT.iter().map(|p| s(p.0)).collect())),
        (
            "short",
            J::Obj(SHORT.iter().map(|p| (p.0.to_string(), s(p.1))).collect()),
        ),
        ("F", fighters(x, &e, &names)?),
        ("classes", classes(x.class, &names)?),
        ("N", J::Arr(n.iter().map(|f| s(f)).collect())),
        ("traj", traj),
        ("receipt", receipt(x.years, &set)),
        (
            "strength",
            J::Obj(
                TOP_NS
                    .iter()
                    .map(|&k| (k.to_string(), strength(&long, &eoy, k)))
                    .collect(),
            ),
        ),
        (
            "year_top",
            J::Obj(
                uyears
                    .iter()
                    .map(|&y| (y.to_string(), year_top(&long, &eoy, y)))
                    .collect(),
            ),
        ),
        (
            "movers",
            J::Obj(
                years
                    .iter()
                    .map(|&y| (y.to_string(), movers(&whr_e, x.staged, y)))
                    .collect(),
            ),
        ),
        ("mix", mix(&ufc)),
        (
            "lineage",
            J::Obj(
                SHORT[..13]
                    .iter()
                    .map(|p| {
                        (
                            p.0.to_string(),
                            J::Arr(
                                [false, true]
                                    .iter()
                                    .map(|&i| lineage(x.apps, p.0, i))
                                    .collect(),
                            ),
                        )
                    })
                    .collect(),
            ),
        ),
        ("streaks", streaks(x)?),
        ("bench", bench(x)?),
        ("integrity", integrity(x.integrity, x.ledger)?),
        ("calib", calib(x.calib)?),
        ("market", vs),
        ("upsets", upsets),
        ("age", age),
        ("layoff", layoff),
    ]);
    Ok(format!("window.DATA = {};\n", data.dump()))
}

/// Descending with NaN last (pandas `sort_values(ascending=False)`), ties in input order under a stable sort.
fn desc(a: f64, b: f64) -> std::cmp::Ordering {
    match (a.is_nan(), b.is_nan()) {
        (true, true) => std::cmp::Ordering::Equal,
        (true, false) => std::cmp::Ordering::Greater,
        (false, true) => std::cmp::Ordering::Less,
        _ => b.partial_cmp(&a).unwrap(),
    }
}

fn asc(a: f64, b: f64) -> std::cmp::Ordering {
    match (a.is_nan(), b.is_nan()) {
        (true, true) => std::cmp::Ordering::Equal,
        (true, false) => std::cmp::Ordering::Greater,
        (false, true) => std::cmp::Ordering::Less,
        _ => a.partial_cmp(&b).unwrap(),
    }
}

fn count_years(bouts: &[&Bout], min: usize) -> Vec<i32> {
    let mut c: BTreeMap<i32, usize> = BTreeMap::new();
    for b in bouts {
        *c.entry(year(b.day)).or_default() += 1;
    }
    c.into_iter().filter(|p| p.1 >= min).map(|p| p.0).collect()
}

/// Row index by fighter.
fn index(f: &Frame) -> Result<HashMap<String, usize>, Error> {
    Ok(f.str("fighter")?
        .into_iter()
        .enumerate()
        .map(|(i, n)| (n, i))
        .collect())
}

/// One published board (men then women) as fighter → row; `rank` is withheld unless `status == "ranked"`.
struct Board<'a> {
    at: Vec<(&'a Frame, HashMap<String, usize>, Vec<f64>)>,
}

impl<'a> Board<'a> {
    fn new(pair: [&'a Frame; 2]) -> Result<Board<'a>, Error> {
        let at = pair
            .iter()
            .map(|f| {
                let st = f.str("status")?;
                let rank = f
                    .f64("rank")?
                    .into_iter()
                    .zip(st)
                    .map(|(r, s)| if s == "ranked" { r } else { f64::NAN })
                    .collect();
                Ok((*f, index(f)?, rank))
            })
            .collect::<Result<_, Error>>()?;
        Ok(Board { at })
    }

    fn row(&self, fighter: &str) -> Option<(usize, usize)> {
        self.at
            .iter()
            .enumerate()
            .find_map(|(k, (_, ix, _))| ix.get(fighter).map(|&i| (k, i)))
    }

    fn rank(&self, fighter: &str) -> Option<f64> {
        self.row(fighter)
            .map(|(k, i)| self.at[k].2[i])
            .filter(|x| !x.is_nan())
    }

    fn f64(&self, col: &str, names: &[String]) -> Result<Vec<Option<f64>>, Error> {
        let c: Vec<Vec<f64>> = self
            .at
            .iter()
            .map(|(f, _, _)| f.f64(col))
            .collect::<Result<_, _>>()?;
        Ok(names
            .iter()
            .map(|n| self.row(n).map(|(k, i)| c[k][i]).filter(|x| !x.is_nan()))
            .collect())
    }

    fn i64(&self, col: &str, names: &[String]) -> Result<Vec<Option<i64>>, Error> {
        let c: Vec<Vec<i64>> = self
            .at
            .iter()
            .map(|(f, _, _)| f.i64(col))
            .collect::<Result<_, _>>()?;
        Ok(names
            .iter()
            .map(|n| self.row(n).map(|(k, i)| c[k][i]))
            .collect())
    }

    fn year(&self, col: &str, names: &[String]) -> Result<Vec<Option<i64>>, Error> {
        let c: Vec<Vec<Option<Day>>> = self
            .at
            .iter()
            .map(|(f, _, _)| f.day(col))
            .collect::<Result<_, _>>()?;
        Ok(names
            .iter()
            .map(|n| {
                self.row(n)
                    .and_then(|(k, i)| c[k][i])
                    .map(|d| year(d) as i64)
            })
            .collect())
    }
}

/// `_scale(x) ** 0.5`: each value over the mean of the column's top 100 positive values.
fn scaled(v: &[f64]) -> Vec<f64> {
    let v: Vec<f64> = v
        .iter()
        .map(|x| if x.is_nan() { 0.0 } else { *x })
        .collect();
    let mut pos: Vec<f64> = v.iter().copied().filter(|x| *x > 0.0).collect();
    pos.sort_by(|a, b| b.total_cmp(a));
    pos.truncate(TOP_N);
    let norm = if pos.is_empty() {
        0.0
    } else {
        psum(&pos) / pos.len() as f64
    };
    v.iter()
        .map(|x| if norm > 0.0 { x / norm } else { x * 0.0 }.sqrt())
        .collect()
}

fn fighters(x: &Inputs, e: &[usize], names: &[String]) -> Result<J, Error> {
    let rc = x.current;
    let at = |c: &[f64]| {
        e.iter()
            .map(|&i| Some(c[i]).filter(|v| !v.is_nan()))
            .collect::<Vec<_>>()
    };
    let int = |c: &str| -> Result<Vec<Option<i64>>, Error> {
        let v = rc.i64(c)?;
        Ok(e.iter().map(|&i| Some(v[i])).collect())
    };
    let col = |c: &str| rc.f64(c).map(|v| at(&v));
    let f1 = |v: Vec<Option<f64>>, nd: usize| J::Arr(v.into_iter().map(|x| opt(x, nd)).collect());
    let gender = rc.str("gender")?;
    let div = |c: &str| -> Result<J, Error> {
        let d = rc.str(c)?;
        Ok(J::Arr(
            e.iter()
                .map(|&i| s(&pool(&d[i], &gender[i]).unwrap_or_default()))
                .collect(),
        ))
    };
    let (at_b, pr, cu) = (
        Board::new(x.all_time)?,
        Board::new(x.prime)?,
        Board::new(x.current_board)?,
    );
    let rank = |b: &Board| f1(names.iter().map(|n| b.rank(n)).collect(), 1);
    let last = rc.day("whr_last_event_date")?;
    let part = |c: &str| -> Result<J, Error> {
        let t = scaled(&rc.f64(&format!("public_legacy_{c}_score"))?);
        Ok(f1(at(&t), 3))
    };
    let mut peak: HashMap<&str, f64> = HashMap::new();
    for r in x.history.rows() {
        if !r.era.is_nan() {
            let p = peak.entry(&r.fighter).or_insert(f64::NEG_INFINITY);
            *p = p.max(r.era);
        }
    }
    let dom = index(x.dominance)?;
    let (dmean, dwins) = (x.dominance.f64("mean_dominance")?, x.dominance.i64("wins")?);
    let obj: Vec<(&str, J)> = vec![
        ("name", J::Arr(names.iter().map(|n| s(n)).collect())),
        ("g", J::Arr(e.iter().map(|&i| opt_s(&gender[i])).collect())),
        ("div", div("career_division")?),
        ("cdiv", div("current_division")?),
        ("n", ints(&int("rating_periods")?, 1)),
        ("w", ints(&int("wins")?, 1)),
        ("l", ints(&int("losses")?, 1)),
        ("d", ints(&int("draws")?, 1)),
        (
            "last",
            J::Arr(
                e.iter()
                    .map(|&i| last[i].map_or(J::Null, |d| s(&iso(d))))
                    .collect(),
            ),
        ),
        ("at", rank(&at_b)),
        ("score", f1(col("public_legacy_score")?, 1)),
        ("T", part("title")?),
        ("S", part("skill")?),
        ("R", part("resume")?),
        ("tw", ints(&int("public_legacy_qualifying_title_wins")?, 1)),
        ("cw", ints(&int("public_legacy_contender_wins")?, 1)),
        ("cy", ints(&int("symon_career_contributing_years")?, 1)),
        ("ay", ints(&int("symon_career_active_years")?, 1)),
        ("mass", f1(col("symon_career_skill_mass")?, 1)),
        ("pr", rank(&pr)),
        ("plevel", f1(pr.f64("elite_level", names)?, 1)),
        ("pwins", f1(pr.f64("tested_opponent_wins", names)?, 1)),
        ("p0", ints(&pr.year("elite_window_start", names)?, 1)),
        ("p1", ints(&pr.year("elite_window_end", names)?, 1)),
        ("cr", rank(&cu)),
        ("cur", f1(cu.f64("current_board_score", names)?, 1)),
        ("ufc", ints(&cu.i64("tested_opponent_wins", names)?, 1)),
        ("whr", f1(col("mu_whr")?, 1)),
        (
            "peak",
            f1(
                names
                    .iter()
                    .map(|n| peak.get(n.as_str()).copied())
                    .collect(),
                1,
            ),
        ),
        ("glicko", f1(col("mu_canonical")?, 1)),
        (
            "dom",
            f1(
                names
                    .iter()
                    .map(|n| dom.get(n).map(|&i| dmean[i]).filter(|v| !v.is_nan()))
                    .collect(),
                1,
            ),
        ),
        (
            "domw",
            ints(
                &names
                    .iter()
                    .map(|n| dom.get(n).map(|&i| dwins[i]))
                    .collect::<Vec<_>>(),
                1,
            ),
        ),
    ];
    Ok(J::Obj(
        obj.into_iter().map(|(k, v)| (k.to_string(), v)).collect(),
    ))
}

/// Class-board rows of the established fighters, components back on the scale of T, S, R.
fn classes(cb: &Frame, names: &[String]) -> Result<J, Error> {
    let idx: HashMap<&str, usize> = names
        .iter()
        .enumerate()
        .map(|(i, n)| (n.as_str(), i))
        .collect();
    let w = [
        SCALE * A,
        SCALE * ((1.0 - A) * S),
        SCALE * ((1.0 - A) * (1.0 - S)),
    ];
    let (f, d, r) = (cb.str("fighter")?, cb.str("division")?, cb.i64("rank")?);
    let (t, k, q) = (cb.f64("title")?, cb.f64("skill")?, cb.f64("resume")?);
    Ok(J::Arr(
        (0..cb.len())
            .filter_map(|i| {
                let &x = idx.get(f[i].as_str())?;
                Some(J::Arr(vec![
                    J::Int(x as i64),
                    s(&d[i]),
                    J::Int(r[i]),
                    num(t[i] / w[0], 4),
                    num(k[i] / w[1], 4),
                    num(q[i] / w[2], 4),
                ]))
            })
            .collect(),
    ))
}

/// Per fighter: [first day, day increments, era rating, method codes, W/L/D/N, opponent index], and the name list.
///
/// Each history row joins the appearance of the same (fighter, date, event) and the same
/// rank k among duplicates; appearances list a-sides before b-sides, so when one fighter has
/// two bouts on a card the k-th history row may take the other bout's opponent, as published.
fn trajectories(
    names: &[String],
    set: &HashSet<&str>,
    h: &History,
    apps: &[Appearance],
) -> (J, Vec<String>) {
    let mut p: Vec<&Appearance> = apps
        .iter()
        .filter(|a| set.contains(a.fighter.as_str()))
        .collect();
    p.sort_by(|a, b| (&a.fighter, a.day, &a.event).cmp(&(&b.fighter, b.day, &b.event)));
    let mut by: HashMap<(&str, Day, &str), Vec<&Appearance>> = HashMap::new();
    for a in p {
        by.entry((&a.fighter, a.day, &a.event)).or_default().push(a);
    }
    let rows: Vec<&Row> = h
        .rows()
        .iter()
        .filter(|r| set.contains(r.fighter.as_str()))
        .collect();
    let mut k: HashMap<(&str, Day, &str), usize> = HashMap::new();
    let joined: Vec<(&Row, Option<&Appearance>)> = rows
        .iter()
        .map(|r| {
            let key = (r.fighter.as_str(), r.day, r.event.as_str());
            let c = k.entry(key).or_default();
            let a = by.get(&key).and_then(|v| v.get(*c)).copied();
            *c += 1;
            (*r, a)
        })
        .collect();
    let others: BTreeSet<&str> = joined
        .iter()
        .filter_map(|(_, a)| a.map(|a| a.opponent.as_str()))
        .filter(|o| !set.contains(o))
        .collect();
    let n: Vec<String> = names
        .iter()
        .cloned()
        .chain(others.into_iter().map(str::to_string))
        .collect();
    let idx: HashMap<&str, i64> = n
        .iter()
        .enumerate()
        .map(|(i, f)| (f.as_str(), i as i64))
        .collect();
    let mut out: Vec<(String, J)> = Vec::new();
    let mut i = 0;
    while i < joined.len() {
        let f = &joined[i].0.fighter;
        let j = i + joined[i..]
            .iter()
            .take_while(|(r, _)| &r.fighter == f)
            .count();
        let g = &joined[i..j];
        let (mut m, mut res) = (String::new(), String::new());
        for (_, a) in g {
            m.push_str(
                &a.and_then(|a| METHODS.iter().position(|x| *x == a.method))
                    .map_or("-".into(), |i| i.to_string()),
            );
            res.push(match a {
                None => 'N',
                Some(a) if a.draw => 'D',
                Some(a) if a.won => 'W',
                _ => 'L',
            });
        }
        out.push((
            f.clone(),
            J::Arr(vec![
                J::Int(g[0].0.day as i64),
                J::Arr(
                    g.iter()
                        .enumerate()
                        .map(|(t, (r, _))| {
                            J::Int(if t == 0 {
                                0
                            } else {
                                (r.day - g[t - 1].0.day) as i64
                            })
                        })
                        .collect(),
                ),
                J::Arr(g.iter().map(|(r, _)| num(np_round(r.era, 0), 1)).collect()),
                J::Str(m),
                J::Str(res),
                J::Arr(
                    g.iter()
                        .map(|(_, a)| J::Int(a.map_or(-1, |a| idx[a.opponent.as_str()])))
                        .collect(),
                ),
            ]),
        ));
        i = j;
    }
    (J::Obj(out), n)
}

/// Each fighter-year's last rating in path order (`_annual_ratings`), over the whole history.
fn year_end(h: &History) -> HashMap<(&str, i32), f64> {
    let mut out = HashMap::new();
    for r in h.rows().iter().filter(|r| !r.mu.is_nan()) {
        out.insert((r.fighter.as_str(), year(r.day)), r.mu);
    }
    out
}

/// Both corners of each UFC bout with a display division: (year, division, fighter), a-sides first.
fn division_appearances<'a>(ufc: &[&'a Bout]) -> Vec<(i32, String, &'a str)> {
    let rows = |side: fn(&Bout) -> &str| {
        ufc.iter()
            .filter(|b| !b.weight_class.is_empty())
            .map(move |b| (year(b.day), display(&b.weight_class), side(b)))
            .filter(|r| !r.2.is_empty())
            .collect::<Vec<_>>()
    };
    let mut out = rows(|b| b.a());
    out.extend(rows(|b| b.b()));
    out
}

/// Year-end ratings of the fighters seen in each (division, year), one row per fighter.
fn annual<'a>(
    long: &[&(i32, String, &'a str)],
    eoy: &HashMap<(&str, i32), f64>,
) -> Vec<(i32, String, &'a str, f64)> {
    let mut seen = HashSet::new();
    long.iter()
        .filter_map(|(y, d, f)| eoy.get(&(*f, *y)).map(|mu| (*y, d.clone(), *f, *mu)))
        .filter(|r| seen.insert((r.2, r.0, r.1.clone())))
        .collect()
}

fn strength(long: &[(i32, String, &str)], eoy: &HashMap<(&str, i32), f64>, k: usize) -> J {
    let merged = annual(&long.iter().collect::<Vec<_>>(), eoy);
    let mut g: BTreeMap<(&str, i32), Vec<f64>> = BTreeMap::new();
    for r in &merged {
        g.entry((r.1.as_str(), r.0)).or_default().push(r.3);
    }
    J::Arr(
        g.into_iter()
            .filter_map(|((d, y), mut v)| {
                v.sort_by(|a, b| desc(*a, *b));
                v.truncate(k);
                (v.len() >= k.min(5)).then(|| {
                    J::Arr(vec![
                        s(d),
                        J::Int(y as i64),
                        num(psum(&v) / v.len() as f64, 2),
                        J::Int(v.len() as i64),
                    ])
                })
            })
            .collect(),
    )
}

/// Top five of each division at the end of year `y`, divisions by their best rating.
fn year_top(long: &[(i32, String, &str)], eoy: &HashMap<(&str, i32), f64>, y: i32) -> J {
    let mut merged = annual(&long.iter().filter(|r| r.0 == y).collect::<Vec<_>>(), eoy);
    merged.sort_by(|a, b| desc(a.3, b.3));
    let mut top: BTreeMap<&str, Vec<(&str, f64)>> = BTreeMap::new();
    for r in &merged {
        let v = top.entry(r.1.as_str()).or_default();
        if v.len() < 5 {
            v.push((r.2, r.3));
        }
    }
    let mut order: Vec<(&str, f64)> = top.iter().map(|(d, v)| (*d, v[0].1)).collect();
    order.sort_by(|a, b| desc(a.1, b.1));
    J::Arr(
        order
            .into_iter()
            .map(|(d, _)| {
                let code = SHORT.iter().find(|p| p.0 == d).map_or(d, |p| p.1);
                let v = &top[d];
                J::Arr(vec![
                    s(code),
                    J::Arr(v.iter().map(|p| num(p.1, 2)).collect()),
                    J::Arr(
                        v.iter()
                            .enumerate()
                            .map(|(i, p)| J::Str(format!("{}. {}  ·  {code}", i + 1, p.0)))
                            .collect(),
                    ),
                ])
            })
            .collect(),
    )
}

/// The year's twelve biggest risers and fallers among established fighters, with per-bout hover lines.
///
/// A history row joins every bout of its fighter on its date (`yearly_rating_delta_frame`'s
/// many-to-many merge), so a fighter with k bouts on one date counts each of their k rows k times.
fn movers(h: &[&Row], staged: &[Bout], y: i32) -> J {
    let mut start: HashMap<&str, f64> = HashMap::new();
    for r in h.iter().filter(|r| year(r.day) < y && !r.mu.is_nan()) {
        start.insert(&r.fighter, r.mu);
    }
    let mut fl: HashMap<(&str, Day), Vec<(&str, &str)>> = HashMap::new();
    for side in [true, false] {
        for b in staged.iter().filter(|b| year(b.day) == y) {
            let (f, o) = if side { (b.a(), b.b()) } else { (b.b(), b.a()) };
            fl.entry((f, b.day))
                .or_default()
                .push((o, if b.winner() == f { "W" } else { "L" }));
        }
    }
    // fighter -> [(day, delta, opponent, result)] in join order
    let mut by: BTreeMap<&str, Vec<(Day, f64, String, String)>> = BTreeMap::new();
    let mut prev: HashMap<&str, f64> = HashMap::new();
    for r in h.iter().filter(|r| year(r.day) == y && !r.mu.is_nan()) {
        let p = prev
            .get(r.fighter.as_str())
            .or(start.get(r.fighter.as_str()))
            .copied();
        prev.insert(&r.fighter, r.mu);
        let Some(p) = p else { continue };
        let d = r.mu - p;
        let v = by.entry(&r.fighter).or_default();
        match fl.get(&(r.fighter.as_str(), r.day)) {
            Some(m) => v.extend(
                m.iter()
                    .map(|(o, res)| (r.day, d, o.to_string(), res.to_string())),
            ),
            None => v.push((r.day, d, "nan".into(), "nan".into())),
        }
    }
    let frame: Vec<(&str, f64, usize)> = by
        .iter()
        .map(|(f, v)| {
            (
                *f,
                psum(&v.iter().map(|r| r.1).collect::<Vec<_>>()),
                v.len(),
            )
        })
        .filter(|r| r.1.abs() > 0.05)
        .collect();
    if frame.is_empty() {
        return J::Arr(vec![]);
    }
    let mut risers = frame.clone();
    risers.sort_by(|a, b| desc(a.1, b.1));
    let mut fallers = frame.clone();
    fallers.sort_by(|a, b| asc(a.1, b.1));
    let mut seen = HashSet::new();
    let mut keep: Vec<(&str, f64, usize)> = risers
        .into_iter()
        .take(12)
        .chain(fallers.into_iter().take(12))
        .filter(|r| seen.insert(r.0))
        .collect();
    keep.sort_by(|a, b| asc(a.1, b.1));
    let hover = |f: &str| {
        let mut v: Vec<&(Day, f64, String, String)> = by[f].iter().collect();
        v.sort_by_key(|r| r.0);
        v.iter()
            .map(|(_, d, o, res)| format!("vs {o}  {res}  Δ{d:+.1}"))
            .collect::<Vec<_>>()
            .join("<br>")
    };
    J::Arr(vec![
        J::Arr(keep.iter().map(|r| num(r.1, 2)).collect()),
        J::Arr(keep.iter().map(|r| s(r.0)).collect()),
        J::Arr(
            keep.iter()
                .map(|r| J::Arr(vec![J::Str(hover(r.0)), J::Str(r.2.to_string())]))
                .collect(),
        ),
    ])
}

/// UFC finishes and decisions by year and division: [year, division, bucket, n].
fn mix(ufc: &[&Bout]) -> J {
    let mut c: BTreeMap<(i32, String, &str), i64> = BTreeMap::new();
    for b in ufc.iter().filter(|b| !b.excluded) {
        let bucket = match b.method.as_str() {
            m @ ("KO/TKO" | "Submission") => m,
            m if m.starts_with("Decision") => "Decision",
            _ => continue,
        };
        let d = if b.weight_class.is_empty() {
            String::new()
        } else {
            display(&b.weight_class)
        };
        *c.entry((year(b.day), d, bucket)).or_default() += 1;
    }
    J::Arr(
        c.into_iter()
            .map(|((y, d, k), n)| J::Arr(vec![J::Int(y as i64), J::Str(d), s(k), J::Int(n)]))
            .collect(),
    )
}

/// Title reigns of one division: [champion, first challenger beaten, start, defences, years, bar ms, label].
fn lineage(apps: &[Appearance], division: &str, interim: bool) -> J {
    let mut w: Vec<&Appearance> = apps
        .iter()
        .filter(|a| {
            a.title
                && (interim || !a.interim)
                && !a.division.is_empty()
                && display(&a.division) == division
                && a.won
        })
        .collect();
    w.sort_by_key(|a| a.day);
    let mut reigns: Vec<(&str, &str, Day, i64)> = Vec::new();
    for a in &w {
        match reigns.last_mut() {
            Some(r) if r.0 == a.fighter => r.3 += 1,
            _ => reigns.push((&a.fighter, &a.opponent, a.day, 0)),
        }
    }
    let Some(last) = w.iter().map(|a| a.day).max() else {
        return J::Arr(vec![]);
    };
    J::Arr(
        reigns
            .iter()
            .enumerate()
            .map(|(i, (f, o, start, def))| {
                let end = reigns.get(i + 1).map_or(last + 150, |r| r.2);
                let days = (end - start).max(30) as i64;
                let tail = f.split_whitespace().last().unwrap_or_default();
                let label = if *def > 0 {
                    format!("{tail} ({def}D)")
                } else {
                    tail.to_string()
                };
                J::Arr(vec![
                    s(f),
                    s(o),
                    s(&iso(*start)),
                    J::Int(*def),
                    num(np_round(days as f64 / JULIAN_YEAR_DAYS, 1), 2),
                    J::Int(days * 86_400_000),
                    J::Str(label),
                ])
            })
            .collect(),
    )
}

/// Win streaks of three or more over the UFC record (`canonical_fights`), longest and strongest first.
fn streaks(x: &Inputs) -> Result<J, Error> {
    let cf = Frame::read(
        &x.snapshot.join("canonical_fights.parquet"),
        &[
            "fighter_a",
            "fighter_b",
            "winner",
            "weight_class",
            "method_class",
            "event_date",
            "is_draw",
            "is_nc",
            "is_title_fight",
            "is_excluded",
        ],
    )?;
    let (a, b, w) = (
        cf.str("fighter_a")?,
        cf.str("fighter_b")?,
        cf.str("winner")?,
    );
    let (wc, method, day) = (
        cf.str("weight_class")?,
        cf.str("method_class")?,
        cf.day("event_date")?,
    );
    let (draw, nc, title, excl) = (
        cf.bool("is_draw")?,
        cf.bool("is_nc")?,
        cf.bool("is_title_fight")?,
        cf.bool("is_excluded")?,
    );
    let rc = x.current;
    let mu: HashMap<String, f64> = rc
        .str("fighter")?
        .into_iter()
        .zip(rc.f64("mu_canonical")?)
        .collect();
    let gender: HashMap<String, String> = rc
        .str("fighter")?
        .into_iter()
        .zip(rc.str("gender")?)
        .collect();
    // (fighter, day, opponent, bout)
    let mut long: Vec<(&str, Day, &str, usize)> = Vec::new();
    for side in [true, false] {
        for i in (0..cf.len()).filter(|&i| !excl[i]) {
            let (f, o) = if side { (&a[i], &b[i]) } else { (&b[i], &a[i]) };
            if !f.is_empty() {
                long.push((
                    f,
                    day[i].ok_or_else(|| {
                        Error::at(format!("canonical_fights row {i}"), "no event_date")
                    })?,
                    o,
                    i,
                ));
            }
        }
    }
    long.sort_by(|p, q| (p.0, p.1).cmp(&(q.0, q.1)));
    struct Streak<'a> {
        f: &'a str,
        run: Vec<(Day, &'a str, usize)>,
        ended: String,
        ongoing: bool,
    }
    let mut out: Vec<Streak> = Vec::new();
    let mut i = 0;
    while i < long.len() {
        let f = long[i].0;
        let j = i + long[i..].iter().take_while(|r| r.0 == f).count();
        let mut run: Vec<(Day, &str, usize)> = Vec::new();
        for &(_, d, o, k) in &long[i..j] {
            if nc[k] {
                continue;
            }
            if !draw[k] && w[k] == f {
                run.push((d, o, k));
                continue;
            }
            if run.len() >= 3 {
                let verb = if draw[k] { "Draw with" } else { "Loss to" };
                out.push(Streak {
                    f,
                    run: std::mem::take(&mut run),
                    ended: format!("{verb} {o}"),
                    ongoing: false,
                });
            }
            run.clear();
        }
        if run.len() >= 3 {
            out.push(Streak {
                f,
                run,
                ended: "Active".into(),
                ongoing: true,
            });
        }
        i = j;
    }
    let rows: Vec<(usize, f64, i64, J)> = out
        .iter()
        .map(|st| {
            let divs: Vec<String> = st
                .run
                .iter()
                .filter(|r| !wc[r.2].is_empty())
                .map(|r| display(&wc[r.2]))
                .collect();
            let mut tally: BTreeMap<&str, usize> = BTreeMap::new();
            for d in &divs {
                *tally.entry(d).or_default() += 1;
            }
            let top = tally.values().copied().max();
            let modal = tally
                .iter()
                .find(|p| Some(*p.1) == top)
                .map(|p| p.0.to_string());
            let opp: Vec<f64> = st
                .run
                .iter()
                .filter_map(|r| mu.get(r.1).copied())
                .filter(|v| !v.is_nan())
                .collect();
            let avg = if opp.is_empty() {
                f64::NAN
            } else {
                psum(&opp) / opp.len() as f64
            };
            let tw = st.run.iter().filter(|r| title[r.2]).count() as i64;
            let fin = st
                .run
                .iter()
                .filter(|r| matches!(method[r.2].as_str(), "KO/TKO" | "Submission"))
                .count() as i64;
            let uniq: BTreeSet<&String> = divs.iter().collect();
            let row = J::Arr(vec![
                s(st.f),
                J::Int(st.run.len() as i64),
                J::Int(st.run[0].0 as i64),
                J::Int(st.run.last().unwrap().0 as i64),
                modal.map_or(J::Null, J::Str),
                J::Arr(uniq.into_iter().map(|d| s(d)).collect()),
                J::Int(tw),
                J::Int(fin),
                num(avg, 0),
                J::Bool(st.ongoing),
                s(&st.ended),
                gender.get(st.f).map_or(J::Null, |g| opt_s(g)),
            ]);
            (st.run.len(), avg, tw, row)
        })
        .collect();
    let mut rows = rows;
    rows.sort_by(|p, q| q.0.cmp(&p.0).then(desc(p.1, q.1)).then(q.2.cmp(&p.2)));
    Ok(J::Arr(rows.into_iter().map(|r| r.3).collect()))
}

/// Top 100 established men by All-time score against Fight Matrix's all-time list.
fn bench(x: &Inputs) -> Result<J, Error> {
    let rc = x.current;
    let (f, g, p, score) = (
        rc.str("fighter")?,
        rc.str("gender")?,
        rc.i64("rating_periods")?,
        rc.f64("public_legacy_score")?,
    );
    let mut men: Vec<usize> = (0..rc.len())
        .filter(|&i| p[i] >= MIN_PERIODS && g[i] == "M" && !score[i].is_nan())
        .collect();
    men.sort_by(|&i, &j| desc(score[i], score[j]));
    let fm = Frame::read(
        &x.snapshot.join("fightmatrix_all_time.parquet"),
        &["fighter", "rank", "points"],
    )?;
    let (ff, fr, fp) = (fm.str("fighter")?, fm.i64("rank")?, fm.i64("points")?);
    let mut order: Vec<usize> = (0..fm.len())
        .filter(|&i| !x.names.key(&ff[i], true).is_empty())
        .collect();
    order.sort_by_key(|&i| fr[i]);
    let mut refs: HashMap<String, (i64, i64)> = HashMap::new();
    for i in order {
        refs.entry(x.names.key(&ff[i], true))
            .or_insert((fr[i], fp[i]));
    }
    let top: Vec<(usize, i64, Option<(i64, i64)>)> = men
        .iter()
        .take(100)
        .enumerate()
        .map(|(k, &i)| {
            let key = x.names.key(&f[i], true);
            (
                i,
                k as i64 + 1,
                if key.is_empty() {
                    None
                } else {
                    refs.get(&key).copied()
                },
            )
        })
        .collect();
    let complete = top.iter().all(|r| r.2.is_some());
    let int = |v: Option<i64>| match (v, complete) {
        (Some(v), true) => J::Int(v),
        (v, _) => opt(v.map(|v| v as f64), 1),
    };
    Ok(J::Arr(
        top.iter()
            .map(|(i, rank, r)| {
                J::Arr(vec![
                    s(&f[*i]),
                    J::Int(*rank),
                    int(r.map(|r| r.0)),
                    int(r.map(|r| rank - r.0)),
                    num(score[*i], 1),
                    int(r.map(|r| r.1)),
                ])
            })
            .collect(),
    ))
}

/// The integrity-policy board summary and the per-result ledger.
fn integrity(ib: &Frame, il: &Frame) -> Result<J, Error> {
    let (f, mu, cost) = (
        ib.str("fighter")?,
        ib.f64("mu_whr")?,
        ib.f64("integrity_cost")?,
    );
    let (ur, rank) = (ib.f64("undiscounted_rank")?, ib.i64("rank")?);
    let (ped, dq, mw) = (
        ib.i64("ped_discounted_fights")?,
        ib.i64("dq_discounted_fights")?,
        ib.i64("missed_weight_discounted_fights")?,
    );
    let mut db: Vec<usize> = (0..ib.len()).filter(|&i| cost[i] > 0.0).collect();
    db.sort_by(|&i, &j| desc(mu[i], mu[j]));
    let c: Vec<f64> = db.iter().map(|&i| cost[i]).collect();
    let debits = db
        .iter()
        .take(25)
        .map(|&i| {
            J::Arr(vec![
                s(&f[i]),
                num(mu[i], 1),
                num(ur[i], 1),
                J::Int(rank[i]),
                num(cost[i], 1),
                J::Int(ped[i]),
                J::Int(dq[i]),
                J::Int(mw[i]),
            ])
        })
        .collect();
    let labels = [
        ("ped", "PED-confirmed win"),
        ("ped-confirmed_win", "PED-confirmed win"),
        ("dq", "Disqualification win"),
        ("win_by_disqualification", "Disqualification win"),
        ("missed_weight", "Missed-weight win"),
        ("won_after_missing_weight", "Missed-weight win"),
    ];
    let (lf, lo, lr, ld) = (
        il.str("fighter")?,
        il.str("opponent")?,
        il.str("reason")?,
        il.str("detail")?,
    );
    let (lw, lp, lday) = (
        il.f64("integrity_weight")?,
        il.f64("discount_pct")?,
        il.day("event_date")?,
    );
    let pct: Vec<f64> = (0..il.len())
        .map(|i| {
            if lp[i].is_nan() && !lw[i].is_nan() {
                100.0 * (1.0 - lw[i])
            } else {
                lp[i]
            }
        })
        .collect();
    let mut rows: Vec<usize> = (0..il.len()).collect();
    let day_desc = |a: Option<Day>, b: Option<Day>| match (a, b) {
        (Some(a), Some(b)) => b.cmp(&a),
        (a, b) => a.is_none().cmp(&b.is_none()),
    };
    rows.sort_by(|&i, &j| {
        desc(pct[i], pct[j])
            .then(day_desc(lday[i], lday[j]))
            .then(lf[i].cmp(&lf[j]))
    });
    let fix = |x: &str| opt_s(&x.replace('\u{fffd}', "—"));
    let ledger = rows
        .iter()
        .map(|&i| {
            let raw = lr[i].trim();
            let key = raw.to_lowercase().replace(' ', "_");
            let reason = labels.iter().find(|p| p.0 == key).map_or(raw, |p| p.1);
            J::Arr(vec![
                lday[i].map_or(J::Null, |d| s(&iso(d))),
                fix(&lf[i]),
                fix(&lo[i]),
                fix(reason),
                fix(&ld[i]),
                num(np_round(lw[i], 3), 2),
                num(np_round(pct[i], 1), 2),
            ])
        })
        .collect();
    let min = c.iter().copied().fold(f64::INFINITY, f64::min);
    let max = c.iter().copied().fold(f64::NEG_INFINITY, f64::max);
    Ok(J::Obj(vec![
        ("n".into(), J::Int(db.len() as i64)),
        ("rated".into(), J::Int(ib.len() as i64)),
        ("cost".into(), J::Arr(vec![num(min, 1), num(max, 1)])),
        ("debits".into(), J::Arr(debits)),
        ("ledger".into(), J::Arr(ledger)),
    ]))
}

/// Calibration of the pre-fight Glicko-2 forecast: all bouts, then divisions with 1,000 or more appearances.
fn calib(cr: &Frame) -> Result<J, Error> {
    let (t, v, b) = (
        cr.str("segment_type")?,
        cr.str("segment_value")?,
        cr.i64("prob_bin")?,
    );
    let (p, y, n) = (
        cr.f64("predicted_mean")?,
        cr.f64("empirical_win_rate")?,
        cr.i64("n")?,
    );
    let mut o: Vec<usize> = (0..cr.len()).filter(|&i| t[i] == "overall").collect();
    o.sort_by_key(|&i| b[i]);
    let mut size: HashMap<&str, i64> = HashMap::new();
    for i in (0..cr.len()).filter(|&i| t[i] == "division") {
        *size.entry(&v[i]).or_default() += n[i];
    }
    let big = (0..cr.len()).filter(|&i| {
        t[i] == "division" && SHORT.iter().any(|d| d.0 == v[i]) && size[v[i].as_str()] >= 1000
    });
    let row = |i: usize, seg: &str| {
        J::Arr(vec![
            s(seg),
            J::Int(b[i]),
            num(p[i], 4),
            num(y[i], 4),
            J::Int(n[i]),
        ])
    };
    Ok(J::Arr(
        o.iter()
            .map(|&i| row(i, "All bouts"))
            .chain(big.map(|i| row(i, &v[i])))
            .collect(),
    ))
}

/// The forecast benchmark (given), the fifteen biggest upsets, and win rate against price by age and layoff.
fn market(x: &Inputs) -> Result<(J, J, J, J), Error> {
    let od = Frame::read(
        &x.snapshot.join("odds_lines.parquet"),
        &[
            "odds_data_quality",
            "fight_url",
            "fighter_a",
            "fighter_b",
            "implied_prob_a_no_vig",
            "event_date",
        ],
    )?;
    let (q, url, fa, fb) = (
        od.str("odds_data_quality")?,
        od.str("fight_url")?,
        od.str("fighter_a")?,
        od.str("fighter_b")?,
    );
    let (pa, oday) = (od.f64("implied_prob_a_no_vig")?, od.days("event_date")?);
    let mut bouts: HashMap<&str, Vec<&Bout>> = HashMap::new();
    for b in x
        .staged
        .iter()
        .filter(|b| !b.excluded && !b.draw() && !b.nc() && !b.winner().is_empty())
    {
        bouts.entry(&b.url).or_default().push(b);
    }
    // (odds row, bout, y)
    let m: Vec<(usize, &Bout, f64)> = (0..od.len())
        .filter(|&i| q[i] == "ok")
        .flat_map(|i| {
            bouts
                .get(url[i].as_str())
                .into_iter()
                .flatten()
                .map(move |b| (i, *b))
        })
        .map(|(i, b)| (i, b, if *b.winner() == fa[i] { 1.0 } else { 0.0 }))
        .filter(|&(i, _, _)| (0.001..=0.999).contains(&pa[i]))
        .collect();

    let pw = |r: &(usize, &Bout, f64)| if r.2 == 1.0 { pa[r.0] } else { 1.0 - pa[r.0] };
    let mut up: Vec<&(usize, &Bout, f64)> = m.iter().collect();
    up.sort_by(|a, b| asc(pw(a), pw(b)));
    let strip = Regex::new(r"\b(UFC|Interim|Title|Bout)\b").unwrap();
    let upsets = J::Arr(
        up.iter()
            .take(15)
            .map(|r| {
                let (i, b) = (r.0, r.1);
                let loser = if r.2 == 1.0 { &fb[i] } else { &fa[i] };
                let wc = if b.weight_class.is_empty() {
                    J::Null
                } else {
                    J::Str(
                        strip
                            .replace_all(&b.weight_class, "")
                            .split_whitespace()
                            .collect::<Vec<_>>()
                            .join(" "),
                    )
                };
                J::Arr(vec![
                    s(&iso(oday[i])),
                    s(b.winner()),
                    s(loser),
                    num(pw(r), 3),
                    opt_s(&b.method),
                    J::Bool(b.title),
                    wc,
                ])
            })
            .collect(),
    );

    // Months since each fighter's previous distinct bout date, any promotion.
    let mut seen: Vec<(&str, Day)> = x
        .staged
        .iter()
        .flat_map(|b| [(b.a().as_str(), b.day), (b.b().as_str(), b.day)])
        .collect();
    seen.sort();
    seen.dedup();
    let lay: HashMap<(&str, Day), f64> = seen
        .windows(2)
        .filter(|w| w[0].0 == w[1].0)
        .map(|w| (w[1], (w[1].1 - w[0].1) as f64 / DAYS_PER_MONTH))
        .collect();
    // (age, layoff, won, priced) per corner, a-sides first.
    let mut corners: Vec<(f64, f64, f64, f64)> = Vec::new();
    for side in [true, false] {
        for r in &m {
            let i = r.0;
            let f = if side { fa[i].as_str() } else { fb[i].as_str() };
            let d = oday[i];
            let age = x
                .births
                .get(f)
                .map_or(f64::NAN, |b| (d - b) as f64 / JULIAN_YEAR_DAYS);
            let won = if side { r.2 } else { 1.0 - r.2 };
            let priced = if side { pa[i] } else { 1.0 - pa[i] };
            corners.push((
                age,
                lay.get(&(f, d)).copied().unwrap_or(f64::NAN),
                won,
                priced,
            ));
        }
    }
    let bands = |col: fn(&(f64, f64, f64, f64)) -> f64, b: &[(f64, f64, &str)]| {
        J::Arr(
            b.iter()
                .map(|&(lo, hi, lab)| {
                    let r: Vec<&(f64, f64, f64, f64)> = corners
                        .iter()
                        .filter(|c| col(c) >= lo && col(c) < hi)
                        .collect();
                    let n = r.len() as f64;
                    let won: Vec<f64> = r.iter().map(|c| c.2).collect();
                    let priced: Vec<f64> = r.iter().map(|c| c.3).collect();
                    let e: Vec<f64> = r.iter().map(|c| c.2 - c.3).collect();
                    J::Arr(vec![
                        s(lab),
                        J::Int(r.len() as i64),
                        num(psum(&won) / n, 4),
                        num(psum(&priced) / n, 4),
                        num(var(&e, 1).sqrt() / n.sqrt(), 4),
                    ])
                })
                .collect(),
        )
    };
    Ok((
        J::from(x.market),
        upsets,
        bands(|c| c.0, &AGE_BANDS),
        bands(|c| c.1, &LAYOFF_BANDS),
    ))
}
