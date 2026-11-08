//! Every number the README's narrative paragraphs quote.
//!
//! The two careers compared are Jon Jones (a) and Georges St-Pierre (b): their All-time points
//! by part, the résumé's two largest wins for a and largest for b (Elo above the 1,750 line),
//! their Prime elite levels and the win chance their gap implies, and the men's contender line
//! (`contender_bar` with 60 over fighter-year means of the unadjusted rating) in 2007 and 2023.

use std::collections::HashMap;

use crate::bouts::Bout;
use crate::era::{contender_bar, CAREER_N};
use crate::error::Error;
use crate::fm;
use crate::frame::Frame;
use crate::history::{History, Row};
use crate::legacy::{points, resume_rows, Pricing};
use crate::policy::CONTENDER;
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
/// fighter → `prime_elite_board.elite_level`. An error names the fighter or the sentence the
/// data no longer supports: the paragraphs assert that Jones leads on points, on the résumé and
/// on Prime, that his two best wins stand above St-Pierre's best, and that the scale drifts up.
pub fn values(
    cur: &Frame,
    rated: &[Bout],
    p: &Pricing,
    h: &History,
    elite: &HashMap<String, f64>,
) -> Result<Vec<(&'static str, Figure)>, Error> {
    use Figure::{Name, Num};
    let f = cur.str("fighter")?;
    let n0 = |c: &str| cur.f64_or(c, 0.0);
    let [t, k, q] = points(
        &n0("public_legacy_title_score")?,
        &n0("public_legacy_skill_score")?,
        &n0("public_legacy_resume_score")?,
    );
    let score = cur.f64("public_legacy_score")?;
    let at = |name: &str| {
        f.iter()
            .position(|x| x == name)
            .ok_or_else(|| Error::at("figures", format!("{name} is not in the current table")))
    };
    let (a, b) = (at(PAIR[0])?, at(PAIR[1])?);
    let mut r = resume_rows(rated, p, None);
    r.sort_by(|x, y| y.mu.total_cmp(&x.mu));
    let best = |name: &str| r.iter().filter(|w| w.fighter == name).collect::<Vec<_>>();
    let (ra, rb) = (best(PAIR[0]), best(PAIR[1]));
    let level = |name: &str| {
        elite
            .get(name)
            .copied()
            .ok_or_else(|| Error::at("figures", format!("{name} is not on the Prime board")))
    };
    let (ea, eb) = (level(PAIR[0])?, level(PAIR[1])?);
    if ra.len() < 2 || rb.is_empty() {
        return Err(Error::at(
            "figures",
            format!(
                "{} has {} priced wins and {} has {}; the text needs two and one",
                PAIR[0],
                ra.len(),
                PAIR[1],
                rb.len()
            ),
        ));
    }
    let d = ea - eb;
    let gender: HashMap<String, String> = f.iter().cloned().zip(cur.str("gender")?).collect();
    let men: Vec<Row> = h
        .rows()
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
    let out = vec![
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
        ("prime_win", Num(1.0 / (1.0 + fm::pow(10.0, -d / 400.0)))),
        ("era_lo", Num(lo)),
        ("era_hi", Num(hi)),
        ("era_gap", Num(hi - lo)),
    ];
    verify(&out)?;
    Ok(out)
}

/// The paragraphs' fixed claims against the figures: a is ahead on points, résumé and Prime,
/// a's two best wins both stand above b's best, and the era line rises.
fn verify(v: &[(&'static str, Figure)]) -> Result<(), Error> {
    let g = |k: &str| v.iter().find(|p| p.0 == k).map_or(f64::NAN, |p| p.1.num());
    let checks = [
        ("ahead on points", g("ratio") > 0.0),
        ("ahead on résumé", g("resume_a") > g("resume_b")),
        (
            "two best wins above the other's best",
            g("elite_2_above") > g("best_b_above"),
        ),
        ("ahead on Prime", g("prime_edge") > 0.0),
        ("era line rises", g("era_gap") > 0.0),
    ];
    match checks.iter().find(|c| !c.1) {
        Some(c) => Err(Error::at(
            "figures",
            format!("{} is not {}; the README text claims it", PAIR[0], c.0),
        )),
        None => Ok(()),
    }
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
    let g = |k: &str| {
        v.iter()
            .find(|p| p.0 == k)
            .map(|p| p.1.clone())
            .unwrap_or_else(|| panic!("figure {k} missing"))
    };
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

#[cfg(test)]
mod tests {
    use super::*;

    fn figures(edit: impl Fn(&str, f64) -> f64) -> Vec<(&'static str, Figure)> {
        [
            ("ratio", 0.2),
            ("resume_a", 900.0),
            ("resume_b", 700.0),
            ("elite_2_above", 150.0),
            ("best_b_above", 100.0),
            ("prime_edge", 30.0),
            ("era_gap", 40.0),
        ]
        .into_iter()
        .map(|(k, x)| (k, Figure::Num(edit(k, x))))
        .collect()
    }

    #[test]
    fn claims_hold_or_error() {
        assert!(verify(&figures(|_, x| x)).is_ok());
        let e = verify(&figures(|k, x| if k == "era_gap" { -x } else { x })).unwrap_err();
        assert!(e.0.contains("era line rises"), "{e}");
        let e = verify(&figures(|k, x| if k == "resume_a" { 0.0 } else { x })).unwrap_err();
        assert!(e.0.contains("ahead on résumé"), "{e}");
    }

    #[test]
    fn missing_fighter_is_an_error() {
        use crate::frame::Table;
        use crate::layoff::Layoff;
        let cur = Table::default()
            .str("fighter", &[PAIR[0], PAIR[1]])
            .str("gender", &["M", "M"])
            .f64("public_legacy_title_score", &[1.0, 1.0])
            .f64("public_legacy_skill_score", &[1.0, 1.0])
            .f64("public_legacy_resume_score", &[1.0, 1.0])
            .f64("public_legacy_score", &[2.0, 1.0])
            .frame();
        let h = History::new(vec![]);
        let layoff = Layoff::new(&h);
        let p = Pricing {
            h: &h,
            rating: |r| r.mu,
            layoff: &layoff,
        };
        let mut elite = HashMap::new();
        elite.insert(PAIR[1].to_string(), 1.0);
        let e = values(&cur, &[], &p, &h, &elite).unwrap_err();
        assert!(e.0.contains("Jon Jones is not on the Prime board"), "{e}");
        elite.insert(PAIR[0].to_string(), 2.0);
        let e = values(&cur, &[], &p, &h, &elite).unwrap_err();
        assert!(e.0.contains("priced wins"), "{e}");
    }
}
