//! Which promotion staged a bout, and how much a career proven there counts.
//!
//! Labels are matched against the versioned rules in
//! data/external/fightmatrix/organization_normalization.csv (first matching
//! pattern, case-insensitive; else an exact canonical name). A rule's tier
//! holds only inside its active and tier windows, else tier 3. The factor of
//! a bout is fixed per canonical promotion, else per tier
//! (1: 0.82, 2: 0.60, 3: 0.42, 4: 0.20).

use std::collections::HashMap;
use std::path::Path;

use regex::Regex;

use crate::bouts::Bout;
use crate::era::year;
use crate::frame::parse_day;
use crate::policy::TIER1;

struct Rule {
    pattern: Regex,
    canonical: String,
    tier: i64,
    active: (Option<f64>, Option<f64>),
    tiered: (Option<f64>, Option<f64>),
}

pub struct Rules(Vec<Rule>);

/// A promotion as resolved for one bout.
#[derive(Clone, Debug)]
pub struct Org {
    pub canonical: String,
    /// `promotion_identity`: the lineage a title belongs to.
    pub identity: String,
    pub tier: i64,
    pub factor: f64,
}

const BY_CANONICAL: [(&str, f64); 10] = [
    ("UFC", 1.0),
    ("PRIDE", 0.95),
    ("Affliction", 0.90),
    ("Strikeforce", 0.88),
    ("WEC", 0.88),
    ("Bellator", 0.65),
    ("PFL", 0.60),
    ("RIZIN", 0.60),
    ("ONE", 0.60),
    ("DREAM", 0.60),
];
pub const TIER4: f64 = 0.20;

fn tier_factor(tier: i64) -> f64 {
    match tier {
        1 => TIER1,
        2 => 0.60,
        3 => 0.42,
        _ => TIER4,
    }
}

fn factor(canonical: &str, tier: i64) -> f64 {
    BY_CANONICAL
        .iter()
        .find(|p| p.0 == canonical)
        .map_or_else(|| tier_factor(tier), |p| p.1)
}

fn within(when: Option<f64>, (start, end): (Option<f64>, Option<f64>)) -> bool {
    match when {
        None => true,
        Some(t) => !start.is_some_and(|s| t < s) && !end.is_some_and(|e| t > e),
    }
}

impl Rules {
    pub fn load(root: &Path) -> Rules {
        let path = root.join("data/external/fightmatrix/organization_normalization.csv");
        let mut rd = csv::Reader::from_path(path).unwrap();
        let h = rd.headers().unwrap().clone();
        let col = |n: &str| h.iter().position(|x| x == n).unwrap();
        let (p, c, t, af, at, tf, tt) = (
            col("pattern"),
            col("canonical_organization"),
            col("tier"),
            col("active_from"),
            col("active_to"),
            col("tier_from"),
            col("tier_to"),
        );
        let day = |s: &str| (!s.is_empty()).then(|| parse_day(s) as f64);
        Rules(
            rd.records()
                .map(Result::unwrap)
                .map(|r| Rule {
                    pattern: Regex::new(&format!("(?i){}", &r[p])).unwrap(),
                    canonical: r[c].to_string(),
                    tier: r[t].parse().unwrap(),
                    active: (day(&r[af]), day(&r[at])),
                    tiered: (day(&r[tf]), day(&r[tt])),
                })
                .collect(),
        )
    }

    /// `normalize_organization`: (canonical, tier) of a label on a day (fractional days allowed).
    pub fn normalize(&self, label: &str, when: Option<f64>, verified: bool) -> (String, i64) {
        let raw = label.split_whitespace().collect::<Vec<_>>().join(" ");
        let folded = raw.to_lowercase();
        let rule = self
            .0
            .iter()
            .find(|r| r.pattern.is_match(&raw))
            .or_else(|| self.0.iter().find(|r| r.canonical.to_lowercase() == folded));
        match rule {
            Some(r) => (
                r.canonical.clone(),
                if within(when, r.active) && within(when, r.tiered) {
                    r.tier
                } else {
                    3
                },
            ),
            None if verified && !raw.is_empty() && folded != "unknown" => (raw, 4),
            None => ("Unknown".into(), 4),
        }
    }

    /// `_organization_context`: the promotion of every bout, keyed by fight URL.
    ///
    /// Bouts are grouped by (org label, event, year) and each group resolved at its median date.
    /// An unlabelled UFCStats bout is a UFC bout; an unresolved label falls back to the event name.
    pub fn context(&self, bouts: &[Bout]) -> HashMap<String, Org> {
        let label = |b: &Bout| {
            if b.org.is_empty() {
                if b.source == "ufc" {
                    "UFC".to_string()
                } else {
                    "Unknown".to_string()
                }
            } else {
                b.org.clone()
            }
        };
        let mut groups: HashMap<(String, &str, i32), Vec<f64>> = HashMap::new();
        for b in bouts {
            groups
                .entry((label(b), b.event.as_str(), year(b.day)))
                .or_default()
                .push(b.day as f64);
        }
        let weak = |c: &str| c == "Unknown" || c == "Major Regional";
        let resolved: HashMap<(String, &str, i32), Org> = groups
            .into_iter()
            .map(|(k, mut d)| {
                d.sort_by(f64::total_cmp);
                let n = d.len();
                let when = Some(if n % 2 == 1 {
                    d[n / 2]
                } else {
                    (d[n / 2 - 1] + d[n / 2]) / 2.0
                });
                let (mut canonical, mut tier) = self.normalize(&k.0, when, true);
                let mut identity = canonical.clone();
                if weak(&canonical) {
                    let (ec, et) = self.normalize(k.1, when, false);
                    if !weak(&ec) {
                        (canonical, tier, identity) = (ec.clone(), et, ec);
                    } else if !(k.0.is_empty() || weak(&k.0)) {
                        identity = k.0.clone();
                    } else {
                        identity = format!("Unresolved::{}", k.1);
                    }
                }
                let factor = factor(&canonical, tier);
                (
                    k,
                    Org {
                        canonical,
                        identity,
                        tier,
                        factor,
                    },
                )
            })
            .collect();
        let mut out = HashMap::new();
        for b in bouts {
            out.entry(b.url.clone())
                .or_insert_with(|| resolved[&(label(b), b.event.as_str(), year(b.day))].clone());
        }
        out
    }
}
