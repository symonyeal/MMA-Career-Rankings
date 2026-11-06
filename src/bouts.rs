//! The bout table: `combined_fights.parquet` as staged, and the published
//! scope prepared for rating.
//!
//! Preparation keeps the corpora `ufc, pre_unified, majors`, prices each
//! winner by method, orders bouts by `(day, event)` stably, and recomputes
//! the integrity flags (PED, DQ, missed weight) from the bout text and the
//! curated PED table.

use std::path::Path;

use regex::Regex;

use crate::frame::{Day, Frame};
use crate::names::Names;

/// Published non-UFC scope, shared with Python staging. UFC is always the base.
pub const SCOPE: &str = include_str!("scope.txt");

/// A predictive history may use card-enumerated sources, never a roster selected
/// by a fighter's eventual career. Rankings deliberately retain the broader scope.
pub fn predictive(bout: &Bout) -> bool {
    const ORGS: [&str; 9] = [
        "UFC",
        "UFC (pre-unified)",
        "Ultimate Fighting Championship (UFC)",
        "PRIDE",
        "WEC",
        "Strikeforce",
        "Affliction",
        "Bellator",
        "RIZIN",
    ];
    bout.model && !bout.nc() && (bout.source == "ufc" || ORGS.contains(&bout.org.as_str()))
}

/// Participants and outcome are fixed by validated construction.
///
/// ```compile_fail
/// use mma_rankings::bouts::{Bout, Outcome};
/// let mut b = Bout::new("Alice".into(), "Bob".into(), 1, Outcome::Draw, f64::NAN).unwrap();
/// b.winner = "Carol".into();
/// ```
#[derive(Clone, Debug)]
pub struct Bout {
    pub url: String,
    pub event: String,
    pub day: Day,
    a: String,
    b: String,
    /// Empty when the bout has no recorded winner.
    winner: String,
    loser: String,
    outcome: Outcome,
    pub excluded: bool,
    pub weight_class: String,
    pub title: bool,
    pub method: String,
    /// Winner's score: the method price, else the staged value; NaN when neither exists.
    score: f64,
    pub end_round: f64,
    pub end_secs: f64,
    pub details: String,
    pub source: String,
    pub org: String,
    pub corpus: String,
    pub corpora: String,
    pub model: bool,
    pub ped: bool,
    pub ped_fighter: String,
    pub ped_source: String,
    pub ped_detail: String,
    pub dq: bool,
    pub missed_weight: bool,
}

/// The two named participants; outcome facts cannot name an unrelated fighter.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Corner {
    A,
    B,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Outcome {
    Win(Corner),
    Draw,
    NoContest,
}

impl Outcome {
    /// Decode a source record without repairing contradictory facts.
    pub fn from_record(
        a: &str,
        b: &str,
        winner: &str,
        loser: &str,
        draw: bool,
        nc: bool,
    ) -> Result<Self, &'static str> {
        if draw || nc {
            if draw && nc || !winner.is_empty() || !loser.is_empty() {
                return Err("draw/no-contest contradicts winner or loser");
            }
            return Ok(if draw { Self::Draw } else { Self::NoContest });
        }
        match (winner, loser) {
            (w, l) if w == a && l == b => Ok(Self::Win(Corner::A)),
            (w, l) if w == b && l == a => Ok(Self::Win(Corner::B)),
            _ => Err("winner and loser must be the two participants"),
        }
    }
}

impl Bout {
    /// Construct one valid bout; NaN means an unavailable method score.
    pub fn new(
        a: String,
        b: String,
        day: Day,
        outcome: Outcome,
        score: f64,
    ) -> Result<Self, &'static str> {
        if a.trim().is_empty() || b.trim().is_empty() || a == b {
            return Err("bout needs two distinct named participants");
        }
        if !score.is_nan() && !(0.0..=1.0).contains(&score) {
            return Err("method score must be missing or between zero and one");
        }
        let (winner, loser) = match outcome {
            Outcome::Win(Corner::A) => (a.clone(), b.clone()),
            Outcome::Win(Corner::B) => (b.clone(), a.clone()),
            Outcome::Draw | Outcome::NoContest => (String::new(), String::new()),
        };
        Ok(Self {
            a,
            b,
            day,
            outcome,
            winner,
            loser,
            score,
            url: String::new(),
            event: String::new(),
            excluded: false,
            weight_class: String::new(),
            title: false,
            method: String::new(),
            end_round: f64::NAN,
            end_secs: f64::NAN,
            details: String::new(),
            source: String::new(),
            org: String::new(),
            corpus: String::new(),
            corpora: String::new(),
            model: false,
            ped: false,
            ped_fighter: String::new(),
            ped_source: String::new(),
            ped_detail: String::new(),
            dq: false,
            missed_weight: false,
        })
    }

    pub fn a(&self) -> &String {
        &self.a
    }
    pub fn b(&self) -> &String {
        &self.b
    }
    /// Empty when the outcome is a draw or no-contest.
    pub fn winner(&self) -> &String {
        &self.winner
    }
    pub fn loser(&self) -> &String {
        &self.loser
    }
    pub fn outcome(&self) -> Outcome {
        self.outcome
    }
    pub fn draw(&self) -> bool {
        self.outcome == Outcome::Draw
    }
    pub fn nc(&self) -> bool {
        self.outcome == Outcome::NoContest
    }
    pub fn score(&self) -> f64 {
        self.score
    }
}
/// Every staged row, in file order, with the staged winner score.
pub fn staged(snapshot: &Path) -> Vec<Bout> {
    let f = Frame::read(&snapshot.join("combined_fights.parquet"));
    let s = |c: &str| f.str(c);
    let (url, event, a, b, winner, loser) = (
        s("fight_url"),
        s("event_name"),
        s("fighter_a"),
        s("fighter_b"),
        s("winner"),
        s("loser"),
    );
    let (wc, method, details, source, org, corpus, corpora) = (
        s("weight_class"),
        s("method_class"),
        s("details_text"),
        s("source"),
        s("org"),
        s("source_corpus"),
        s("available_in_corpora"),
    );
    let day = f.day("event_date");
    let (draw, nc, excluded, title, model) = (
        f.bool("is_draw"),
        f.bool("is_nc"),
        f.bool("is_excluded"),
        f.bool("is_title_fight"),
        f.bool("is_model_bout"),
    );
    let (score, end_round, end_secs) = (
        f.f64("method_score_winner"),
        f.f64("end_round"),
        f.f64("end_time_seconds"),
    );
    (0..f.len())
        .map(|i| {
            let outcome = Outcome::from_record(&a[i], &b[i], &winner[i], &loser[i], draw[i], nc[i])
                .unwrap_or_else(|e| panic!("combined_fights row {i}: {e}"));
            let mut bout = Bout::new(
                a[i].clone(),
                b[i].clone(),
                day[i].expect("bout without a date"),
                outcome,
                score[i],
            )
            .unwrap_or_else(|e| panic!("combined_fights row {i}: {e}"));
            bout.url = url[i].clone();
            bout.event = event[i].clone();
            bout.excluded = excluded[i];
            bout.weight_class = wc[i].clone();
            bout.title = title[i];
            bout.method = method[i].clone();
            bout.end_round = end_round[i];
            bout.end_secs = end_secs[i];
            bout.details = details[i].clone();
            bout.source = source[i].clone();
            bout.org = org[i].clone();
            bout.corpus = corpus[i].clone();
            bout.corpora = corpora[i].clone();
            bout.model = model[i];
            bout
        })
        .collect()
}

/// `METHOD_SCORES`: finishes 1.00, unanimous 0.95, majority or split 0.90, DQ 0.85.
fn method_score(method: &str) -> Option<f64> {
    match method {
        "KO/TKO" | "Submission" => Some(1.00),
        "Decision - Unanimous" => Some(0.95),
        "Decision - Majority" | "Decision - Split" => Some(0.90),
        "DQ" => Some(0.85),
        _ => None,
    }
}

/// The published scope, priced, ordered and integrity-flagged; excluded bouts included.
pub fn prepared(snapshot: &Path, root: &Path, names: &Names) -> Vec<Bout> {
    let mut out: Vec<Bout> = staged(snapshot)
        .into_iter()
        .filter(|x| {
            let m = format!(",{},", x.corpora);
            std::iter::once("ufc")
                .chain(SCOPE.trim().split(','))
                .any(|c| m.contains(&format!(",{c},")))
        })
        .collect();
    for x in &mut out {
        if let Some(s) = method_score(&x.method) {
            x.score = s;
        }
    }
    out.sort_by(|x, y| (x.day, &x.event).cmp(&(y.day, &y.event)));
    flag_integrity(&mut out, root, names);
    out
}

/// Bouts that enter the rating: prepared and not excluded.
pub fn rated(prepared: &[Bout]) -> Vec<Bout> {
    prepared.iter().filter(|x| !x.excluded).cloned().collect()
}

fn ped_fighter(x: &Bout) -> String {
    let token = Regex::new(r"[A-Za-z']+").unwrap();
    let lowered = x.details.to_lowercase();
    let mut scored: Vec<(usize, &str)> = Vec::new();
    for f in [&x.a, &x.b] {
        let tokens: Vec<String> = token
            .find_iter(f)
            .map(|m| m.as_str().to_lowercase())
            .filter(|t| t.chars().count() > 1)
            .collect();
        let Some(last) = tokens.last() else { continue };
        let score = tokens
            .iter()
            .filter(|t| lowered.contains(t.as_str()))
            .count()
            + if lowered.contains(last.as_str()) {
                2
            } else {
                0
            };
        if score > 0 {
            scored.push((score, f));
        }
    }
    scored.sort_by(|p, q| q.cmp(p));
    match scored.as_slice() {
        [] => String::new(),
        [(s0, _), (s1, _), ..] if s0 == s1 => String::new(),
        [(_, f), ..] => f.to_string(),
    }
}

fn winner_named(winner: &str, text: &str, names: &Names) -> bool {
    let text_key = names.key(text, true);
    names
        .key(winner, false)
        .split_whitespace()
        .filter(|p| p.chars().count() >= 3)
        .any(|p| text_key.contains(&names.key(p, true)))
}

fn flag_integrity(bouts: &mut [Bout], root: &Path, names: &Names) {
    let ped_re = Regex::new(r"(?i)(?:failed\s+drug\s+test|illegal\s+inhaler\s+use)").unwrap();
    let weight_re = Regex::new(r"(?i)missed?\s+weight").unwrap();
    for x in bouts.iter_mut() {
        x.ped = ped_re.is_match(&x.details);
        if x.ped {
            x.ped_fighter = ped_fighter(x);
            x.ped_source = "Greco details_text".into();
            x.ped_detail = x.details.clone();
        }
        x.dq = x.method == "DQ";
        x.missed_weight = !x.winner.is_empty()
            && weight_re.is_match(&x.details)
            && winner_named(&x.winner, &x.details, names);
    }
    // Curated rows match on (date, event) and a named participant, and replace the text-derived citation.
    let path = root.join("data/external/integrity/ped_bouts.csv");
    let mut rd = csv::Reader::from_path(path).unwrap();
    let h = rd.headers().unwrap().clone();
    let col = |n: &str| h.iter().position(|x| x == n).unwrap();
    let (date, event, fighter, body, substance, finding, url) = (
        col("event_date"),
        col("event_name"),
        col("fighter"),
        col("sanctioning_body"),
        col("substance"),
        col("finding_type"),
        col("source_url"),
    );
    for r in rd.records().map(Result::unwrap) {
        let day = crate::frame::parse_day(&r[date]);
        for x in bouts.iter_mut().filter(|x| {
            x.day == day && x.event == r[event] && (x.a == r[fighter] || x.b == r[fighter])
        }) {
            x.ped = true;
            x.ped_fighter = r[fighter].to_string();
            x.ped_source = format!("curated:{}", &r[body]);
            x.ped_detail = format!("{}; {}; {}", &r[substance], &r[finding], &r[url]);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rejects_contradictory_source_outcomes() {
        for (winner, loser, draw, nc) in [
            ("Carol", "Bob", false, false),
            ("Alice", "Alice", false, false),
            ("Alice", "Bob", true, false),
            ("Alice", "Bob", false, true),
            ("", "", true, true),
            ("", "", false, false),
        ] {
            assert!(Outcome::from_record("Alice", "Bob", winner, loser, draw, nc).is_err());
        }
        assert_eq!(
            Outcome::from_record("Alice", "Bob", "Alice", "Bob", false, false),
            Ok(Outcome::Win(Corner::A))
        );
        assert_eq!(
            Outcome::from_record("Alice", "Bob", "Bob", "Alice", false, false),
            Ok(Outcome::Win(Corner::B))
        );
        assert_eq!(
            Outcome::from_record("Alice", "Bob", "", "", true, false),
            Ok(Outcome::Draw)
        );
        assert_eq!(
            Outcome::from_record("Alice", "Bob", "", "", false, true),
            Ok(Outcome::NoContest)
        );
    }

    #[test]
    fn construction_preserves_participants_and_score_domain() {
        for (a, b) in [("", "Bob"), ("Alice", " "), ("Alice", "Alice")] {
            assert!(Bout::new(a.into(), b.into(), 1, Outcome::Draw, 0.5).is_err());
        }
        for score in [-0.01, 1.01, f64::INFINITY] {
            assert!(Bout::new(
                "Alice".into(),
                "Bob".into(),
                1,
                Outcome::Win(Corner::A),
                score
            )
            .is_err());
        }
        for (outcome, winner, loser) in [
            (Outcome::Win(Corner::A), "Alice", "Bob"),
            (Outcome::Win(Corner::B), "Bob", "Alice"),
            (Outcome::Draw, "", ""),
            (Outcome::NoContest, "", ""),
        ] {
            let b = Bout::new("Alice".into(), "Bob".into(), 1, outcome, f64::NAN).unwrap();
            assert_eq!(b.winner(), winner);
            assert_eq!(b.loser(), loser);
            assert_eq!(b.outcome(), outcome);
        }
    }

    #[test]
    fn predictive_history_uses_enumerated_cards_not_eventual_career_selection() {
        let mut b = Bout::new(
            "Alice".into(),
            "Bob".into(),
            1,
            Outcome::Win(Corner::A),
            1.0,
        )
        .unwrap();
        b.model = true;
        b.source = "sherdog_careers".into();
        b.org = "Regional promotion".into();
        assert!(!predictive(&b));
        b.org = "PRIDE".into();
        assert!(predictive(&b));
        b.org = "Regional promotion".into();
        b.source = "ufc".into();
        assert!(predictive(&b));
        b.model = false;
        assert!(!predictive(&b));
    }
}
