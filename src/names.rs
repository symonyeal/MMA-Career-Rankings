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

use crate::error::Error;

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
        Names::try_load(root).unwrap_or_else(|e| panic!("{e}"))
    }

    /// `load`, with the file, and for a row its number, named in every error.
    pub fn try_load(root: &Path) -> Result<Names, Error> {
        let mut alias = HashMap::new();
        let mut add = |canonical: &str, other: &str| {
            let (c, a) = (basic(canonical), basic(other));
            if !c.is_empty() && !a.is_empty() && c != a {
                alias.insert(a, c);
            }
        };
        let aliases = root.join("data/external/aliases/fighter_aliases.csv");
        let at = |p: &Path, e: &dyn std::fmt::Display| Error::at(p.display(), e);
        let mut rd = csv::Reader::from_path(&aliases).map_err(|e| at(&aliases, &e))?;
        for (i, r) in rd.records().enumerate() {
            let r = r.map_err(|e| at(&aliases, &e))?;
            if r.len() < 2 {
                return Err(at(&aliases, &format!("row {}: expected 2 columns", i + 2)));
            }
            add(&r[0], &r[1]);
        }
        let overrides = root.join("data/external/crossorg/identity_overrides.csv");
        let mut rd = csv::Reader::from_path(&overrides).map_err(|e| at(&overrides, &e))?;
        let h = rd.headers().map_err(|e| at(&overrides, &e))?.clone();
        let col = |n: &str| {
            h.iter()
                .position(|x| x == n)
                .ok_or_else(|| at(&overrides, &format!("missing column {n}")))
        };
        let (sid, name, canonical) = (
            col("sherdog_id")?,
            col("sherdog_name")?,
            col("canonical_name")?,
        );
        for r in rd.records() {
            let r = r.map_err(|e| at(&overrides, &e))?;
            if r[sid].trim().is_empty() {
                add(&r[canonical], &r[name]);
            }
        }
        Ok(Names { alias })
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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_missing_alias_file_is_named() {
        let e = Names::try_load(Path::new("no/such/root")).err().unwrap();
        assert!(e.0.contains("fighter_aliases.csv"), "{e}");
    }
}
