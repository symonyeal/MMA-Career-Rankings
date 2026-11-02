//! Per-fighter facts beside the ratings: record, latest division, gender,
//! inactivity, divisions and integrity counts (`rate_snapshot` attachments).
//!
//! Gender is read off the bout graph (`_female_by_bout_graph`): men and women
//! are disjoint components, so a component whose bouts are billed "Women's …"
//! more often than with a men's-only label is women's, and the label
//! propagates to every fighter in it.

use std::collections::{BTreeMap, HashMap, HashSet, VecDeque};

use crate::appearances::Appearance;
use crate::bouts::Bout;
use crate::division;
use crate::divisions::normalize;
use crate::frame::{Day, Frame, Table};
use crate::history::History;
use crate::stats::np_round;

const MENS_ONLY: [&str; 5] = [
    "Light Heavyweight",
    "Heavyweight",
    "Middleweight",
    "Welterweight",
    "Lightweight",
];
const DAYS_PER_MONTH: f64 = 365.25 / 12.0;

fn women(rated: &[Bout]) -> HashSet<&str> {
    let mut adj: HashMap<&str, Vec<&str>> = HashMap::new();
    for b in rated.iter().filter(|b| !b.a.is_empty() && !b.b.is_empty()) {
        adj.entry(&b.a).or_default().push(&b.b);
        adj.entry(&b.b).or_default().push(&b.a);
    }
    let mut comp: HashMap<&str, usize> = HashMap::new();
    let mut n = 0;
    for &s in adj.keys() {
        if comp.contains_key(s) {
            continue;
        }
        let mut q = VecDeque::from([s]);
        comp.insert(s, n);
        while let Some(x) = q.pop_front() {
            for &y in &adj[x] {
                if !comp.contains_key(y) {
                    comp.insert(y, n);
                    q.push_back(y);
                }
            }
        }
        n += 1;
    }
    let mut tally = vec![(0usize, 0usize); n];
    for b in rated {
        let Some(&c) = comp.get(b.a.as_str()) else {
            continue;
        };
        let d = normalize(&b.weight_class).unwrap_or_default();
        tally[c].0 += d.starts_with("Women's") as usize;
        tally[c].1 += MENS_ONLY.contains(&d.as_str()) as usize;
    }
    comp.into_iter()
        .filter(|(_, c)| tally[*c].0 > tally[*c].1)
        .map(|(f, _)| f)
        .collect()
}

/// `prepared` holds every recorded bout of the scope (inactivity and integrity counts read it);
/// `rated` the bouts that enter the rating; `snapshot_max` the latest rated date.
pub fn columns(
    prepared: &[Bout],
    rated: &[Bout],
    history: &History,
    apps: &[Appearance],
    snapshot_max: Day,
) -> Frame {
    // Record and latest division over rated sides in pandas order: a-sides, then b-sides.
    let sides = || {
        rated
            .iter()
            .map(|b| (&b.a, b))
            .chain(rated.iter().map(|b| (&b.b, b)))
    };
    let mut record: BTreeMap<&str, [i64; 3]> = BTreeMap::new();
    let mut recent: HashMap<&str, Vec<(Day, &str, Option<String>)>> = HashMap::new();
    for (f, b) in sides().filter(|(f, _)| !f.is_empty()) {
        let r = record.entry(f).or_default();
        r[0] += (b.winner == *f && !b.draw) as i64;
        r[1] += (!b.winner.is_empty() && b.winner != *f && !b.draw) as i64;
        r[2] += b.draw as i64;
        recent
            .entry(f)
            .or_default()
            .push((b.day, &b.event, normalize(&b.weight_class)));
    }
    let female = women(rated);
    let mut last: HashMap<&str, Day> = HashMap::new();
    let mut counts: HashMap<&str, [i64; 3]> = HashMap::new();
    for b in prepared {
        for f in [&b.a, &b.b].into_iter().filter(|f| !f.is_empty()) {
            let d = last.entry(f).or_insert(b.day);
            *d = (*d).max(b.day);
        }
        if b.ped && !b.ped_fighter.is_empty() {
            counts.entry(&b.ped_fighter).or_default()[0] += 1;
        }
        if b.dq && !b.winner.is_empty() {
            counts.entry(&b.winner).or_default()[1] += 1;
        }
        if b.missed_weight && !b.winner.is_empty() {
            counts.entry(&b.winner).or_default()[2] += 1;
        }
    }
    let fighters: Vec<&str> = record.keys().copied().collect();
    let latest = |f: &str| {
        let mut v = recent[f].clone();
        v.sort_by(|x, y| (x.0, x.1).cmp(&(y.0, y.1)));
        v.into_iter().rev().find_map(|x| x.2).unwrap_or_default()
    };
    let months = |f: &str| {
        np_round(
            ((snapshot_max - last[f]) as f64 / DAYS_PER_MONTH).max(0.0),
            2,
        )
    };
    let c = |f: &str, i: usize| counts.get(f).map_or(0, |c| c[i]);
    let base = Table::default()
        .str("fighter", &fighters)
        .i64(
            "wins",
            &fighters.iter().map(|f| record[f][0]).collect::<Vec<_>>(),
        )
        .i64(
            "losses",
            &fighters.iter().map(|f| record[f][1]).collect::<Vec<_>>(),
        )
        .i64(
            "draws",
            &fighters.iter().map(|f| record[f][2]).collect::<Vec<_>>(),
        )
        .opt_str(
            "recent_division",
            &fighters.iter().map(|f| latest(f)).collect::<Vec<_>>(),
        )
        .str(
            "gender",
            &fighters
                .iter()
                .map(|f| if female.contains(f) { "F" } else { "M" })
                .collect::<Vec<_>>(),
        )
        .day(
            "last_recorded_event_date",
            &fighters.iter().map(|f| Some(last[f])).collect::<Vec<_>>(),
        )
        .f64(
            "months_inactive",
            &fighters.iter().map(|f| months(f)).collect::<Vec<_>>(),
        )
        .i64(
            "ped_confirmed_fights",
            &fighters.iter().map(|f| c(f, 0)).collect::<Vec<_>>(),
        )
        .i64(
            "dq_wins",
            &fighters.iter().map(|f| c(f, 1)).collect::<Vec<_>>(),
        )
        .i64(
            "missed_weight_wins",
            &fighters.iter().map(|f| c(f, 2)).collect::<Vec<_>>(),
        )
        .frame();
    let div = division::primary(rated, apps, history).frame();
    let at: HashMap<String, usize> = div
        .str("fighter")
        .into_iter()
        .enumerate()
        .map(|(i, f)| (f, i))
        .collect();
    let idx: Vec<Option<usize>> = fighters.iter().map(|f| at.get(*f).copied()).collect();
    base.hstack(&[&div
        .select(&[
            "career_division",
            "career_division_reliability",
            "current_division",
            "current_division_reliability",
        ])
        .take(&idx)])
}
