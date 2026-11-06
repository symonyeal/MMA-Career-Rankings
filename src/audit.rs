//! Audit of the published men's top 100 against public-perception anchors.
//!
//! Each of the 100 carries its ratings row, its coverage (bouts, UFC bouts,
//! first and last appearance, birth date), its connectivity to the rated core,
//! its best public anchor rank (Tapology, ESPN, "The 100 Greatest", the Fight
//! Matrix all-time list) and a plain reading of the gap. Written to
//! `data/model_tuning/top100-audit`: the table (parquet and csv), the score
//! comparison against the skill-mass ordering, the anchors missing from the
//! 100, and a JSON summary.

use std::collections::{BTreeMap, HashMap, HashSet};
use std::fmt::Write as _;
use std::path::Path;
use std::sync::Arc;

use arrow::array::{Array, ArrayRef, AsArray, RecordBatch};
use arrow::compute::cast;
use arrow::datatypes::{DataType, Field, Float64Type, Int64Type, Schema, TimeUnit};
use serde_json::{json, Value};

use crate::bouts::Bout;
use crate::connectivity::{Graph, MIN_PATHS};
use crate::divisions::female;
use crate::era::year;
use crate::frame::{iso, Day, Frame, Table};
use crate::history::History;
use crate::stats::{py_repr, py_round};

const SCORE: &str = "public_legacy_score";
const SKILL: &str = "symon_career_skill_mass";

const TAPOLOGY: [&str; 10] = [
    "Georges St-Pierre",
    "Demetrious Johnson",
    "Islam Makhachev",
    "Jon Jones",
    "Alexander Volkanovski",
    "Daniel Cormier",
    "Khabib Nurmagomedov",
    "Anderson Silva",
    "Ilia Topuria",
    "Jose Aldo",
];
const ESPN: [&str; 10] = [
    "Jon Jones",
    "Georges St-Pierre",
    "Anderson Silva",
    "Demetrious Johnson",
    "Khabib Nurmagomedov",
    "Fedor Emelianenko",
    "Randy Couture",
    "Chuck Liddell",
    "BJ Penn",
    "Kamaru Usman",
];
const THE100: [(&str, i64); 34] = [
    ("Anderson Silva", 3),
    ("Stipe Miocic", 9),
    ("Ilia Topuria", 10),
    ("Alex Pereira", 11),
    ("Israel Adesanya", 12),
    ("Dricus Du Plessis", 15),
    ("Kamaru Usman", 16),
    ("Max Holloway", 17),
    ("Leon Edwards", 25),
    ("Henry Cejudo", 26),
    ("Alexandre Pantoja", 29),
    ("Randy Couture", 31),
    ("Alistair Overeem", 33),
    ("Charles Oliveira", 34),
    ("Dustin Poirier", 35),
    ("Conor McGregor", 36),
    ("Frank Shamrock", 38),
    ("Robert Whittaker", 45),
    ("Petr Yan", 52),
    ("Ken Shamrock", 53),
    ("Bas Rutten", 54),
    ("Glover Teixeira", 60),
    ("Vadim Nemkov", 62),
    ("Ryan Bader", 63),
    ("Phil Davis", 64),
    ("Frankie Edgar", 65),
    ("TJ Dillashaw", 71),
    ("Josh Barnett", 72),
    ("BJ Penn", 80),
    ("Tyron Woodley", 81),
    ("Tony Ferguson", 95),
    ("Benson Henderson", 97),
    ("Robbie Lawler", 98),
    ("Tom Aspinall", 100),
];
const QUALITATIVE: [(&str, &str); 5] = [
    (
        "Amanda Nunes",
        "public women's GOAT tier from discrepancy prompt",
    ),
    (
        "Cristiane Justino",
        "public women's GOAT tier from discrepancy prompt",
    ),
    ("Valentina Shevchenko", "public women's all-time elite tier"),
    (
        "Patricio Freire",
        "publicly strong Bellator all-time tier from discrepancy prompt",
    ),
    (
        "Ronda Rousey",
        "public impact and women's pioneer tier from discrepancy prompt",
    ),
];
const NON_ANCHORS: [&str; 31] = [
    "Usman Nurmagomedov",
    "Yaroslav Amosov",
    "A.J. McKee",
    "Johnny Eblen",
    "Kyoji Horiguchi",
    "Sean Sherk",
    "Ben Askren",
    "Michael Page",
    "Rajabali Shaidullaev",
    "Seika Izawa",
    "Timur Khizriev",
    "Vladimir Matyushenko",
    "Paulo Filho",
    "Andrey Koreshkov",
    "Ramazan Kuramagomedov",
    "Renato Sobral",
    "Jon Fitch",
    "Gilbert Melendez",
    "Joseph Benavidez",
    "Archie Colgan",
    "Vitaly Minakov",
    "Pedro Rizzo",
    "Tim Sylvia",
    "Miguel Torres",
    "Shinya Aoki",
    "Diego Sanchez",
    "Vitor Ribeiro",
    "Vladyslav Rudniev",
    "Ricco Rodriguez",
    "Oleg Popov",
    "Patchy Mix",
];
const WATCH_BELOW_40: [&str; 9] = [
    "Anderson Silva",
    "Demetrious Johnson",
    "Jose Aldo",
    "Stipe Miocic",
    "Kamaru Usman",
    "Max Holloway",
    "Amanda Nunes",
    "Charles Oliveira",
    "Dustin Poirier",
];
const MISSING_FIX: &str =
    "Missing from model top 100; inspect title/resume signal, late-career smoothing, and data coverage.";

/// Anchor key: casefolded, alphanumerics only.
fn key(name: &str) -> String {
    name.to_lowercase()
        .replace('ß', "ss")
        .chars()
        .filter(|c| c.is_ascii_lowercase() || c.is_ascii_digit())
        .collect()
}

/// Public anchors by key, each `(source, rank)` in insertion order, and the first spelling of each key.
struct Anchors {
    rows: Vec<(String, Vec<(&'static str, i64)>)>,
    at: HashMap<String, usize>,
    name: HashMap<String, String>,
}

impl Anchors {
    fn new(snapshot: &Path) -> Anchors {
        let mut a = Anchors {
            rows: vec![],
            at: HashMap::new(),
            name: HashMap::new(),
        };
        for (r, f) in TAPOLOGY.iter().enumerate() {
            a.add(f, "Tapology fan top 10", r as i64 + 1);
        }
        for (r, f) in ESPN.iter().enumerate() {
            a.add(f, "ESPN 21st-century men top 10", r as i64 + 1);
        }
        for (f, r) in THE100 {
            a.add(f, "The 100 Greatest", r);
        }
        let p = snapshot.join("fightmatrix_all_time.parquet");
        if p.exists() {
            let fm = Frame::read(&p);
            let rank = fm.f64("rank");
            for (f, r) in fm.str("fighter").iter().zip(rank) {
                if !f.is_empty() && !r.is_nan() {
                    a.add(f, "FightMatrix all-time local snapshot", r as i64);
                }
            }
        }
        a
    }

    fn add(&mut self, fighter: &str, source: &'static str, rank: i64) {
        let k = key(fighter);
        self.name
            .entry(k.clone())
            .or_insert_with(|| fighter.to_string());
        let i = *self.at.entry(k.clone()).or_insert_with(|| {
            self.rows.push((k, vec![]));
            self.rows.len() - 1
        });
        self.rows[i].1.push((source, rank));
    }

    fn of(&self, fighter: &str) -> &[(&'static str, i64)] {
        self.at.get(&key(fighter)).map_or(&[], |&i| &self.rows[i].1)
    }

    fn rank(&self, fighter: &str) -> Option<i64> {
        self.of(fighter).iter().map(|r| r.1).min()
    }

    fn has(&self, fighter: &str) -> bool {
        !self.of(fighter).is_empty() || qualitative(fighter).is_some()
    }

    fn reason(&self, fighter: &str) -> String {
        let rows = self.of(fighter);
        if !rows.is_empty() {
            return rows
                .iter()
                .map(|(s, r)| format!("{s}: {r}"))
                .collect::<Vec<_>>()
                .join("; ");
        }
        if let Some(q) = qualitative(fighter) {
            return q.to_string();
        }
        if NON_ANCHORS.iter().any(|n| key(n) == key(fighter)) {
            return "not in supplied public top-100/top-10 anchors".into();
        }
        "no supplied public anchor".into()
    }
}

fn qualitative(fighter: &str) -> Option<&'static str> {
    QUALITATIVE
        .iter()
        .find(|(n, _)| key(n) == key(fighter))
        .map(|p| p.1)
}

/// `public_legacy_eligibility_override`: proven UFC title resumes rank before the 13-period floor.
fn title_override(periods: f64, ufc: f64, score: f64, wins: f64, defenses: f64) -> bool {
    let z = |x: f64| if x.is_nan() { 0.0 } else { x };
    let (periods, ufc, score, wins, defenses) =
        (z(periods), z(ufc), z(score), z(wins), z(defenses));
    periods >= 8.0 && ufc >= 8.0 && score > 0.0 && (wins >= 3.0 || (wins >= 2.0 && defenses >= 1.0))
}

/// `_ranked`: rows of `pop` eligible on `col` with a positive score, by score desc then name;
/// returns `(row, score)` in rank order.
fn ranked(c: &Frame, pop: &[usize], col: &str) -> Vec<(usize, f64)> {
    let (score, periods) = (c.f64(col), c.f64("rating_periods"));
    let (ufc, total, wins, def) = (
        c.f64("public_legacy_ufc_bouts"),
        c.f64(SCORE),
        c.f64("public_legacy_title_wins"),
        c.f64("public_legacy_title_defenses"),
    );
    let names = c.str("fighter");
    let mut out: Vec<(usize, f64)> = pop
        .iter()
        .copied()
        .filter(|&i| {
            let floor = periods[i] >= 13.0
                || (col == SCORE && title_override(periods[i], ufc[i], total[i], wins[i], def[i]));
            floor && score[i] > 0.0
        })
        .map(|i| (i, score[i]))
        .collect();
    out.sort_by(|x, y| {
        y.1.total_cmp(&x.1)
            .then_with(|| names[x.0].cmp(&names[y.0]))
    });
    out
}

/// `f"{x:,.{d}f}"`, "NA" for a missing value.
fn num(x: f64, d: usize) -> String {
    if x.is_nan() {
        return "NA".into();
    }
    let s = format!("{x:.d$}");
    let (sign, s) = s.strip_prefix('-').map_or(("", s.as_str()), |r| ("-", r));
    let (int, frac) = s.split_once('.').map_or((s, None), |(i, f)| (i, Some(f)));
    let mut g = String::new();
    for (k, ch) in int.chars().enumerate() {
        if k > 0 && (int.len() - k) % 3 == 0 {
            g.push(',');
        }
        g.push(ch);
    }
    format!(
        "{sign}{g}{}",
        frac.map_or(String::new(), |f| format!(".{f}"))
    )
}

struct Row {
    rank: i64,
    anchor: Option<i64>,
    has_anchor: bool,
    external: bool,
    active: bool,
    title_wins: i64,
}

fn outlier(r: &Row) -> &'static str {
    let Some(public) = r.anchor else {
        return if r.has_anchor {
            "qualitative_anchor_no_rank"
        } else if r.external && r.active {
            "active_external_unanchored"
        } else if r.rank <= 25 {
            "unanchored_top25"
        } else {
            "unanchored"
        };
    };
    let delta = r.rank - public;
    match () {
        _ if r.rank <= 25 && public >= 50 => "severe_overplacement",
        _ if delta <= -40 => "severe_overplacement",
        _ if delta <= -20 => "overplacement",
        _ if delta >= 40 => "severe_underplacement",
        _ if delta >= 20 => "underplacement",
        _ => "aligned_or_explainable",
    }
}

fn recommendation(r: &Row, class: &str) -> &'static str {
    if class == "qualitative_anchor_no_rank" {
        "No numeric delta available; keep the qualitative public-resume explanation visible."
    } else if r.external && r.title_wins == 0 && r.rank <= 25 {
        "Do not defend as proven public greatness yet: non-UFC title lineage is missing from the title ledger, \
         so this is a skill-mass/crossover claim."
    } else if class == "severe_underplacement" || class == "underplacement" {
        "Audit prime-vs-twilight and impact/title context; current score still trails public anchor."
    } else if class == "severe_overplacement" || class == "overplacement" {
        "Audit whether WHR smoothing backfilled future skill into early years or a closed external graph."
    } else if class.starts_with("unanchored") {
        "Keep only with a written plain-English schedule-strength explanation."
    } else {
        "No immediate model change; keep the decomposition visible."
    }
}

/// Writes the five audit files into `dir`.
///
/// `rated` are the rated bouts of the published scope (`load_fight_table`);
/// `canonical` the (fighter_a, fighter_b) pairs of `canonical_fights`, the rated core.
pub fn write(
    dir: &Path,
    snapshot: &Path,
    current: &Frame,
    history: &History,
    rated: &[Bout],
    canonical: &[(String, String)],
    births: &HashMap<String, Day>,
) {
    let c = current;
    let anchors = Anchors::new(snapshot);
    let names = c.str("fighter");
    let gender = c.str("gender");
    let (men, women): (Vec<usize>, Vec<usize>) = (0..c.len()).partition(|&i| !female(&gender[i]));
    let published = ranked(c, &men, SCORE);
    let published_women = ranked(c, &women, SCORE);
    let skill = ranked(c, &men, SKILL);

    // Score comparison: outer join on fighter, sorted by name.
    let mut cmp: BTreeMap<&str, [Option<(i64, f64)>; 2]> = BTreeMap::new();
    for (side, board) in [&published, &skill].into_iter().enumerate() {
        for (r, &(i, s)) in board.iter().enumerate() {
            cmp.entry(&names[i]).or_default()[side] = Some((r as i64 + 1, s));
        }
    }
    let complete = cmp.values().all(|v| v[0].is_some() && v[1].is_some());
    let col = |side: usize, f: fn((i64, f64)) -> f64| {
        cmp.values()
            .map(|v| v[side].map_or(f64::NAN, f))
            .collect::<Vec<_>>()
    };
    let (rp, sp, rs, ss) = (
        col(0, |p| p.0 as f64),
        col(0, |p| p.1),
        col(1, |p| p.0 as f64),
        col(1, |p| p.1),
    );
    let change: Vec<f64> = rs.iter().zip(&rp).map(|(a, b)| a - b).collect();
    let ints = |v: &[f64]| v.iter().map(|&x| x as i64).collect::<Vec<_>>();
    let mut t = Table::default().str("fighter", &cmp.keys().copied().collect::<Vec<_>>());
    t = if complete {
        t.i64("model_rank_public", &ints(&rp))
    } else {
        t.f64("model_rank_public", &rp)
    };
    t = t.f64("score_public", &sp);
    t = if complete {
        t.i64("model_rank_skill_mass", &ints(&rs))
    } else {
        t.f64("model_rank_skill_mass", &rs)
    };
    t = t.f64("score_skill_mass", &ss);
    t = if complete {
        t.i64("rank_change_vs_skill_mass", &ints(&change))
    } else {
        t.f64("rank_change_vs_skill_mass", &change)
    };
    std::fs::create_dir_all(dir).unwrap();
    write_parquet(&t.frame(), &dir.join("top100_score_comparison.parquet"));

    // The top 100 with coverage and connectivity.
    let top: Vec<(usize, f64)> = published.iter().take(100).copied().collect();
    let who: Vec<&str> = top.iter().map(|&(i, _)| names[i].as_str()).collect();
    let mut bouts: HashMap<&str, (i64, i64)> = HashMap::new();
    for b in rated {
        for f in [b.a(), b.b()] {
            let e = bouts.entry(f).or_default();
            e.0 += 1;
            e.1 += i64::from(b.source == "ufc");
        }
    }
    let core: HashSet<&str> = canonical
        .iter()
        .flat_map(|(a, b)| [a.as_str(), b.as_str()])
        .collect();
    let mut counts: HashMap<String, usize> = HashMap::new();
    for (a, b) in canonical {
        for f in [a, b].into_iter().filter(|f| !f.is_empty()) {
            *counts.entry(f.clone()).or_default() += 1;
        }
    }
    let graph = Graph::new(
        rated.iter().map(|b| (b.a().as_str(), b.b().as_str())),
        &counts,
    );
    let span = |f: &str| {
        let rows = history.of(f);
        (
            rows.iter().map(|r| r.day).min(),
            rows.iter().map(|r| r.day).max(),
        )
    };
    let (first, last): (Vec<Option<Day>>, Vec<Option<Day>>) = who.iter().map(|f| span(f)).unzip();
    let total: Vec<i64> = who.iter().map(|f| bouts[f].0).collect();
    let ufc: Vec<i64> = who.iter().map(|f| bouts[f].1).collect();
    let paths: Vec<f64> = who
        .iter()
        .map(|f| graph.paths(f).map_or(f64::NAN, |p| p as f64))
        .collect();
    let rankable: Vec<bool> = who
        .iter()
        .zip(&paths)
        .map(|(f, p)| core.contains(f) || *p >= MIN_PATHS as f64)
        .collect();
    let born: Vec<bool> = who.iter().map(|f| births.contains_key(*f)).collect();
    let active: Vec<bool> = last
        .iter()
        .map(|d| d.is_some_and(|d| year(d) >= 2024))
        .collect();
    let external: Vec<bool> = ufc.iter().map(|&u| u == 0).collect();
    let anchor: Vec<Option<i64>> = who.iter().map(|f| anchors.rank(f)).collect();
    let has: Vec<bool> = who.iter().map(|f| anchors.has(f)).collect();

    let g = |n: &str| c.f64(n);
    let (skill_mass, skill_score, exposure, resume, contender, tw, td, tdiv) = (
        g(SKILL),
        g("public_legacy_skill_score"),
        g("public_legacy_exposure_factor"),
        g("public_legacy_resume_score"),
        g("public_legacy_contender_wins"),
        g("public_legacy_title_wins"),
        g("public_legacy_title_defenses"),
        g("public_legacy_title_win_divisions"),
    );
    let (mut reasons, mut classes, mut fixes) = (vec![], vec![], vec![]);
    for (k, &(i, s)) in top.iter().enumerate() {
        let int = |x: f64| x as i64;
        let source = if ufc[k] == 0 {
            "external-only".to_string()
        } else {
            format!("{}/{} UFC-rated", ufc[k], total[k])
        };
        reasons.push(format!(
            "{SCORE} {}; skill mass {}; evaluated skill {} (exposure {}); contender resume {} ({} wins); \
             title ledger {} wins/{} defenses/{} divisions; {source}",
            num(s, 1), num(skill_mass[i], 1), num(skill_score[i], 1), num(exposure[i], 2), num(resume[i], 1),
            int(contender[i]), int(tw[i]), int(td[i]), int(tdiv[i]),
        ));
        let r = Row {
            rank: k as i64 + 1,
            anchor: anchor[k],
            has_anchor: has[k],
            external: external[k],
            active: active[k],
            title_wins: int(tw[i]),
        };
        let class = outlier(&r);
        classes.push(class);
        fixes.push(recommendation(&r, class));
    }
    let added = Table::default()
        .f64("score", &top.iter().map(|p| p.1).collect::<Vec<_>>())
        .i64("model_rank", &(1..=top.len() as i64).collect::<Vec<_>>())
        .day("first_appearance", &first)
        .day("last_appearance", &last)
        .i64("total_bouts", &total)
        .i64("ufc_bouts", &ufc)
        .f64("disjoint_paths", &paths)
        .bool("rankable", &rankable)
        .bool("birth_date_known", &born)
        .bool("active_2024_plus", &active)
        .bool("external_only", &external)
        .f64(
            "public_anchor_rank",
            &anchor
                .iter()
                .map(|a| a.map_or(f64::NAN, |a| a as f64))
                .collect::<Vec<_>>(),
        )
        .f64(
            "delta",
            &anchor
                .iter()
                .enumerate()
                .map(|(k, a)| a.map_or(f64::NAN, |a| (k as i64 + 1 - a) as f64))
                .collect::<Vec<_>>(),
        )
        .bool("has_public_anchor", &has)
        .str(
            "public_reason",
            &who.iter().map(|f| anchors.reason(f)).collect::<Vec<_>>(),
        )
        .str("model_reason", &reasons)
        .str("outlier_class", &classes)
        .str("recommended_fix_or_explanation", &fixes)
        .frame();
    let audit = c
        .take(&top.iter().map(|p| Some(p.0)).collect::<Vec<_>>())
        .hstack(&[&added]);
    write_parquet(&audit, &dir.join("top100_audit.parquet"));
    std::fs::write(dir.join("top100_audit.csv"), csv(&audit)).unwrap();

    // Anchors absent from the 100, best rank first.
    let in_top: HashSet<String> = who.iter().map(|f| key(f)).collect();
    let mut missing: Vec<(i64, String)> = anchors
        .rows
        .iter()
        .filter(|(k, _)| !in_top.contains(k))
        .map(|(k, rows)| {
            (
                rows.iter().map(|r| r.1).min().unwrap(),
                anchors.name[k].clone(),
            )
        })
        .collect();
    missing.sort();
    let mut m =
        String::from("fighter,public_anchor_rank,public_reason,recommended_fix_or_explanation\n");
    for (r, f) in &missing {
        let _ = writeln!(
            m,
            "{},{r},{},{}",
            cell(f),
            cell(&anchors.reason(f)),
            cell(MISSING_FIX)
        );
    }
    std::fs::write(dir.join("public_anchor_missing_from_model_top100.csv"), m).unwrap();

    // Summary.
    let mut on_board: HashMap<String, (i64, &str)> = HashMap::new();
    for (board, rows) in [("men", &published), ("women", &published_women)] {
        for (r, &(i, _)) in rows.iter().enumerate() {
            on_board.insert(key(&names[i]), (r as i64 + 1, board));
        }
    }
    let below40: Vec<Value> = WATCH_BELOW_40
        .iter()
        .filter_map(|f| {
            let found = on_board.get(&key(f));
            (found.is_none_or(|p| p.0 > 40)).then(|| {
                json!({"fighter": f, "model_rank": found.map(|p| p.0), "board": found.map(|p| p.1),
                       "reason": anchors.reason(f)})
            })
        })
        .collect();
    let pick = |n: usize, keep: &dyn Fn(usize) -> bool| -> Vec<&str> {
        (0..n.min(who.len()))
            .filter(|&k| keep(k))
            .map(|k| who[k])
            .collect()
    };
    let debut = |keep: fn(i32) -> bool| {
        first
            .iter()
            .filter(|d| d.is_some_and(|d| keep(year(d))))
            .count()
    };
    let summary = json!({
        "snapshot": snapshot.file_name().unwrap().to_string_lossy(),
        "scope": crate::bouts::SCOPE.trim(),
        "published_score": SCORE,
        "diagnostic_score": SKILL,
        "board": "men (the published default)",
        "ranked_fighters": published.len(),
        "ranked_fighters_women_board": published_women.len(),
        "top100_birth_date_coverage": py_round(born.iter().filter(|&&b| b).count() as f64 / born.len() as f64, 4),
        "top100_active_2024_plus": active.iter().filter(|&&b| b).count(),
        "top100_external_only": external.iter().filter(|&&b| b).count(),
        "top100_connectivity_rankable": rankable.iter().filter(|&&b| b).count(),
        "external_only_names": pick(100, &|k| external[k]),
        "top100_debut_before_2000": debut(|y| y < 2000),
        "top100_debut_2015_plus": debut(|y| y >= 2015),
        "top25_unanchored_count": pick(25, &|k| !has[k]).len(),
        "top25_unanchored_names": pick(25, &|k| !has[k]),
        "top10_active_external_unanchored": pick(10, &|k| external[k] && active[k] && !has[k]),
        "watch_names_below_40_or_missing": below40,
        "missing_public_anchor_names": missing.iter().map(|(r, f)| json!({
            "fighter": f, "public_anchor_rank": r, "public_reason": anchors.reason(f),
            "recommended_fix_or_explanation": MISSING_FIX})).collect::<Vec<_>>(),
        "top10": (0..10.min(top.len())).map(|k| json!({
            "model_rank": k + 1, "fighter": who[k], "score": top[k].1, "model_reason": reasons[k]})).collect::<Vec<_>>(),
    });
    std::fs::write(dir.join("top100_audit.json"), python_json(&summary) + "\n").unwrap();
}

/// Parquet as pandas writes it: strings as `large_string`.
fn write_parquet(f: &Frame, path: &Path) {
    let b = f.batch();
    let (fields, columns): (Vec<Field>, Vec<ArrayRef>) = b
        .schema()
        .fields()
        .iter()
        .zip(b.columns())
        .map(|(fi, a)| match fi.data_type() {
            DataType::Utf8 => (
                Field::new(fi.name(), DataType::LargeUtf8, true),
                cast(a, &DataType::LargeUtf8).unwrap(),
            ),
            _ => (fi.as_ref().clone(), a.clone()),
        })
        .unzip();
    Frame::from_batch(RecordBatch::try_new(Arc::new(Schema::new(fields)), columns).unwrap())
        .write(path);
}

/// A csv field quoted as Python's `csv.QUOTE_MINIMAL` does.
fn cell(s: &str) -> String {
    if s.contains([',', '"', '\n', '\r']) {
        format!("\"{}\"", s.replace('"', "\"\""))
    } else {
        s.to_string()
    }
}

/// `DataFrame.to_csv(index=False)`: shortest float repr, `True`/`False`, empty for missing,
/// datetimes as dates when every value is midnight.
fn csv(f: &Frame) -> String {
    let b = f.batch();
    let n = b.num_rows();
    let mut cols: Vec<Vec<String>> = Vec::new();
    for a in b.columns() {
        let col: Vec<String> = match a.data_type() {
            DataType::Float64 => {
                let v = a.as_primitive::<Float64Type>();
                (0..n)
                    .map(|i| {
                        if v.is_null(i) || v.value(i).is_nan() {
                            String::new()
                        } else {
                            py_repr(v.value(i))
                        }
                    })
                    .collect()
            }
            DataType::Int64 => {
                let v = a.as_primitive::<Int64Type>();
                (0..n)
                    .map(|i| {
                        if v.is_null(i) {
                            String::new()
                        } else {
                            v.value(i).to_string()
                        }
                    })
                    .collect()
            }
            DataType::Boolean => {
                let v = a.as_boolean();
                (0..n)
                    .map(|i| match (v.is_null(i), v.value(i)) {
                        (true, _) => String::new(),
                        (_, true) => "True".into(),
                        _ => "False".into(),
                    })
                    .collect()
            }
            DataType::Utf8 | DataType::LargeUtf8 => {
                let v = cast(a, &DataType::Utf8).unwrap();
                let v = v.as_string::<i32>();
                (0..n)
                    .map(|i| {
                        if v.is_null(i) {
                            String::new()
                        } else {
                            cell(v.value(i))
                        }
                    })
                    .collect()
            }
            DataType::Timestamp(_, _) => {
                let v = cast(a, &DataType::Timestamp(TimeUnit::Microsecond, None)).unwrap();
                let v = v.as_primitive::<arrow::datatypes::TimestampMicrosecondType>();
                const US: i64 = 86_400_000_000;
                let midnight = (0..n).all(|i| v.is_null(i) || v.value(i).rem_euclid(US) == 0);
                (0..n)
                    .map(|i| {
                        if v.is_null(i) {
                            return String::new();
                        }
                        let (d, us) = (v.value(i).div_euclid(US) as Day, v.value(i).rem_euclid(US));
                        if midnight {
                            iso(d)
                        } else {
                            let s = us / 1_000_000;
                            format!(
                                "{} {:02}:{:02}:{:02}",
                                iso(d),
                                s / 3600,
                                s / 60 % 60,
                                s % 60
                            )
                        }
                    })
                    .collect()
            }
            t => panic!("csv: unsupported column type {t}"),
        };
        cols.push(col);
    }
    let mut out = b
        .schema()
        .fields()
        .iter()
        .map(|f| cell(f.name()))
        .collect::<Vec<_>>()
        .join(",")
        + "\n";
    for i in 0..n {
        out += &cols
            .iter()
            .map(|c| c[i].as_str())
            .collect::<Vec<_>>()
            .join(",");
        out.push('\n');
    }
    out
}

/// `json.dumps(indent=2)`: two-space indent, ASCII-escaped, Python float repr.
fn python_json(v: &Value) -> String {
    fn go(v: &Value, depth: usize, out: &mut String) {
        let pad = |d: usize| "  ".repeat(d);
        match v {
            Value::Null => out.push_str("null"),
            Value::Bool(b) => out.push_str(if *b { "true" } else { "false" }),
            Value::Number(n) => match n.as_i64() {
                Some(i) if !n.is_f64() => out.push_str(&i.to_string()),
                _ => out.push_str(&py_repr(n.as_f64().unwrap())),
            },
            Value::String(s) => {
                out.push('"');
                for ch in s.chars() {
                    match ch {
                        '"' => out.push_str("\\\""),
                        '\\' => out.push_str("\\\\"),
                        '\n' => out.push_str("\\n"),
                        '\r' => out.push_str("\\r"),
                        '\t' => out.push_str("\\t"),
                        '\u{8}' => out.push_str("\\b"),
                        '\u{c}' => out.push_str("\\f"),
                        c if (c as u32) < 0x20 || (c as u32) > 0x7f => {
                            let mut buf = [0u16; 2];
                            for u in c.encode_utf16(&mut buf) {
                                let _ = write!(out, "\\u{u:04x}");
                            }
                        }
                        c => out.push(c),
                    }
                }
                out.push('"');
            }
            Value::Array(a) if a.is_empty() => out.push_str("[]"),
            Value::Object(o) if o.is_empty() => out.push_str("{}"),
            Value::Array(a) => {
                out.push_str("[\n");
                for (k, x) in a.iter().enumerate() {
                    out.push_str(&pad(depth + 1));
                    go(x, depth + 1, out);
                    out.push_str(if k + 1 < a.len() { ",\n" } else { "\n" });
                }
                out.push_str(&pad(depth));
                out.push(']');
            }
            Value::Object(o) => {
                out.push_str("{\n");
                for (k, (name, x)) in o.iter().enumerate() {
                    out.push_str(&pad(depth + 1));
                    go(&Value::String(name.clone()), depth + 1, out);
                    out.push_str(": ");
                    go(x, depth + 1, out);
                    out.push_str(if k + 1 < o.len() { ",\n" } else { "\n" });
                }
                out.push_str(&pad(depth));
                out.push('}');
            }
        }
    }
    let mut out = String::new();
    go(v, 0, &mut out);
    out
}
