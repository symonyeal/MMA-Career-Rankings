//! Policy values and predicates shared by more than one stage; each is defined here once.

use crate::bouts::Bout;

/// `CONTENDER_LINE_MU`: the rating that separates a contender from the field.
pub const CONTENDER: f64 = 1750.0;
/// `SUSTAINED_PEAK_MIN_FIGHTS`: the rating-period floor of every board.
pub const MIN_PERIODS: i64 = 13;
/// `DAYS_PER_MONTH`.
pub const DAYS_PER_MONTH: f64 = 365.25 / 12.0;
/// Win weight of a first-tier organisation; a win over an opponent priced at or above it is a top-tier win.
pub const TIER1: f64 = 0.82;

const UFC_ORGS: [&str; 3] = [
    "UFC",
    "UFC (pre-unified)",
    "Ultimate Fighting Championship (UFC)",
];

/// A bout in a UFC-family corpus.
pub fn ufc_corpus(b: &Bout) -> bool {
    b.corpus == "ufc" || b.corpus == "pre_unified"
}

/// `is_ufc_bout`: a UFC-family corpus row or a bout another source labels UFC.
pub fn is_ufc(b: &Bout) -> bool {
    ufc_corpus(b) || UFC_ORGS.contains(&b.org.as_str())
}
