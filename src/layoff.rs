//! Price a win over an opponent returning from a long absence.
//!
//! The opponent's price drops 90 Elo per era-normal turnaround of absence
//! beyond the first, capped at four. The normal turnaround of year y is the
//! 75th percentile of the gaps between consecutive appearance dates that end
//! in y, or the corpus-wide value when y has fewer than 200 gaps. The rule
//! changes no rating; policy and evidence are in docs/DECISIONS.md.

use std::collections::{BTreeMap, HashMap};

use crate::era::year;
use crate::frame::Day;
use crate::history::History;
use crate::stats::quantile;

const Q: f64 = 0.75;
const MIN_SAMPLE: usize = 200;
const FALLBACK_DAYS: f64 = 270.0;
const MAX_EXCESS: f64 = 4.0;
/// `OPPONENT_LAYOFF_ELO_PER_TURNAROUND`, set by the owner on 2026-09-03.
pub const ELO_PER_TURNAROUND: f64 = -90.0;

/// Excess turnarounds of each (fighter, appearance date); a career's first date has none.
pub struct Layoff(HashMap<(String, Day), f64>);

impl Layoff {
    pub fn new(h: &History) -> Layoff {
        // Distinct dates per fighter, in date order (rows are already fighter-sorted).
        let mut dates: Vec<(&str, Day)> = h.rows.iter().map(|r| (r.fighter.as_str(), r.day)).collect();
        dates.dedup();
        let gaps: Vec<(&str, Day, f64)> = dates
            .windows(2)
            .filter(|w| w[0].0 == w[1].0)
            .map(|w| (w[1].0, w[1].1, (w[1].1 - w[0].1) as f64))
            .collect();
        let corpus = quantile(&gaps.iter().map(|g| g.2).collect::<Vec<_>>(), Q);
        let mut by_year: BTreeMap<i32, Vec<f64>> = BTreeMap::new();
        for g in &gaps {
            by_year.entry(year(g.1)).or_default().push(g.2);
        }
        let normal: HashMap<i32, f64> = by_year
            .into_iter()
            .map(|(y, v)| (y, if v.len() < MIN_SAMPLE { corpus } else { quantile(&v, Q) }.max(1.0)))
            .collect();
        Layoff(
            gaps.into_iter()
                .map(|(f, d, gap)| {
                    let reference = normal.get(&year(d)).copied().unwrap_or(FALLBACK_DAYS);
                    ((f.to_string(), d), (gap / reference - 1.0).clamp(0.0, MAX_EXCESS))
                })
                .collect(),
        )
    }

    pub fn excess(&self, fighter: &str, day: Day) -> f64 {
        self.0.get(&(fighter.to_string(), day)).copied().unwrap_or(0.0)
    }

    /// `discount_opponent_mu`: the opponent's rating on the night.
    pub fn price(&self, mu: f64, opponent: &str, day: Day) -> f64 {
        mu + ELO_PER_TURNAROUND * self.excess(opponent, day)
    }
}
