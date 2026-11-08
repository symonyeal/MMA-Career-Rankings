//! The Markdown blocks of RANKINGS.md and README.md.
//!
//! Each block sits between `<!-- NAME:BEGIN -->` and `<!-- NAME:END -->`
//! markers and is regenerated whole; the text around it is the owner's.
//! Score cells print as pandas did: `round(1)` shown with Python's float repr,
//! counts as `{:.0f}` (blank when missing).

use std::collections::HashMap;

use crate::boards::Boards;
use crate::divisions::{pool, MEN_LIMIT_LB};
use crate::frame::{iso, Frame};
use crate::history::History;
use crate::policy::{CONTENDER, MIN_PERIODS};
use crate::stats::{fmt0, np_round, py_repr};

/// `GENDER_GAUGE_NOTE`, printed above the women's All-time board.
const GAUGE_NOTE: &str =
    "Men and women do not compete against each other, so the engine publishes \
separate boards and each rank applies only within its own board.";

/// `ELITE_PRIME_TOP`, `CURRENT_BOARD_TOP`, the All-time head and the women's length.
const TOP: usize = 100;
const ELITE_TOP: usize = 50;
const CURRENT_TOP: usize = 30;
const WOMEN_TOP: usize = 10;

/// Blocks of RANKINGS.md, in file order of their markers' names; README.md carries the first-named four.
pub const RANKINGS: [&str; 8] = [
    "PUBLICATION:RELEASE",
    "BOARD:TOP100",
    "BOARD:WOMEN10",
    "BOARD:ELITEPRIME50",
    "BOARD:CURRENT30",
    "BOARD:CURRENTWOMEN10",
    "BOARD:ELITEPRIMEWOMEN10",
    "BOARD:CLASS",
];
pub const README: [&str; 4] = [
    "PUBLICATION:RELEASE",
    "BOARD:TOP100",
    "BOARD:ELITEPRIME50",
    "BOARD:CURRENT30",
];

/// `{:,}` of a count.
fn commas(n: i64) -> String {
    let s = n.abs().to_string();
    let mut out = String::new();
    for (i, ch) in s.chars().enumerate() {
        if i > 0 && (s.len() - i).is_multiple_of(3) {
            out.push(',');
        }
        out.push(ch);
    }
    if n < 0 {
        format!("-{out}")
    } else {
        out
    }
}

/// Text left, figures right.
fn table(cols: &[(&str, Vec<String>)]) -> String {
    let left = |n: &str| n == "Fighter" || n == "Division";
    let mut lines = vec![
        format!(
            "| {} |",
            cols.iter().map(|c| c.0).collect::<Vec<_>>().join(" | ")
        ),
        format!(
            "|{}|",
            cols.iter()
                .map(|c| if left(c.0) { " --- " } else { " ---: " })
                .collect::<Vec<_>>()
                .join("|")
        ),
    ];
    for i in 0..cols[0].1.len() {
        lines.push(format!(
            "| {} |",
            cols.iter()
                .map(|c| c.1[i].as_str())
                .collect::<Vec<_>>()
                .join(" | ")
        ));
    }
    lines.join("\n")
}

fn cell(x: Option<f64>) -> String {
    x.map_or(String::new(), fmt0)
}

fn escape(name: &str) -> String {
    name.replace('|', "\\|")
}

/// The ratings_current columns the tables print, by fighter.
struct Lookup<'a> {
    row: HashMap<&'a str, usize>,
    gender: Vec<String>,
    career: Vec<String>,
    now: Vec<String>,
    title_wins: Vec<f64>,
    contender_wins: Vec<f64>,
    last: Vec<Option<i32>>,
}

impl<'a> Lookup<'a> {
    fn new(c: &Frame, fighter: &'a [String]) -> Lookup<'a> {
        let (u, r, w) = (
            c.day("last_ufc_event_date"),
            c.day("last_recorded_event_date"),
            c.day("whr_last_event_date"),
        );
        Lookup {
            row: fighter
                .iter()
                .enumerate()
                .map(|(i, f)| (f.as_str(), i))
                .collect(),
            gender: c.str("gender"),
            career: c.str("career_division"),
            now: c.str("current_division"),
            title_wins: c.f64("current_title_wins"),
            contender_wins: c.f64("current_contender_wins"),
            last: (0..u.len()).map(|i| u[i].or(r[i]).or(w[i])).collect(),
        }
    }

    fn division(&self, f: &str, current: bool) -> String {
        let i = self.row[f];
        pool(
            if current {
                &self.now[i]
            } else {
                &self.career[i]
            },
            &self.gender[i],
        )
        .unwrap_or_default()
    }
}

/// `top_board_markdown`: the All-time board (with Score and Prime rank) or the elite Prime board (without).
fn top_board(
    top: &[(String, i64)],
    n: usize,
    look: &Lookup,
    b: &Boards,
    score: Option<&HashMap<&str, f64>>,
    prime_rank: Option<&HashMap<String, i64>>,
) -> String {
    let rows = &top[..n.min(top.len())];
    let d = |f: &str| b.decades.get(f);
    let mut cols: Vec<(&str, Vec<String>)> = vec![
        ("#", rows.iter().map(|r| r.1.to_string()).collect()),
        ("Fighter", rows.iter().map(|r| escape(&r.0)).collect()),
        (
            "Division",
            rows.iter().map(|r| look.division(&r.0, false)).collect(),
        ),
    ];
    if let Some(s) = score {
        cols.push((
            "Score",
            rows.iter()
                .map(|r| py_repr(np_round(s[r.0.as_str()], 1)))
                .collect(),
        ));
    }
    cols.push((
        "Prime",
        rows.iter()
            .map(|r| cell(d(&r.0).map(|x| x.level).filter(|x| !x.is_nan())))
            .collect(),
    ));
    if let Some(p) = prime_rank {
        cols.push((
            "Prime rank",
            rows.iter()
                .map(|r| cell(p.get(&r.0).map(|&k| k as f64)))
                .collect(),
        ));
    }
    cols.push((
        "Elite wins",
        rows.iter()
            .map(|r| cell(d(&r.0).map(|x| x.wins as f64)))
            .collect(),
    ));
    table(&cols)
}

/// `current_board_markdown`: the score, its title and contender wins inside the window, and recency.
fn current_board(
    top: &[(String, i64, f64)],
    n: usize,
    look: &Lookup,
    bouts: &HashMap<&str, f64>,
) -> String {
    let rows = &top[..n.min(top.len())];
    let at = |v: &[f64], f: &str| cell(Some(v[look.row[f]]).filter(|x| !x.is_nan()));
    table(&[
        ("#", rows.iter().map(|r| r.1.to_string()).collect()),
        ("Fighter", rows.iter().map(|r| escape(&r.0)).collect()),
        (
            "Division",
            rows.iter().map(|r| look.division(&r.0, true)).collect(),
        ),
        (
            "Score",
            rows.iter()
                .map(|r| (np_round(r.2, 0) as i64).to_string())
                .collect(),
        ),
        (
            "Title wins",
            rows.iter().map(|r| at(&look.title_wins, &r.0)).collect(),
        ),
        (
            "Contender wins",
            rows.iter()
                .map(|r| at(&look.contender_wins, &r.0))
                .collect(),
        ),
        (
            "UFC bouts",
            rows.iter()
                .map(|r| cell(Some(bouts[r.0.as_str()])))
                .collect(),
        ),
        (
            "Last UFC bout",
            rows.iter()
                .map(|r| look.last[look.row[r.0.as_str()]].map_or(String::new(), iso))
                .collect(),
        ),
    ])
}

/// `CLASS_ORDER`: men heaviest first, then the women's classes heaviest first.
fn class_order() -> Vec<&'static str> {
    MEN_LIMIT_LB
        .iter()
        .rev()
        .map(|p| p.0)
        .chain([
            "Women's Featherweight",
            "Women's Bantamweight",
            "Women's Flyweight",
            "Women's Strawweight",
            "Women's Atomweight",
        ])
        .collect()
}

/// `class_board_markdown`: top 10 men / 5 women per class with at least 10 ranked.
fn class_board(classes: &Frame, b: &Boards) -> String {
    let (g, d, rank, fighter, score, share) = (
        classes.str("gender"),
        classes.str("division"),
        classes.i64("rank"),
        classes.str("fighter"),
        classes.f64("score"),
        classes.f64("share"),
    );
    let mut parts = Vec::new();
    for (k, (gender, label, n)) in [("M", "Men", 10), ("F", "Women", 5)]
        .into_iter()
        .enumerate()
    {
        for div in class_order() {
            let rows: Vec<usize> = (0..g.len())
                .filter(|&i| g[i] == gender && d[i] == div)
                .collect();
            if rows.len() < 10 {
                continue;
            }
            let rows = &rows[..n];
            parts.push(format!(
                "#### {label} — {div}\n\n{}",
                table(&[
                    ("#", rows.iter().map(|&i| rank[i].to_string()).collect()),
                    (
                        "Fighter",
                        rows.iter().map(|&i| escape(&fighter[i])).collect()
                    ),
                    (
                        "Class score",
                        rows.iter()
                            .map(|&i| py_repr(np_round(score[i], 1)))
                            .collect()
                    ),
                    (
                        "Share of All-time",
                        rows.iter()
                            .map(|&i| format!("{:.0}%", share[i] * 100.0))
                            .collect()
                    ),
                    (
                        "All-time #",
                        rows.iter()
                            .map(|&i| cell(b.all_time_rank[k].get(&fighter[i]).map(|&x| x as f64)))
                            .collect()
                    ),
                ])
            ));
        }
    }
    parts.join("\n\n")
}

/// `contender_line_reach`: share of established fighters whose era-adjusted peak reached the contender line.
fn reach(current: &Frame, history: &History) -> f64 {
    let (fighter, periods) = (current.str("fighter"), current.i64("rating_periods"));
    let peaks: Vec<f64> = fighter
        .iter()
        .zip(&periods)
        .filter(|(_, &p)| p >= MIN_PERIODS)
        .filter_map(|(f, _)| {
            history
                .of(f)
                .iter()
                .map(|r| r.era)
                .filter(|x| !x.is_nan())
                .reduce(f64::max)
        })
        .collect();
    peaks.iter().filter(|&&x| x >= CONTENDER).count() as f64 / peaks.len() as f64
}

/// Release facts that come from the run rather than the tables.
pub struct Release<'a> {
    /// snapshot folder name
    pub snapshot: &'a str,
    /// last staged event date, ISO
    pub through: &'a str,
    pub rated_bouts: i64,
    /// staged fight records (combined_fights_summary.json `rows`)
    pub records: i64,
    /// fighters eligible for whole-career coverage, and those merged
    pub eligible: i64,
    pub merged: i64,
}

/// `publication_release_markdown`: the release facts, generated from the same snapshot as the tables.
fn release(r: &Release, current: &Frame, history: &History, b: &Boards) -> String {
    let (eligible, merged) = (r.eligible, r.merged);
    let (men, women) = (b.prime_ranked[0] as i64, b.prime_ranked[1] as i64);
    let rows = [
        ("Dataset", r.snapshot.to_string()),
        ("Data through", r.through.to_string()),
        (
            "Included records",
            "UFC, early UFC and major-promotion careers".into(),
        ),
        ("All-time basis", "All-time career score".into()),
        ("Rated fights", commas(r.rated_bouts)),
        ("Rated fighters", commas(current.len() as i64)),
        ("Available fight records", commas(r.records)),
        (
            "Whole-career coverage",
            format!(
                "{} of {} eligible fighters ({:.1}%)",
                commas(merged),
                commas(eligible),
                merged as f64 / eligible as f64 * 100.0
            ),
        ),
        (
            "Prime contender threshold",
            format!(
                "{} — reached by {:.1}% of established fighters",
                commas(CONTENDER as i64),
                reach(current, history) * 100.0
            ),
        ),
        (
            "Prime qualifiers",
            format!(
                "{} {}; {} {}",
                commas(men),
                if men == 1 { "man" } else { "men" },
                commas(women),
                if women == 1 { "woman" } else { "women" }
            ),
        ),
    ];
    let mut lines = vec![
        "| Release fact | Value |".to_string(),
        "| --- | ---: |".to_string(),
    ];
    lines.extend(rows.iter().map(|(l, v)| format!("| {l} | {v} |")));
    lines.join("\n")
}

/// Every block body by marker name. `current` is ratings_current, `classes` the class board.
pub fn blocks(
    b: &Boards,
    current: &Frame,
    history: &History,
    classes: &Frame,
    r: &Release,
) -> Vec<(&'static str, String)> {
    let fighter = current.str("fighter");
    let look = Lookup::new(current, &fighter);
    let legacy: HashMap<&str, f64> = fighter
        .iter()
        .map(String::as_str)
        .zip(current.f64("public_legacy_score"))
        .collect();
    let bouts: HashMap<&str, f64> = fighter
        .iter()
        .map(String::as_str)
        .zip(current.f64("public_legacy_ufc_bouts"))
        .collect();
    vec![
        ("PUBLICATION:RELEASE", release(r, current, history, b)),
        (
            "BOARD:TOP100",
            top_board(
                &b.all_time_top[0],
                TOP,
                &look,
                b,
                Some(&legacy),
                Some(&b.prime_rank[0]),
            ),
        ),
        (
            "BOARD:WOMEN10",
            format!(
                "{GAUGE_NOTE}\n\n{}",
                top_board(
                    &b.all_time_top[1],
                    WOMEN_TOP,
                    &look,
                    b,
                    Some(&legacy),
                    Some(&b.prime_rank[1])
                )
            ),
        ),
        (
            "BOARD:ELITEPRIME50",
            top_board(&b.prime_top[0], ELITE_TOP, &look, b, None, None),
        ),
        (
            "BOARD:CURRENT30",
            current_board(&b.current_top[0], CURRENT_TOP, &look, &bouts),
        ),
        (
            "BOARD:CURRENTWOMEN10",
            current_board(&b.current_top[1], WOMEN_TOP, &look, &bouts),
        ),
        (
            "BOARD:ELITEPRIMEWOMEN10",
            top_board(&b.prime_top[1], WOMEN_TOP, &look, b, None, None),
        ),
        ("BOARD:CLASS", class_board(classes, b)),
    ]
}

/// Replaces the named blocks of `text`; the result has LF line endings. Panics unless each marker pair occurs exactly once.
pub fn splice(text: &str, blocks: &[(&str, String)], names: &[&str]) -> String {
    let mut out = text.replace("\r\n", "\n");
    for name in names {
        let body = &blocks
            .iter()
            .find(|x| x.0 == *name)
            .unwrap_or_else(|| panic!("no block {name}"))
            .1;
        let (begin, end) = (
            format!("<!-- {name}:BEGIN -->"),
            format!("<!-- {name}:END -->"),
        );
        assert!(
            out.matches(&begin).count() == 1 && out.matches(&end).count() == 1,
            "{name}: expected one marker pair"
        );
        let i = out.find(&begin).unwrap();
        let j = out[i..].find(&end).unwrap() + i + end.len();
        out.replace_range(i..j, &format!("{begin}\n\n{body}\n\n{end}"));
    }
    out
}
