//! Fighter-perspective appearances of the rated bouts, with division and title lineage.
//!
//! A bout keeps its reported division; an unlabelled bout borrows one by vote
//! (`fill_division_from_career`): each participant offers its four nearest
//! labelled bouts by date, the most votes win, then the closest gap, then the
//! label. Champion state per division is the winner of the latest real UFC
//! title bout in it, read before each card and advanced after it, so same-card
//! title bouts cannot leak into each other (`prefight_ranking_context`).

use std::collections::HashMap;

use crate::appearances::Appearance;
use crate::bouts::Bout;
use crate::divisions::{normalize, ufc_title};
use crate::frame::Day;

const NEIGHBOURS: usize = 4;

pub fn interim_title_bout(weight_class: &str) -> bool {
    ufc_title(weight_class) && weight_class.to_lowercase().contains("interim")
}

/// Division of each bout: reported, else the career vote; `None` when neither exists.
pub fn filled_divisions(bouts: &[Bout]) -> Vec<Option<String>> {
    let reported: Vec<Option<String>> = bouts.iter().map(|b| normalize(&b.weight_class)).collect();
    // Sides in pandas concat order: every a-side, then every b-side.
    let sides = || {
        (0..bouts.len())
            .map(|i| (i, bouts[i].a()))
            .chain((0..bouts.len()).map(|i| (i, bouts[i].b())))
    };
    // Labelled (date, division) per fighter, first side per (fighter, date) kept, in date order.
    let mut known: HashMap<&str, Vec<(Day, &str)>> = HashMap::new();
    for (i, f) in sides() {
        if let Some(d) = &reported[i] {
            let k = known.entry(f.as_str()).or_default();
            if !k.iter().any(|x| x.0 == bouts[i].day) {
                k.push((bouts[i].day, d));
            }
        }
    }
    for k in known.values_mut() {
        k.sort_by_key(|x| x.0);
    }
    let mut votes: HashMap<usize, Vec<(&str, i64)>> = HashMap::new();
    for (i, f) in sides() {
        if reported[i].is_some() {
            continue;
        }
        let Some(k) = known.get(f.as_str()) else {
            continue;
        };
        let day = bouts[i].day;
        let p = k.partition_point(|x| x.0 < day);
        let lo = p.saturating_sub(NEIGHBOURS);
        let hi = (p + NEIGHBOURS).min(k.len());
        let mut w: Vec<(i64, &str)> = k[lo..hi]
            .iter()
            .map(|x| ((x.0 - day).abs() as i64, x.1))
            .collect();
        w.sort_by_key(|x| x.0);
        votes
            .entry(i)
            .or_default()
            .extend(w.into_iter().take(NEIGHBOURS).map(|(g, d)| (d, g)));
    }
    reported
        .iter()
        .enumerate()
        .map(|(i, r)| {
            r.clone().or_else(|| {
                let mut t: HashMap<&str, (usize, i64)> = HashMap::new();
                for &(d, g) in votes.get(&i)? {
                    let e = t.entry(d).or_insert((0, i64::MAX));
                    e.0 += 1;
                    e.1 = e.1.min(g);
                }
                t.into_iter()
                    .min_by_key(|&(d, (v, g))| (std::cmp::Reverse(v), g, d))
                    .map(|x| x.0.to_string())
            })
        })
        .collect()
}

/// `build_performance_appearances`, live columns: all a-sides in bout order, then all b-sides.
/// `rated` is ordered by `(day, event)`, so cards are consecutive runs.
pub fn appearances(rated: &[Bout]) -> Vec<Appearance> {
    let division = filled_divisions(rated);
    let n = rated.len();
    let (mut champ, mut interim_champ) = (vec![[false; 2]; n], vec![[false; 2]; n]);
    let mut champions: HashMap<&str, &str> = HashMap::new();
    let mut interims: HashMap<&str, &str> = HashMap::new();
    let names: std::collections::HashSet<&str> = rated
        .iter()
        .flat_map(|b| [b.a().as_str(), b.b().as_str()])
        .filter(|f| !f.is_empty())
        .collect();
    let mut lo = 0;
    while lo < n {
        let hi = lo
            + rated[lo..]
                .iter()
                .take_while(|b| b.day == rated[lo].day && b.event == rated[lo].event)
                .count();
        for k in lo..hi {
            if let Some(d) = division[k].as_deref() {
                for (s, f) in [rated[k].a(), rated[k].b()].into_iter().enumerate() {
                    champ[k][s] = champions.get(d) == Some(&f.as_str());
                    interim_champ[k][s] = interims.get(d) == Some(&f.as_str());
                }
            }
        }
        for k in lo..hi {
            let (b, Some(d)) = (&rated[k], division[k].as_deref()) else {
                continue;
            };
            // A winner who is no rated fighter leaves the lineage unchanged.
            if !names.contains(b.winner().as_str()) || !ufc_title(&b.weight_class) {
                continue;
            }
            if interim_title_bout(&b.weight_class) {
                interims.insert(d, b.winner());
            } else {
                champions.insert(d, b.winner());
                interims.remove(d);
            }
        }
        lo = hi;
    }
    let mut out = Vec::with_capacity(2 * n);
    for s in 0..2 {
        for (k, b) in rated.iter().enumerate() {
            let (fighter, opponent) = if s == 0 {
                (b.a(), b.b())
            } else {
                (b.b(), b.a())
            };
            let won = b.winner() == fighter && !b.draw();
            out.push(Appearance {
                url: b.url.clone(),
                day: b.day,
                event: b.event.clone(),
                fighter: fighter.clone(),
                opponent: opponent.clone(),
                division: division[k].clone().unwrap_or_default(),
                won,
                draw: b.draw(),
                score: if b.draw() {
                    0.5
                } else if won {
                    1.0
                } else {
                    0.0
                },
                method: b.method.clone(),
                title: ufc_title(&b.weight_class),
                interim: interim_title_bout(&b.weight_class),
                champion: champ[k][s],
                interim_champion: interim_champ[k][s],
            });
        }
    }
    out
}
