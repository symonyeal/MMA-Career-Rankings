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

/// Corpora of the published scope `majors,pre_unified` (UFC is always the base).
pub const SCOPE: [&str; 3] = ["ufc", "pre_unified", "majors"];

#[derive(Clone, Debug, Default)]
pub struct Bout {
    pub url: String,
    pub event: String,
    pub day: Day,
    pub a: String,
    pub b: String,
    /// Empty when the bout has no recorded winner.
    pub winner: String,
    pub loser: String,
    pub draw: bool,
    pub nc: bool,
    pub excluded: bool,
    pub weight_class: String,
    pub title: bool,
    pub method: String,
    /// Winner's score: the method price, else the staged value; NaN when neither exists.
    pub score: f64,
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

/// Every staged row, in file order, with the staged winner score.
pub fn staged(snapshot: &Path) -> Vec<Bout> {
    let f = Frame::read(&snapshot.join("combined_fights.parquet"));
    let s = |c: &str| f.str(c);
    let (url, event, a, b, winner, loser) = (s("fight_url"), s("event_name"), s("fighter_a"), s("fighter_b"), s("winner"), s("loser"));
    let (wc, method, details, source, org, corpus, corpora) = (
        s("weight_class"), s("method_class"), s("details_text"), s("source"), s("org"), s("source_corpus"),
        s("available_in_corpora"),
    );
    let day = f.day("event_date");
    let (draw, nc, excluded, title, model) = (f.bool("is_draw"), f.bool("is_nc"), f.bool("is_excluded"), f.bool("is_title_fight"), f.bool("is_model_bout"));
    let (score, end_round, end_secs) = (f.f64("method_score_winner"), f.f64("end_round"), f.f64("end_time_seconds"));
    (0..f.len())
        .map(|i| Bout {
            url: url[i].clone(),
            event: event[i].clone(),
            day: day[i].expect("bout without a date"),
            a: a[i].clone(),
            b: b[i].clone(),
            winner: winner[i].clone(),
            loser: loser[i].clone(),
            draw: draw[i],
            nc: nc[i],
            excluded: excluded[i],
            weight_class: wc[i].clone(),
            title: title[i],
            method: method[i].clone(),
            score: score[i],
            end_round: end_round[i],
            end_secs: end_secs[i],
            details: details[i].clone(),
            source: source[i].clone(),
            org: org[i].clone(),
            corpus: corpus[i].clone(),
            corpora: corpora[i].clone(),
            model: model[i],
            ..Bout::default()
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
            SCOPE.iter().any(|c| m.contains(&format!(",{c},")))
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
        let tokens: Vec<String> =
            token.find_iter(f).map(|m| m.as_str().to_lowercase()).filter(|t| t.chars().count() > 1).collect();
        let Some(last) = tokens.last() else { continue };
        let score = tokens.iter().filter(|t| lowered.contains(t.as_str())).count()
            + if lowered.contains(last.as_str()) { 2 } else { 0 };
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
        x.missed_weight =
            !x.winner.is_empty() && weight_re.is_match(&x.details) && winner_named(&x.winner, &x.details, names);
    }
    // Curated rows match on (date, event) and a named participant, and replace the text-derived citation.
    let path = root.join("data/external/integrity/ped_bouts.csv");
    let mut rd = csv::Reader::from_path(path).unwrap();
    let h = rd.headers().unwrap().clone();
    let col = |n: &str| h.iter().position(|x| x == n).unwrap();
    let (date, event, fighter, body, substance, finding, url) = (
        col("event_date"), col("event_name"), col("fighter"), col("sanctioning_body"), col("substance"),
        col("finding_type"), col("source_url"),
    );
    for r in rd.records().map(Result::unwrap) {
        let day = crate::frame::parse_day(&r[date]);
        for x in bouts.iter_mut().filter(|x| x.day == day && x.event == r[event] && (x.a == r[fighter] || x.b == r[fighter])) {
            x.ped = true;
            x.ped_fighter = r[fighter].to_string();
            x.ped_source = format!("curated:{}", &r[body]);
            x.ped_detail = format!("{}; {}; {}", &r[substance], &r[finding], &r[url]);
        }
    }
}
