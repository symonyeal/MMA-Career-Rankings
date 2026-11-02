//! Every number the README's narrative paragraphs quote.
//!
//! The two careers compared are Jon Jones (a) and Georges St-Pierre (b): their All-time points
//! by part, the résumé's two largest wins for a and largest for b (Elo above the 1,750 line),
//! their Prime elite levels and the win chance their gap implies, and the men's contender line
//! (`contender_bar` with 60 over fighter-year means of the unadjusted rating) in 2007 and 2023.

use std::collections::HashMap;

use crate::bouts::Bout;
use crate::era::{contender_bar, CAREER_N};
use crate::frame::Frame;
use crate::history::{History, Row};
use crate::legacy::{points, resume_rows, Pricing, CONTENDER};
use crate::skill::annual;
use crate::stats::{fmt0, py_round};

pub const PAIR: [&str; 2] = ["Jon Jones", "Georges St-Pierre"];
const ERA_YEARS: [i32; 2] = [2007, 2023];

#[derive(Clone, Debug, PartialEq)]
pub enum Figure {
    Num(f64),
    Name(String),
}

impl Figure {
    pub fn num(&self) -> f64 {
        match self {
            Figure::Num(x) => *x,
            Figure::Name(_) => f64::NAN,
        }
    }

    pub fn name(&self) -> &str {
        match self {
            Figure::Name(s) => s,
            Figure::Num(_) => "",
        }
    }
}

/// The 22 figures in print order. `cur` holds every fighter (`fighter, gender, public_legacy_*`),
/// `p` is the era pricing, `h` the history (its raw `mu` gives the era line) and `elite` maps
/// fighter → `prime_elite_board.elite_level`.
pub fn values(
    cur: &Frame,
    rated: &[Bout],
    p: &Pricing,
    h: &History,
    elite: &HashMap<String, f64>,
) -> Vec<(&'static str, Figure)> {
    use Figure::{Name, Num};
    let f = cur.str("fighter");
    let n0 = |c: &str| {
        cur.f64(c)
            .into_iter()
            .map(|x| if x.is_nan() { 0.0 } else { x })
            .collect::<Vec<_>>()
    };
    let [t, k, q] = points(
        &n0("public_legacy_title_score"),
        &n0("public_legacy_skill_score"),
        &n0("public_legacy_resume_score"),
    );
    let score = cur.f64("public_legacy_score");
    let at = |name: &str| f.iter().position(|x| x == name).unwrap();
    let (a, b) = (at(PAIR[0]), at(PAIR[1]));
    let mut r = resume_rows(rated, p, None);
    r.sort_by(|x, y| y.mu.total_cmp(&x.mu));
    let best = |name: &str| r.iter().filter(|w| w.fighter == name).collect::<Vec<_>>();
    let (ra, rb) = (best(PAIR[0]), best(PAIR[1]));
    let (ea, eb) = (elite[PAIR[0]], elite[PAIR[1]]);
    let d = ea - eb;
    let gender: HashMap<String, String> = f.iter().cloned().zip(cur.str("gender")).collect();
    let men: Vec<Row> = h
        .rows
        .iter()
        .filter(|r| gender.get(&r.fighter).map(String::as_str) != Some("F"))
        .cloned()
        .collect();
    let men = History::new(men);
    let line = |y: i32| {
        let v: Vec<f64> = annual(&men, |r| r.mu)
            .into_iter()
            .filter(|x| x.1 == y)
            .map(|x| x.2)
            .collect();
        contender_bar(&v, CAREER_N)
    };
    let (lo, hi) = (line(ERA_YEARS[0]), line(ERA_YEARS[1]));
    vec![
        ("score_a", Num(score[a])),
        ("score_b", Num(score[b])),
        ("ratio", Num(score[a] / score[b] - 1.0)),
        ("title_a", Num(t[a])),
        ("title_b", Num(t[b])),
        ("resume_a", Num(q[a])),
        ("resume_b", Num(q[b])),
        ("skill_a", Num(k[a])),
        ("skill_b", Num(k[b])),
        ("elite_1_name", Name(ra[0].opponent.clone())),
        ("elite_1_above", Num(ra[0].mu - CONTENDER)),
        ("elite_2_name", Name(ra[1].opponent.clone())),
        ("elite_2_above", Num(ra[1].mu - CONTENDER)),
        ("best_b_name", Name(rb[0].opponent.clone())),
        ("best_b_above", Num(rb[0].mu - CONTENDER)),
        ("prime_a", Num(ea)),
        ("prime_b", Num(eb)),
        ("prime_edge", Num(d)),
        ("prime_win", Num(1.0 / (1.0 + 10f64.powf(-d / 400.0)))),
        ("era_lo", Num(lo)),
        ("era_hi", Num(hi)),
        ("era_gap", Num(hi - lo)),
    ]
}

/// Python `f"{round(x):,}"`.
fn n(x: f64) -> String {
    let s = format!("{}", py_round(x, 0).abs() as i64);
    let mut out = String::new();
    for (i, c) in s.chars().enumerate() {
        if i > 0 && (s.len() - i) % 3 == 0 {
            out.push(',');
        }
        out.push(c);
    }
    if py_round(x, 0) < 0.0 {
        format!("-{out}")
    } else {
        out
    }
}

/// Python `f"{x:.0%}"`.
fn pct(x: f64) -> String {
    format!("{}%", fmt0(x * 100.0))
}

/// The two narrative paragraphs (`write_readme`), unwrapped: `(opening words, text)`.
pub fn paragraphs(v: &[(&'static str, Figure)]) -> [(&'static str, String); 2] {
    let g = |k: &str| v.iter().find(|p| p.0 == k).map(|p| p.1.clone()).unwrap();
    let x = |k: &str| n(g(k).num());
    let era = format!(
        "All-time and Prime read every rating against its own year's contender line. The \
         model's scale drifts upward over time: on this fit the 60th-best man stood at {} \
         in 2007 and {} in 2023, so without this era adjustment a 2023 win would \
         be priced on a scale about {} points higher than a 2007 win. \
         Current, whose fighters are all contemporaries, reads the unadjusted ratings.",
        x("era_lo"),
        x("era_hi"),
        5.0 * py_round(g("era_gap").num() / 5.0, 0)
    );
    let points = format!(
        "**The score is a points total, not a ratio.** \
         Jon Jones's {} against Georges St-Pierre's {} does not mean Jones was \
         {} better. It means his three parts add up to more points: title {} \
         against {}, résumé {} against {}, skill \
         {} against {}. Most of the résumé gap is two elite wins: \
         {} at {} points above the line and {} at \
         {}, where St-Pierre's best was {} at {}. \
         For who was better at their best, read Prime: {} against {}, an \
         {}-point edge, which the rating turns into about a {} chance of winning.",
        x("score_a"),
        x("score_b"),
        pct(g("ratio").num()),
        x("title_a"),
        x("title_b"),
        x("resume_a"),
        x("resume_b"),
        x("skill_a"),
        x("skill_b"),
        g("elite_1_name").name(),
        x("elite_1_above"),
        g("elite_2_name").name(),
        x("elite_2_above"),
        g("best_b_name").name(),
        x("best_b_above"),
        x("prime_a"),
        x("prime_b"),
        x("prime_edge"),
        pct(g("prime_win").num())
    );
    [
        ("All-time and Prime read every rating", era),
        ("**The score is a points total, not a ratio.**", points),
    ]
}
