//! The WHR rating path of every fighter, one row per appearance.
//!
//! Rows are ordered `(fighter, day, event)` stably over the fit's appearance
//! order, as `ratings_history_whr.parquet` is written. `mu` is the fitted
//! rating (`mu_whr`), `era` the same rating read against its year's contender
//! line (`mu_era`, see `era`).

use std::collections::HashMap;
use std::ops::Range;
use std::path::Path;

use crate::frame::{Day, Frame};

#[derive(Clone, Debug)]
pub struct Row {
    pub fighter: String,
    pub day: Day,
    pub event: String,
    pub mu: f64,
    pub era: f64,
}

/// Indexed history exposes rows only as a shared slice.
///
/// ```compile_fail
/// use mma_rankings::history::History;
/// let mut h = History::new(vec![]);
/// h.rows.clear();
/// ```
pub struct History {
    rows: Vec<Row>,
    by: HashMap<String, Range<usize>>,
}

impl History {
    /// Sorts stably by `(fighter, day, event)` and indexes each fighter's block.
    pub fn new(mut rows: Vec<Row>) -> History {
        rows.sort_by(|x, y| (&x.fighter, x.day, &x.event).cmp(&(&y.fighter, y.day, &y.event)));
        let mut by = HashMap::new();
        let mut i = 0;
        while i < rows.len() {
            let j = i + rows[i..]
                .iter()
                .take_while(|r| r.fighter == rows[i].fighter)
                .count();
            by.insert(rows[i].fighter.clone(), i..j);
            i = j;
        }
        History { rows, by }
    }

    /// Rows in indexed path order; indexed keys cannot be mutated.
    pub fn rows(&self) -> &[Row] {
        &self.rows
    }

    /// Change only the era value, preserving row identity and the index.
    pub fn set_era<F: Fn(&Row) -> f64>(&mut self, value: F) {
        for row in &mut self.rows {
            row.era = value(row);
        }
    }

    pub fn read(snapshot: &Path) -> History {
        let f = Frame::read(&snapshot.join("ratings_history_whr.parquet"));
        let (fighter, event, day, mu, era) = (
            f.str("fighter"),
            f.str("event_name"),
            f.day("event_date"),
            f.f64("mu_whr"),
            f.f64("mu_era"),
        );
        History::new(
            (0..f.len())
                .map(|i| Row {
                    fighter: fighter[i].clone(),
                    day: day[i].unwrap(),
                    event: event[i].clone(),
                    mu: mu[i],
                    era: era[i],
                })
                .collect(),
        )
    }

    /// One fighter's rows in path order; empty when unrated.
    pub fn of(&self, fighter: &str) -> &[Row] {
        self.by.get(fighter).map_or(&[], |r| &self.rows[r.clone()])
    }

    /// `opponent_ratings`: the fighter's latest row strictly before `day`.
    ///
    /// pandas sorted by date alone with an unstable sort, so among same-date
    /// rows its choice was implementation-defined; this takes the last in path order.
    pub fn before(&self, fighter: &str, day: Day) -> Option<&Row> {
        let rows = self.of(fighter);
        rows[..rows.partition_point(|r| r.day < day)].last()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn era_updates_preserve_index_and_strictly_prior_lookup() {
        let row = |f: &str, day, mu| Row {
            fighter: f.into(),
            day,
            event: "card".into(),
            mu,
            era: f64::NAN,
        };
        let mut h = History::new(vec![
            row("Bob", 2, 1200.0),
            row("Alice", 3, 1600.0),
            row("Alice", 1, 1500.0),
        ]);
        h.set_era(|r| r.mu - 100.0);
        assert_eq!(h.rows().len(), 3);
        assert_eq!(h.of("Alice").len(), 2);
        assert_eq!(h.of("Bob")[0].fighter, "Bob");
        assert_eq!(h.before("Alice", 3).unwrap().era, 1400.0);
        assert_eq!(h.before("Alice", 4).unwrap().era, 1500.0);
        assert!(h.before("Alice", 1).is_none());
    }
}
