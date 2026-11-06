//! The All-time (public legacy) score: title, skill and résumé points.
//!
//! S = 1000 [a (T/n_T)^p + (1 − a)(s (K/n_K)^p + (1 − s)(R/n_R)^p)], a = 0.30, s = 0.25, p = ½,
//! each n the mean of its part's hundred largest positive values over every fighter.
//!   T = 1000 Σ q⁴ over title wins, q = 1/(1 + 10^(−(μ_opp − bar)/400)): the opponent's era
//!       rating strictly before the bout, less 90 Elo per excess turnaround of layoff, against
//!       the opponent's division-year 90th percentile (≥ 5 fighter-years) or the nearest
//!       year's contender line; both sides carry +54 Elo once the fighter had fought in the UFC;
//!       a major-promotion (tier 1) win is floored at 0.05 + 0.95 q⁴.
//!   K = exposure · Career Skill Mass.
//!   R = 1000 · exposure · Σ_years min(1, Σ q³) over wins against opponents rated ≥ 1,750 with
//!       ≥ 8 UFC bouts, q against the fixed 1,750.
//! Exposure is the share of a career proven against top organisations, shrunk n/(n + 5) toward
//! the population. Decisions: docs/DECISIONS.md.

use std::collections::{BTreeMap, HashMap, HashSet};

use crate::appearances::Appearance;
use crate::bouts::Bout;
use crate::divisions::{normalize, ufc_title};
use crate::era::{contender_bar, year, CAREER_N};
use crate::frame::{Day, Frame, Table};
use crate::history::{History, Row};
use crate::layoff::Layoff;
use crate::orgs::{Org, Rules, TIER4};
use crate::skill::annual;
use crate::stats::{kahan_mean, kahan_sum, mean, psum, quantile};

/// `CONTENDER_LINE_MU`.
pub const CONTENDER: f64 = 1750.0;
const MIN_OPPONENT_UFC_BOUTS: usize = 8;
const POOL_OFFSET: f64 = 54.0;
const MAJOR_FLOOR: f64 = 0.05;
const TITLE_DIVISION_MIN_YEARS: usize = 5;
const YEAR_CAP: f64 = 1.0;
const SCALE: f64 = 1000.0;
const SHRINK: f64 = 5.0;
const W: [f64; 3] = [0.30, 0.70 * 0.25, 0.70 * 0.75];
const TOP_N: usize = 100;
const POWER: f64 = 0.5;

/// One priced win: who beat whom, when, the opponent's price and the win's weight.
#[derive(Clone, Debug)]
pub struct Win {
    pub url: String,
    pub fighter: String,
    pub opponent: String,
    pub day: Day,
    pub mu: f64,
    pub weight: f64,
    pub qualifying: bool,
}

/// `winning_sides`: the a-side wins of every bout, then the b-side wins, in date order.
fn wins<'a>(bouts: impl Iterator<Item = &'a Bout> + Clone) -> Vec<(&'a Bout, &'a str, &'a str)> {
    let mut out: Vec<(&Bout, &str, &str)> = bouts
        .clone()
        .filter(|b| b.winner() == b.a())
        .map(|b| (b, b.a().as_str(), b.b().as_str()))
        .collect();
    out.extend(
        bouts
            .filter(|b| b.winner() == b.b())
            .map(|b| (b, b.b().as_str(), b.a().as_str())),
    );
    out.sort_by_key(|w| w.0.day);
    out
}

fn ufc_family(b: &Bout) -> bool {
    b.corpus == "ufc" || b.corpus == "pre_unified"
}

/// `ufc_debut_dates_from`: first UFC-family bout of each fighter.
pub fn debuts(bouts: &[Bout]) -> HashMap<String, Day> {
    let mut out: HashMap<String, Day> = HashMap::new();
    for b in bouts.iter().filter(|b| ufc_family(b)) {
        for f in [b.a(), b.b()] {
            let d = out.entry(f.clone()).or_insert(b.day);
            *d = (*d).min(b.day);
        }
    }
    out
}

/// `ufc_bout_counts`: UFC-family model bouts per fighter.
pub fn ufc_bouts(bouts: &[Bout]) -> HashMap<String, usize> {
    let mut out = HashMap::new();
    for b in bouts.iter().filter(|b| ufc_family(b) && b.model) {
        for f in [b.a(), b.b()] {
            *out.entry(f.clone()).or_insert(0) += 1;
        }
    }
    out
}

/// `title_quality`: q^k, q the chance a fighter at `bar` loses to an opponent rated `mu`.
pub fn quality(mu: f64, bar: f64, k: f64) -> f64 {
    (1.0 / (1.0 + 10f64.powf(-(mu - bar) / 400.0))).powf(k)
}

/// The rating paths and pricing rules every ledger shares.
pub struct Pricing<'a> {
    pub h: &'a History,
    pub rating: fn(&Row) -> f64,
    pub layoff: &'a Layoff,
}

impl Pricing<'_> {
    /// `opponent_ratings` then `attach_opponent_layoff`, plus `offset` when the opponent had
    /// fought in the UFC before the bout; `None` for an unrated opponent.
    fn price(
        &self,
        opponent: &str,
        day: Day,
        debuts: Option<&HashMap<String, Day>>,
    ) -> Option<f64> {
        let mu = (self.rating)(self.h.before(opponent, day)?);
        let offset = debuts
            .and_then(|d| d.get(opponent))
            .is_some_and(|&d| d < day);
        Some(
            self.layoff
                .price(mu + if offset { POOL_OFFSET } else { 0.0 }, opponent, day),
        )
    }
}

fn flagged(b: &Bout) -> bool {
    b.excluded || b.draw() || b.nc()
}

/// `title_quality_rows`: every title win priced, on or after `since` (fractional day) when given.
pub fn title_rows(
    rated: &[Bout],
    p: &Pricing,
    pools: &HashMap<String, Option<String>>,
    ctx: &HashMap<String, Org>,
    since: Option<f64>,
) -> Vec<Win> {
    let debut = debuts(rated);
    let annual: Vec<(&str, i32, f64)> = annual(p.h, p.rating)
        .into_iter()
        .map(|(f, y, m)| {
            (
                f,
                y,
                m + if debut.get(f).is_some_and(|&d| year(d) <= y) {
                    POOL_OFFSET
                } else {
                    0.0
                },
            )
        })
        .collect();
    let mut by_year: BTreeMap<i32, Vec<f64>> = BTreeMap::new();
    let mut by_division: HashMap<(&str, i32), Vec<f64>> = HashMap::new();
    for &(f, y, m) in &annual {
        by_year.entry(y).or_default().push(m);
        if let Some(Some(d)) = pools.get(f) {
            by_division.entry((d.as_str(), y)).or_default().push(m);
        }
    }
    let bar: Vec<(i32, f64)> = by_year
        .iter()
        .map(|(y, v)| (*y, contender_bar(v, CAREER_N)))
        .filter(|p| !p.1.is_nan())
        .collect();
    let fallback = mean(&annual.iter().map(|x| x.2).collect::<Vec<_>>());
    let local: HashMap<(&str, i32), f64> = by_division
        .into_iter()
        .filter(|(_, v)| v.len() >= TITLE_DIVISION_MIN_YEARS)
        .map(|(k, v)| (k, quantile(&v, 0.90)))
        .collect();
    let bouts = rated.iter().filter(|b| b.title && !flagged(b));
    let mut out = Vec::new();
    for (b, f, o) in wins(bouts) {
        let Some(mu) = p.price(o, b.day, Some(&debut)) else {
            continue;
        };
        let y = year(b.day);
        // The nearest year with a line; the earlier one on a tie.
        let near = bar
            .iter()
            .min_by_key(|(x, _)| (x - y).abs())
            .map_or(fallback, |p| p.1);
        let line = pools
            .get(o)
            .and_then(|d| d.as_deref())
            .and_then(|d| local.get(&(d, y)))
            .copied()
            .unwrap_or(near);
        let q = quality(mu, line, 4.0);
        let weight = if ctx.get(&b.url).is_some_and(|c| c.tier == 1) {
            MAJOR_FLOOR + (1.0 - MAJOR_FLOOR) * q
        } else {
            q
        };
        if since.is_none_or(|s| b.day as f64 >= s) {
            out.push(Win {
                url: b.url.clone(),
                fighter: f.into(),
                opponent: o.into(),
                day: b.day,
                mu,
                weight,
                qualifying: mu >= line,
            });
        }
    }
    out
}

/// `contender_resume_rows`: wins over tested contenders, priced q³ against the fixed line.
pub fn resume_rows(rated: &[Bout], p: &Pricing, since: Option<f64>) -> Vec<Win> {
    let tested = ufc_bouts(rated);
    let mut out = Vec::new();
    for (b, f, o) in wins(rated.iter().filter(|b| !flagged(b))) {
        let Some(mu) = p.price(o, b.day, None) else {
            continue;
        };
        if tested.get(o).copied().unwrap_or(0) < MIN_OPPONENT_UFC_BOUTS || mu < CONTENDER {
            continue;
        }
        if since.is_none_or(|s| b.day as f64 >= s) {
            let weight = quality(mu, CONTENDER, 3.0);
            out.push(Win {
                url: b.url.clone(),
                fighter: f.into(),
                opponent: o.into(),
                day: b.day,
                mu,
                weight,
                qualifying: true,
            });
        }
    }
    out
}

/// `title_quality_ledger`: fighter → (Σ weight, qualifying wins).
pub fn title_ledger(rows: &[Win]) -> HashMap<String, (f64, i64)> {
    let mut g: HashMap<&str, (Vec<f64>, i64)> = HashMap::new();
    for w in rows {
        let e = g.entry(&w.fighter).or_default();
        e.0.push(w.weight);
        e.1 += i64::from(w.qualifying);
    }
    g.into_iter()
        .map(|(f, (v, n))| (f.to_string(), (kahan_sum(&v), n)))
        .collect()
}

/// `contender_resume_ledger`: fighter → (Σ_years min(1, Σ weight), wins).
pub fn resume_ledger(rows: &[Win]) -> HashMap<String, (f64, i64)> {
    let mut g: BTreeMap<(&str, i32), Vec<f64>> = BTreeMap::new();
    for w in rows {
        g.entry((&w.fighter, year(w.day)))
            .or_default()
            .push(w.weight);
    }
    let mut per: BTreeMap<&str, Vec<f64>> = BTreeMap::new();
    for ((f, _), v) in g {
        per.entry(f).or_default().push(kahan_sum(&v).min(YEAR_CAP));
    }
    let mut n: HashMap<&str, i64> = HashMap::new();
    for w in rows {
        *n.entry(&w.fighter).or_insert(0) += 1;
    }
    per.into_iter()
        .map(|(f, v)| (f.to_string(), (kahan_sum(&v), n[f])))
        .collect()
}

/// `_legacy_division_bucket`: a title's division with any women's prefix removed.
fn bucket(weight_class: &str) -> Option<String> {
    let label = normalize(weight_class)?;
    let mut t = label.split_whitespace().collect::<Vec<_>>().join(" ");
    for p in ["Women's ", "Womens ", "Female "] {
        if let Some(r) = t.strip_prefix(p) {
            t = r.trim().to_string();
        }
    }
    (!t.is_empty()).then_some(t)
}

/// Title counts: appearances, wins, defences, distinct divisions won.
type Counts = [i64; 4];

/// `championship_resume_ledger`: counts from the UFC title flags of the appearance rows.
fn appearance_titles(app: &[Appearance]) -> HashMap<String, Counts> {
    let mut out: HashMap<String, Counts> = HashMap::new();
    let mut divisions: HashMap<&str, HashSet<String>> = HashMap::new();
    for a in app {
        let title = a.title || a.interim;
        let win = title && a.score >= 1.0;
        let e = out.entry(a.fighter.clone()).or_default();
        e[0] += i64::from(title);
        e[1] += i64::from(win);
        e[2] += i64::from(win && (a.champion || a.interim_champion));
        if win {
            if let Some(d) = bucket(&a.division) {
                divisions.entry(&a.fighter).or_default().insert(d);
            }
        }
    }
    for (f, d) in divisions {
        out.get_mut(f).unwrap()[3] = d.len() as i64;
    }
    out
}

/// `source_title_resume_ledger`: counts from the bouts' own title flags across promotions.
///
/// A defence is a title win by the reigning winner of the same promotion lineage and division;
/// a title win with no division counts as a defence after the fighter's first in that lineage.
fn source_titles(rated: &[Bout], ctx: &HashMap<String, Org>) -> HashMap<String, Counts> {
    let mut f: Vec<&Bout> = rated
        .iter()
        .filter(|b| {
            if ctx[&b.url].canonical == "UFC" {
                ufc_title(&b.weight_class)
            } else {
                b.title
            }
        })
        .collect();
    f.sort_by(|x, y| (x.day, &x.event, &x.url).cmp(&(y.day, &y.event, &y.url)));
    let mut champion: HashMap<String, &str> = HashMap::new();
    let mut defence: HashSet<(&str, &str)> = HashSet::new();
    for b in &f {
        if b.winner().is_empty() || b.draw() {
            continue;
        }
        let key = format!(
            "{}::{}",
            ctx[&b.url].identity,
            bucket(&b.weight_class).unwrap_or_default()
        );
        if champion.get(&key) == Some(&b.winner().as_str()) {
            defence.insert((&b.url, b.winner()));
        }
        champion.insert(key, b.winner());
    }
    // Undivisioned wins: every win after the first in (fighter, lineage), by (date, url).
    let mut undivided: Vec<(&str, &str, Day, &str)> = f
        .iter()
        .filter(|b| !b.winner().is_empty() && !b.draw() && bucket(&b.weight_class).is_none())
        .map(|b| {
            (
                b.winner().as_str(),
                ctx[&b.url].identity.as_str(),
                b.day,
                b.url.as_str(),
            )
        })
        .collect();
    undivided.sort();
    for w in undivided.windows(2) {
        if (w[0].0, w[0].1) == (w[1].0, w[1].1) {
            defence.insert((w[1].3, w[1].0));
        }
    }
    let mut out: HashMap<String, Counts> = HashMap::new();
    let mut divisions: HashMap<&str, HashSet<String>> = HashMap::new();
    for side in [0, 1] {
        for b in &f {
            let fighter = if side == 0 { b.a() } else { b.b() };
            let win = b.winner() == fighter && !b.draw();
            let e = out.entry(fighter.clone()).or_default();
            e[0] += 1;
            e[1] += i64::from(win);
            e[2] += i64::from(defence.contains(&(b.url.as_str(), fighter.as_str())));
            if win {
                if let Some(d) = bucket(&b.weight_class) {
                    divisions.entry(fighter).or_default().insert(d);
                }
            }
        }
    }
    for (f, d) in divisions {
        out.get_mut(f).unwrap()[3] = d.len() as i64;
    }
    out
}

/// `organization_exposure_ledger`: fighter → (exposure factor, UFC, top-org, unknown-org bouts).
fn exposure(rated: &[Bout], ctx: &HashMap<String, Org>) -> HashMap<String, (f64, i64, i64, i64)> {
    let mut sides: Vec<(&str, Option<f64>, bool)> = Vec::new();
    for side in [0, 1] {
        for b in rated {
            let c = &ctx[&b.url];
            let known = c.canonical != "Unknown";
            sides.push((
                if side == 0 { b.a() } else { b.b() },
                known.then_some(c.factor),
                c.canonical == "UFC",
            ));
        }
    }
    let identified: Vec<f64> = sides.iter().filter_map(|s| s.1).collect();
    let prior = if identified.is_empty() {
        TIER4
    } else {
        psum(&identified) / identified.len() as f64
    };
    let mut g: HashMap<&str, (Vec<f64>, i64, i64, i64)> = HashMap::new();
    for (f, v, ufc) in sides {
        let e = g.entry(f).or_default();
        if let Some(v) = v {
            e.0.push(v);
        }
        e.1 += i64::from(ufc);
        e.2 += i64::from(v.is_some_and(|v| v >= 0.82));
        e.3 += i64::from(v.is_none());
    }
    g.into_iter()
        .map(|(f, (mut v, ufc, top, unknown))| {
            let n = v.len() as f64;
            let own = if v.is_empty() {
                f64::NAN
            } else {
                let m = kahan_mean(&v);
                v.sort_by(|a, b| b.total_cmp(a));
                let k = ((v.len() as f64 * 0.25).ceil() as usize).max(1);
                0.5 * m + 0.5 * psum(&v[..k]) / k as f64
            };
            let w = n / (n + SHRINK);
            let x = w * own + (1.0 - w) * prior;
            (
                f.to_string(),
                (
                    if x.is_nan() {
                        TIER4
                    } else {
                        x.clamp(TIER4, 1.0)
                    },
                    ufc,
                    top,
                    unknown,
                ),
            )
        })
        .collect()
}

/// `_scale`: divide by the mean of the `TOP_N` largest positive values (zero stays zero).
fn scale(v: &[f64]) -> Vec<f64> {
    let mut pos: Vec<f64> = v.iter().copied().filter(|x| *x > 0.0).collect();
    pos.sort_by(|a, b| b.total_cmp(a));
    let top = &pos[..pos.len().min(TOP_N)];
    let n = if top.is_empty() {
        0.0
    } else {
        psum(top) / top.len() as f64
    };
    v.iter()
        .map(|x| if n > 0.0 { x / n } else { x * 0.0 })
        .collect()
}

/// `legacy_points`: 1000 w_i (X_i/n_i)^p of the three parts (title, skill, résumé).
pub fn points(title: &[f64], skill: &[f64], resume: &[f64]) -> [Vec<f64>; 3] {
    let part = |x: &[f64], w: f64| {
        scale(x)
            .into_iter()
            .map(|v| SCALE * w * v.powf(POWER))
            .collect::<Vec<_>>()
    };
    [part(title, W[0]), part(skill, W[1]), part(resume, W[2])]
}

/// Σ of the three parts per fighter, in Python's `sum` order.
pub fn total(p: &[Vec<f64>; 3]) -> Vec<f64> {
    (0..p[0].len())
        .map(|i| 0.0 + p[0][i] + p[1][i] + p[2][i])
        .collect()
}

/// `public_legacy_score_rows` for every fighter of `cur` (`fighter`, `symon_career_skill_mass`).
///
/// `pools` from `skill::pools`; `h` is the era-rated history (`rating` reads `mu_era`).
/// `public_legacy_rank_context_win_mass` is not produced: it reads the retired rank-context sleeve.
pub fn score(
    cur: &Frame,
    pools: &HashMap<String, Option<String>>,
    app: &[Appearance],
    rated: &[Bout],
    p: &Pricing,
    rules: &Rules,
) -> Table {
    let fighters = cur.str("fighter");
    let mass: Vec<f64> = cur
        .f64("symon_career_skill_mass")
        .into_iter()
        .map(|x| if x.is_nan() { 0.0 } else { x })
        .collect();
    let ctx = rules.context(rated);
    let title = title_ledger(&title_rows(rated, p, pools, &ctx, None));
    let resume = resume_ledger(&resume_rows(rated, p, None));
    let (a, s) = (appearance_titles(app), source_titles(rated, &ctx));
    let ex = exposure(rated, &ctx);
    let n = fighters.len();
    let get = |m: &HashMap<String, Counts>, f: &str, i: usize| m.get(f).map_or(0, |c| c[i]);
    let counts: Vec<Counts> = fighters
        .iter()
        .map(|f| std::array::from_fn(|i| get(&a, f, i).max(get(&s, f, i))))
        .collect();
    let e: Vec<f64> = fighters
        .iter()
        .map(|f| ex.get(f).map_or(1.0, |x| x.0))
        .collect();
    let tq: Vec<f64> = fighters
        .iter()
        .map(|f| title.get(f).map_or(0.0, |x| x.0))
        .collect();
    let rq: Vec<f64> = fighters
        .iter()
        .map(|f| resume.get(f).map_or(0.0, |x| x.0))
        .collect();
    let ts: Vec<f64> = tq.iter().map(|x| SCALE * x).collect();
    let rs: Vec<f64> = (0..n).map(|i| SCALE * rq[i] * e[i]).collect();
    let ks: Vec<f64> = (0..n).map(|i| mass[i] * e[i]).collect();
    let total = total(&points(&ts, &ks, &rs));
    let int = |g: &dyn Fn(usize) -> i64| (0..n).map(g).collect::<Vec<i64>>();
    let exi = |f: &str, i: usize| ex.get(f).map_or(0, |x| [x.1, x.2, x.3][i]);
    Table::default()
        .str("fighter", &fighters)
        .f64("public_legacy_score", &total)
        .f64("public_legacy_skill_mass", &mass)
        .f64("public_legacy_skill_score", &ks)
        .f64("public_legacy_exposure_factor", &e)
        .f64("public_legacy_title_score", &ts)
        .f64("public_legacy_title_quality", &tq)
        .i64(
            "public_legacy_qualifying_title_wins",
            &int(&|i| title.get(&fighters[i]).map_or(0, |x| x.1)),
        )
        .f64("public_legacy_resume_score", &rs)
        .f64("public_legacy_resume_quality", &rq)
        .i64(
            "public_legacy_contender_wins",
            &int(&|i| resume.get(&fighters[i]).map_or(0, |x| x.1)),
        )
        .i64("public_legacy_title_appearances", &int(&|i| counts[i][0]))
        .i64("public_legacy_title_wins", &int(&|i| counts[i][1]))
        .i64("public_legacy_title_defenses", &int(&|i| counts[i][2]))
        .i64("public_legacy_title_win_divisions", &int(&|i| counts[i][3]))
        .f64(
            "public_legacy_multi_division_bonus",
            &(0..n)
                .map(|i| (counts[i][3] - 1).max(0) as f64)
                .collect::<Vec<_>>(),
        )
        .i64("public_legacy_ufc_bouts", &int(&|i| exi(&fighters[i], 0)))
        .i64(
            "public_legacy_top_org_bouts",
            &int(&|i| exi(&fighters[i], 1)),
        )
        .i64(
            "public_legacy_unknown_org_bouts",
            &int(&|i| exi(&fighters[i], 2)),
        )
}
