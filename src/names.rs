//! Fighter name keys for joins across sources.
//!
//! A key is the name with any `(sherdog:N)` suffix removed, NFKD-folded,
//! combining marks dropped, trimmed and lowercased; aliases then map a
//! spelling to its canonical key; `compact` keeps alphanumerics only.

use std::collections::HashMap;
use std::path::Path;
use std::sync::OnceLock;

use regex::Regex;
use unicode_normalization::char::is_combining_mark;
use unicode_normalization::UnicodeNormalization;

fn basic(name: &str) -> String {
    static SID: OnceLock<Regex> = OnceLock::new();
    let sid = SID.get_or_init(|| Regex::new(r"(?i)\s*\(sherdog:\d+\)\s*$").unwrap());
    let folded: String = sid
        .replace(name, "")
        .nfkd()
        .filter(|c| !is_combining_mark(*c))
        .collect();
    folded.trim().to_lowercase()
}

fn compacted(key: &str) -> String {
    key.chars().filter(|c| c.is_alphanumeric()).collect()
}

/// Alias keys: `fighter_aliases.csv` rows, then id-free rows of the
/// cross-source overrides, each `alias key -> canonical key`.
pub struct Names {
    alias: HashMap<String, String>,
}

impl Names {
    pub fn load(root: &Path) -> Names {
        let mut alias = HashMap::new();
        let mut add = |canonical: &str, other: &str| {
            let (c, a) = (basic(canonical), basic(other));
            if !c.is_empty() && !a.is_empty() && c != a {
                alias.insert(a, c);
            }
        };
        let aliases = root.join("data/external/aliases/fighter_aliases.csv");
        for r in csv::Reader::from_path(aliases)
            .unwrap()
            .records()
            .map(Result::unwrap)
        {
            add(&r[0], &r[1]);
        }
        let overrides = root.join("data/external/crossorg/identity_overrides.csv");
        let mut rd = csv::Reader::from_path(overrides).unwrap();
        let h = rd.headers().unwrap().clone();
        let col = |n: &str| h.iter().position(|x| x == n).unwrap();
        let (sid, name, canonical) = (
            col("sherdog_id"),
            col("sherdog_name"),
            col("canonical_name"),
        );
        for r in rd.records().map(Result::unwrap) {
            if r[sid].trim().is_empty() {
                add(&r[canonical], &r[name]);
            }
        }
        Names { alias }
    }

    pub fn key(&self, name: &str, compact: bool) -> String {
        let k = basic(name);
        let k = self.alias.get(&k).cloned().unwrap_or(k);
        if compact {
            compacted(&k)
        } else {
            k
        }
    }
}

/// The key without aliases, as `normalize_name_key(apply_aliases=False)`.
pub fn plain_key(name: &str, compact: bool) -> String {
    let k = basic(name);
    if compact {
        compacted(&k)
    } else {
        k
    }
}
