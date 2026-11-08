//! The Current score: the All-time formula over the last 18 months, on unadjusted ratings.
//!
//! Title and résumé points sum only wins on or after the window start, each still priced
//! against everything known about the opponent. The skill part is the aged rating capped at
//! the strongest opponent ever beaten (going in), shrunk toward the contender line by the
//! exposure factor, `1750 + e (level − 1750)`, and its excess over the line. Owner decisions
//! of 2026-10-14 (docs/DECISIONS.md).

use std::collections::HashMap;

use crate::bouts::Bout;
use crate::error::Error;
use crate::frame::{Day, Frame, Table};
use crate::legacy::{points, resume_ledger, resume_rows, title_ledger, title_rows, total, Pricing};
use crate::orgs::Org;
use crate::policy::{is_ufc, CONTENDER, DAYS_PER_MONTH};
use crate::stats::np_round;

pub const WINDOW_MONTHS: f64 = 18.0;
/// `current_score_rows` for every fighter of `cur` (`fighter`, `mu_whr_age_activity_adjusted`,
/// `public_legacy_exposure_factor`); `p` reads raw `mu_whr`; `recorded` holds every prepared bout.
pub fn score(
    cur: &Frame,
    pools: &HashMap<String, Option<String>>,
    rated: &[Bout],
    recorded: &[Bout],
    p: &Pricing,
    ctx: &HashMap<String, Org>,
) -> Result<Table, Error> {
    let reference: Day = rated
        .iter()
        .map(|b| b.day)
        .max()
        .ok_or_else(|| Error::at("current", "no rated bouts"))?;
    let since = reference as f64 - WINDOW_MONTHS * DAYS_PER_MONTH;
    let fighters = cur.str("fighter")?;
    let e: Vec<f64> = cur
        .f64("public_legacy_exposure_factor")?
        .into_iter()
        .map(|x| if x.is_nan() { 1.0 } else { x })
        .collect();
    let aged = cur.f64("mu_whr_age_activity_adjusted")?;
    let title = title_ledger(&title_rows(rated, p, pools, ctx, Some(since)));
    let resume = resume_ledger(&resume_rows(rated, p, Some(since)));
    let mut title_wins: HashMap<&str, i64> = HashMap::new();
    for b in rated.iter().filter(|b| {
        b.title
            && !(b.excluded || b.draw() || b.nc())
            && b.day as f64 >= since
            && !b.winner().is_empty()
    }) {
        *title_wins.entry(b.winner()).or_insert(0) += 1;
    }
    let mut best: HashMap<&str, f64> = HashMap::new();
    for b in rated {
        for (f, o) in [(b.a(), b.b()), (b.b(), b.a())] {
            if b.winner() != f {
                continue;
            }
            if let Some(r) = p.h.before(o, b.day) {
                let m = best.entry(f).or_insert(f64::NEG_INFINITY);
                *m = m.max(r.mu);
            }
        }
    }
    let mut last: HashMap<&str, Day> = HashMap::new();
    for b in recorded.iter().filter(|b| is_ufc(b)) {
        for f in [b.a(), b.b()] {
            let d = last.entry(f).or_insert(b.day);
            *d = (*d).max(b.day);
        }
    }
    let n = fighters.len();
    let ts: Vec<f64> = fighters
        .iter()
        .map(|f| 1000.0 * title.get(f).map_or(0.0, |x| x.0))
        .collect();
    let rs: Vec<f64> = (0..n)
        .map(|i| 1000.0 * resume.get(&fighters[i]).map_or(0.0, |x| x.0) * e[i])
        .collect();
    let bw: Vec<f64> = fighters
        .iter()
        .map(|f| best.get(f.as_str()).copied().unwrap_or(f64::NAN))
        .collect();
    // The aged level, capped at the best win; unknown where nothing was beaten.
    let level: Vec<f64> = (0..n)
        .map(|i| {
            let capped = if aged[i] <= bw[i] { aged[i] } else { bw[i] };
            CONTENDER + e[i].clamp(0.0, 1.0) * (capped - CONTENDER)
        })
        .collect();
    let ks: Vec<f64> = level
        .iter()
        .map(|l| {
            if l.is_nan() {
                0.0
            } else {
                (l - CONTENDER).max(0.0)
            }
        })
        .collect();
    let score = total(&points(&ts, &ks, &rs));
    let lu: Vec<Option<Day>> = fighters
        .iter()
        .map(|f| last.get(f.as_str()).copied())
        .collect();
    let months: Vec<f64> = lu
        .iter()
        .map(|d| {
            d.map_or(f64::NAN, |d| {
                np_round(((reference - d) as f64 / DAYS_PER_MONTH).max(0.0), 2)
            })
        })
        .collect();
    let int = |m: &dyn Fn(&str) -> i64| fighters.iter().map(|f| m(f)).collect::<Vec<i64>>();
    Ok(Table::default()
        .str("fighter", &fighters)
        .f64("current_title_score", &ts)
        .i64(
            "current_title_wins",
            &int(&|f| title_wins.get(f).copied().unwrap_or(0)),
        )
        .f64("current_resume_score", &rs)
        .i64(
            "current_contender_wins",
            &int(&|f| resume.get(f).map_or(0, |x| x.1)),
        )
        .f64("current_best_win_mu", &bw)
        .f64("current_skill_level", &level)
        .f64("current_skill_score", &ks)
        .f64("current_score", &score)
        .day("last_ufc_event_date", &lu)
        .f64("months_since_ufc", &months))
}
