//! Career and current division of each fighter (`division_resume_rows`, `primary_division_rows`).
//!
//! Appearances in a reported division are joined to the fighter's WHR path on
//! (fighter, date, event); a fighter with k path rows and k bouts on one card
//! contributes k² joined rows, as the pandas many-to-many merge did. Per
//! (fighter, division):
//!
//! `eff = n + 0.75·title + 1.0·title wins + 0.75·defences`,
//! `recency = Σ 0.5^(age/1095 days)`, `reliability = eff/(eff + 8)`.
//!
//! The career division maximises (eff, recency); the current division is the
//! one with the latest title win, then eff, else the career division. Only
//! weight-limited divisions qualify unless a fighter has no other. The division
//! score is a further tie-break in the source; it is not ported, and a tie on
//! the keys above is an `Error` naming the fighter, not a silent pick.

use std::collections::HashMap;

use crate::appearances::Appearance;
use crate::bouts::Bout;
use crate::divisions::normalize;
use crate::error::Error;
use crate::fm;
use crate::frame::{Day, Table};
use crate::history::History;
use crate::stats::psum;

/// `DIVISION_WEIGHT_LIMIT_LB` keys: the divisions a fighter can call home.
const REAL: [&str; 12] = [
    "Women's Strawweight",
    "Women's Flyweight",
    "Women's Bantamweight",
    "Women's Featherweight",
    "Flyweight",
    "Bantamweight",
    "Featherweight",
    "Lightweight",
    "Welterweight",
    "Middleweight",
    "Light Heavyweight",
    "Heavyweight",
];
const K: f64 = 8.0;
const HALFLIFE_DAYS: f64 = 1095.0;

struct Resume<'a> {
    division: &'a str,
    eff: f64,
    recency: f64,
    last_win: Option<Day>,
}

/// `apps` are `perf::appearances(rated)`; the joined division is the reported one, never the vote.
pub fn primary(rated: &[Bout], apps: &[Appearance], history: &History) -> Result<Table, Error> {
    let reported: HashMap<&str, Option<String>> = rated
        .iter()
        .map(|b| (b.url.as_str(), normalize(&b.weight_class)))
        .collect();
    // Joined rows as (appearance, multiplicity).
    let joined: Vec<(&Appearance, &str, usize)> = apps
        .iter()
        .filter_map(|a| {
            let d = reported[a.url.as_str()].as_deref()?;
            let m = history
                .of(&a.fighter)
                .iter()
                .filter(|r| r.day == a.day && r.event == a.event && !r.mu.is_nan())
                .count();
            (m > 0).then_some((a, d, m))
        })
        .collect();
    let as_of = joined.iter().map(|j| j.0.day).max().unwrap_or(0);
    // Groups keyed (fighter, division) in first-appearance order.
    let mut index: HashMap<(&str, &str), usize> = HashMap::new();
    let mut groups: Vec<(&str, &str, Vec<(&Appearance, usize)>)> = Vec::new();
    for &(a, d, m) in &joined {
        let g = *index.entry((a.fighter.as_str(), d)).or_insert_with(|| {
            groups.push((a.fighter.as_str(), d, Vec::new()));
            groups.len() - 1
        });
        groups[g].2.push((a, m));
    }
    let mut by_fighter: HashMap<&str, Vec<Resume>> = HashMap::new();
    let mut order: Vec<&str> = Vec::new();
    for (f, d, mut rows) in groups {
        rows.sort_by(|x, y| (x.0.day, &x.0.event).cmp(&(y.0.day, &y.0.event)));
        let (mut n, mut title, mut wins, mut defences, mut recency, mut last_win) =
            (0usize, 0usize, 0usize, 0usize, Vec::new(), None);
        for (a, m) in rows {
            let t = a.title || a.interim;
            let w = t && a.score >= 1.0;
            n += m;
            title += m * t as usize;
            wins += m * w as usize;
            defences += m * (w && (a.champion || a.interim_champion)) as usize;
            recency.extend(std::iter::repeat_n(
                fm::pow(0.5, (as_of - a.day).max(0) as f64 / HALFLIFE_DAYS),
                m,
            ));
            if w {
                last_win = last_win.max(Some(a.day));
            }
        }
        let eff = n as f64 + 0.75 * title as f64 + 1.0 * wins as f64 + 0.75 * defences as f64;
        if !by_fighter.contains_key(f) {
            order.push(f);
        }
        by_fighter.entry(f).or_default().push(Resume {
            division: d,
            eff,
            recency: psum(&recency),
            last_win,
        });
    }
    let reliability = |r: &Resume| r.eff / (r.eff + K);
    let mut out: (Vec<String>, Vec<String>, Vec<f64>, Vec<String>, Vec<f64>) = Default::default();
    for f in order {
        let rs = &by_fighter[f];
        let real: Vec<&Resume> = rs.iter().filter(|r| REAL.contains(&r.division)).collect();
        let cand = if real.is_empty() {
            rs.iter().collect()
        } else {
            real
        };
        let career = cand[best(f, &cand, &|r| (r.eff, r.recency))?.unwrap()];
        let champ: Vec<&Resume> = cand
            .iter()
            .copied()
            .filter(|r| r.last_win.is_some())
            .collect();
        let current =
            best(f, &champ, &|r| (r.last_win.unwrap() as f64, r.eff))?.map_or(career, |i| champ[i]);
        out.0.push(f.to_string());
        out.1.push(career.division.to_string());
        out.2.push(reliability(career));
        out.3.push(current.division.to_string());
        out.4.push(reliability(current));
    }
    Ok(Table::default()
        .str("fighter", &out.0)
        .str("career_division", &out.1)
        .f64("career_division_reliability", &out.2)
        .str("current_division", &out.3)
        .f64("current_division_reliability", &out.4))
}

/// The index of the unique maximum of `key`; `None` for no candidate, an error for a tie.
fn best(
    f: &str,
    c: &[&Resume],
    key: &dyn Fn(&Resume) -> (f64, f64),
) -> Result<Option<usize>, Error> {
    let Some(top) = (0..c.len()).max_by(|&i, &j| key(c[i]).partial_cmp(&key(c[j])).unwrap()) else {
        return Ok(None);
    };
    if c.iter().filter(|r| key(r) == key(c[top])).count() > 1 {
        return Err(Error::at(
            f,
            "division pick ties on its live keys; the division score tie-break is needed",
        ));
    }
    Ok(Some(top))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn resume(division: &str, eff: f64) -> Resume<'_> {
        Resume {
            division,
            eff,
            recency: 1.0,
            last_win: None,
        }
    }

    #[test]
    fn a_tie_names_the_fighter() {
        let (a, b) = (resume("Lightweight", 5.0), resume("Welterweight", 5.0));
        let key = |r: &Resume| (r.eff, r.recency);
        let e = best("Jane Doe", &[&a, &b], &key).unwrap_err();
        assert!(e.0.starts_with("Jane Doe: division pick ties"), "{e}");
        assert_eq!(
            best("Jane Doe", &[&a, &resume("Heavyweight", 6.0)], &key),
            Ok(Some(1))
        );
        assert_eq!(best("Jane Doe", &[], &key), Ok(None));
    }
}
