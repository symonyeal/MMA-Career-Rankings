//! Dominance of each win (`per_fight_dominance`, `per_fighter_dominance`).
//!
//! Per bout, significant strikes, submission attempts and control seconds are
//! summed over rounds and divided by bout minutes ((end round − 1)·5 + end
//! seconds/60, at least 1); the a-minus-b differences are z-scored (ddof 0) over
//! the bouts with round data on both sides and summed. Decisions add the
//! z-scored mean judge margin, z taken over the decisions with a card. A
//! finish win is floored at ±2.75 for its winner. A fighter's dominance is the
//! mean over their wins, read from the winner's side.

use std::collections::{BTreeMap, HashMap};
use std::path::Path;

use crate::bouts::Bout;
use crate::frame::{Day, Frame, Table};
use crate::names::Names;
use crate::stats::{kahan_mean, psum};

const FINISH_FLOOR_Z: f64 = 2.75;

/// pandas `(s - s.mean()) / s.std(ddof=0)`, NaN-skipping; all zeros when the spread is 0 or undefined.
fn z(s: &[f64]) -> Vec<f64> {
    let filled: Vec<f64> = s
        .iter()
        .map(|x| if x.is_nan() { 0.0 } else { *x })
        .collect();
    let n = s.iter().filter(|x| !x.is_nan()).count() as f64;
    let m = psum(&filled) / n;
    let sq: Vec<f64> = s
        .iter()
        .map(|x| if x.is_nan() { 0.0 } else { (m - x) * (m - x) })
        .collect();
    let sd = (psum(&sq) / n).sqrt();
    if sd == 0.0 || sd.is_nan() {
        return vec![0.0; s.len()];
    }
    s.iter().map(|x| (x - m) / sd).collect()
}

/// Mean of the integer tokens of a judge-total string such as `"29 28 28"`.
fn points(s: &str) -> f64 {
    let t: Vec<f64> = s
        .replace(',', " ")
        .split_whitespace()
        .filter(|t| {
            let u = t.trim_start_matches('-');
            !u.is_empty() && u.chars().all(|c| c.is_ascii_digit())
        })
        .map(|t| t.parse::<i64>().unwrap() as f64)
        .collect();
    if t.is_empty() {
        f64::NAN
    } else {
        psum(&t) / t.len() as f64
    }
}

/// a-perspective dominance of every rated bout, in bout order.
fn per_fight(snapshot: &Path, rated: &[Bout], names: &Names) -> Vec<f64> {
    let r = Frame::read(&snapshot.join("canonical_rounds.parquet"));
    let (url, fighter) = (r.str("fight_url"), r.str("fighter"));
    let stats: Vec<Vec<f64>> = ["sig_str_landed", "sub_att", "ctrl_seconds"]
        .iter()
        .map(|c| {
            r.f64(c)
                .into_iter()
                .map(|x| if x.is_nan() { 0.0 } else { x })
                .collect()
        })
        .collect();
    let mut bout: BTreeMap<(&str, &str), [f64; 3]> = BTreeMap::new();
    for i in 0..r.len() {
        let e = bout
            .entry((url[i].as_str(), fighter[i].as_str()))
            .or_default();
        for j in 0..3 {
            e[j] += stats[j][i];
        }
    }
    // NaN durations stay NaN (pandas `clip` keeps them), so such bouts drop out of the z-scores.
    let minutes = |b: &Bout| {
        let m = (if b.end_round.is_nan() {
            f64::NAN
        } else {
            (b.end_round - 1.0).max(0.0)
        } * 300.0
            + b.end_secs)
            / 60.0;
        if m.is_nan() {
            m
        } else {
            m.max(1.0)
        }
    };
    // Bouts with both sides' rounds, in fight_url order.
    let mut by_url: Vec<(&str, usize)> = rated
        .iter()
        .enumerate()
        .map(|(i, b)| (b.url.as_str(), i))
        .collect();
    by_url.sort();
    let both: Vec<(usize, [f64; 3])> = by_url
        .into_iter()
        .filter_map(|(u, i)| {
            let b = &rated[i];
            let (x, y) = (bout.get(&(u, b.a.as_str()))?, bout.get(&(u, b.b.as_str()))?);
            let m = minutes(b);
            Some((i, [0, 1, 2].map(|j| x[j] / m - y[j] / m)))
        })
        .collect();
    let zs: Vec<Vec<f64>> = (0..3)
        .map(|j| z(&both.iter().map(|p| p.1[j]).collect::<Vec<_>>()))
        .collect();
    let mut dom = vec![0.0; rated.len()];
    for (k, &(i, _)) in both.iter().enumerate() {
        let d = zs[0][k] + zs[1][k] + zs[2][k];
        dom[i] = if d.is_nan() { 0.0 } else { d };
    }
    // Judge margin, red minus blue, keyed by the unordered name pair and date; later cards win.
    let s = Frame::read(&snapshot.join("datalab_scorecards.parquet"));
    let (red, blue, day) = (
        s.str("red_fighter_name"),
        s.str("blue_fighter_name"),
        s.day("event_date"),
    );
    let (rp, bp) = (
        s.str("red_fighter_total_pts"),
        s.str("blue_fighter_total_pts"),
    );
    let mut cards: HashMap<(String, String, Day), (String, f64)> = HashMap::new();
    for i in 0..s.len() {
        let (r, b, m) = (
            names.key(&red[i], false),
            names.key(&blue[i], false),
            points(&rp[i]) - points(&bp[i]),
        );
        let Some(d) = day[i] else { continue };
        if m.is_nan() {
            continue;
        }
        let pair = if r <= b {
            (r.clone(), b)
        } else {
            (b, r.clone())
        };
        cards.insert((pair.0, pair.1, d), (r, m));
    }
    let gap: Vec<f64> = rated
        .iter()
        .map(|b| {
            let (a, o) = (names.key(&b.a, false), names.key(&b.b, false));
            let pair = if a <= o {
                (a.clone(), o)
            } else {
                (o, a.clone())
            };
            match cards.get(&(pair.0, pair.1, b.day)) {
                Some((r, m)) if b.method.starts_with("Decision") => {
                    if *r == a {
                        *m
                    } else {
                        -m
                    }
                }
                _ => f64::NAN,
            }
        })
        .collect();
    let scored: Vec<usize> = (0..rated.len()).filter(|&i| !gap[i].is_nan()).collect();
    for (k, zk) in z(&scored.iter().map(|&i| gap[i]).collect::<Vec<_>>())
        .into_iter()
        .enumerate()
    {
        dom[scored[k]] += zk;
    }
    for (i, b) in rated.iter().enumerate() {
        if b.method == "KO/TKO" || b.method == "Submission" {
            if b.winner == b.a {
                dom[i] = dom[i].max(FINISH_FLOOR_Z);
            } else if b.winner == b.b {
                dom[i] = dom[i].min(-FINISH_FLOOR_Z);
            }
        }
    }
    dom
}

/// fighter, wins, mean_dominance: winners only, rows in name order.
pub fn fighters(snapshot: &Path, rated: &[Bout], names: &Names) -> Table {
    let dom = per_fight(snapshot, rated, names);
    let mut wins: BTreeMap<&str, Vec<f64>> = BTreeMap::new();
    for (b, d) in rated.iter().zip(dom) {
        if !b.winner.is_empty() && (b.winner == b.a || b.winner == b.b) {
            wins.entry(&b.winner)
                .or_default()
                .push(if b.winner == b.a { d } else { -d });
        }
    }
    let f: Vec<&str> = wins.keys().copied().collect();
    Table::default()
        .str("fighter", &f)
        .i64(
            "wins",
            &wins.values().map(|v| v.len() as i64).collect::<Vec<_>>(),
        )
        .f64(
            "mean_dominance",
            &wins.values().map(|v| kahan_mean(v)).collect::<Vec<_>>(),
        )
}
