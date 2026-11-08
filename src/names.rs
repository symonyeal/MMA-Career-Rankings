//! Fighter name keys for joins across sources.
//!
//! A key is the name with any `(sherdog:N)` suffix removed, NFKD-folded,
//! marks of nonzero combining class dropped (Python `unicodedata.combining`), trimmed and lowercased; aliases then map a
//! spelling to its canonical key; `compact` keeps alphanumerics only.

use std::collections::HashMap;
use std::path::Path;
use std::sync::OnceLock;

use regex::Regex;
use unicode_normalization::char::{canonical_combining_class, is_combining_mark};
use unicode_normalization::UnicodeNormalization;

use crate::error::Error;
use crate::frame::csv_rows;

fn basic(name: &str) -> String {
    static SID: OnceLock<Regex> = OnceLock::new();
    let sid = SID.get_or_init(|| Regex::new(r"(?i)\s*\(sherdog:\d+\)\s*$").unwrap());
    let folded: String = sid
        .replace(name, "")
        .nfkd()
        .filter(|c| canonical_combining_class(*c) == 0)
        .collect();
    folded.trim().to_lowercase()
}

fn compacted(key: &str) -> String {
    key.chars()
        .filter(|c| c.is_alphanumeric() && !is_combining_mark(*c))
        .collect()
}

/// Alias keys: `fighter_aliases.csv` rows, then id-free rows of the
/// cross-source overrides, each `alias key -> canonical key`.
pub struct Names {
    alias: HashMap<String, String>,
}

impl Names {
    /// The file, and for a row its number, are named in every error.
    pub fn load(root: &Path) -> Result<Names, Error> {
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
        for r in csv_rows(
            &overrides,
            &["sherdog_id", "sherdog_name", "canonical_name"],
        )? {
            if r[0].trim().is_empty() {
                add(&r[2], &r[1]);
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

/// The cross-language rule cases, `tests/fixtures/rule_parity.json`.
#[cfg(test)]
pub fn parity_cases() -> serde_json::Value {
    let path = Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/rule_parity.json");
    serde_json::from_str(&std::fs::read_to_string(path).unwrap()).unwrap()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn name_keys_match_the_python_staging() {
        let names = Names {
            alias: HashMap::new(),
        };
        for c in parity_cases()["name_keys"].as_array().unwrap() {
            let name = c[0].as_str().unwrap();
            assert_eq!(names.key(name, false), c[1].as_str().unwrap(), "{c}");
            assert_eq!(names.key(name, true), c[2].as_str().unwrap(), "{c}");
        }
    }

    #[test]
    fn a_missing_alias_file_is_named() {
        let e = Names::load(Path::new("no/such/root")).err().unwrap();
        assert!(e.0.contains("fighter_aliases.csv"), "{e}");
    }
}
