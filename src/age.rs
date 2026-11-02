//! Birth dates for the age-dependent WHR prior and the age tables.

use std::collections::HashMap;
use std::path::Path;

use crate::frame::{Day, Frame};

/// `load_birth_dates`: one date per fighter, UFCStats first, then Sherdog, then Fight Matrix.
pub fn births(snapshot: &Path) -> HashMap<String, Day> {
    let mut out = HashMap::new();
    for (file, col) in [
        ("canonical_fighters", "dob"),
        ("sherdog_birth_dates", "dob"),
        ("fightmatrix_profiles", "birth_date"),
    ] {
        let p = snapshot.join(format!("{file}.parquet"));
        if !p.exists() {
            continue;
        }
        let f = Frame::read(&p);
        if !f.has("fighter") || !f.has(col) {
            continue;
        }
        let mut rows: Vec<(String, Day)> = f
            .str("fighter")
            .into_iter()
            .zip(f.day(col))
            .filter_map(|(n, d)| Some((n, d?)))
            .filter(|p| !p.0.is_empty())
            .collect();
        // Within one source the first row per fighter in name order wins (stable sort, keep first).
        rows.sort_by(|a, b| a.0.cmp(&b.0));
        for (n, d) in rows {
            out.entry(n).or_insert(d);
        }
    }
    out
}
