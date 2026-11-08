//! `mma <snapshot>` rebuilds every published output from a staged snapshot;
//! `mma heldout <snapshot>` runs the held-out test of the published WHR against its candidate;
//! `mma stamp` points site/index.html at the current asset hashes.
//!
//! The snapshot is `<root>/data/snapshots/<date>`, written by the Python staging. Text outputs use LF.

use std::collections::{HashMap, HashSet};
use std::path::Path;

use mma_rankings::error::Error;
use mma_rankings::frame::{read_text, write_text, Frame, Table};
use mma_rankings::layoff::Layoff;
use mma_rankings::legacy::Pricing;
use mma_rankings::names::Names;
use mma_rankings::orgs::Rules;
use mma_rankings::publish::Release;
use mma_rankings::{
    age, appearances, audit, boards, bouts, classes, current, dominance, era, figures, forecast,
    glicko, heldout, integrity, legacy, narrative, publish, release, roster, site, skill, whr,
};
use serde_json::json;
use sha2::{Digest, Sha256};

/// Site assets stamped into index.html by content hash.
const ASSETS: [&str; 3] = ["style.css", "data.js", "app.js"];
/// ratings_current columns in published order.
const CURRENT: [&str; 71] = [
    "fighter",
    "mu_canonical",
    "phi_canonical",
    "sigma_canonical",
    "mu_method",
    "phi_method",
    "sigma_method",
    "last_event_date",
    "rating_periods",
    "whr_last_event_date",
    "mu_whr",
    "mu_whr_age_activity_adjusted",
    "whr_age_inactivity_adjustment",
    "wins",
    "losses",
    "draws",
    "recent_division",
    "gender",
    "symon_prime_score",
    "symon_prime_raw_mean",
    "symon_prime_shrinkage",
    "symon_prime_window_fights",
    "symon_prime_window_start",
    "symon_prime_window_end",
    "symon_prime_within_var",
    "symon_prime_sampling_var",
    "last_recorded_event_date",
    "months_inactive",
    "career_division",
    "career_division_reliability",
    "current_division",
    "current_division_reliability",
    "symon_career_rank",
    "symon_career_skill_mass",
    "symon_career_active_years",
    "symon_career_contributing_years",
    "symon_career_peak_year_excess",
    "symon_career_mean_year_excess",
    "symon_career_first_year",
    "symon_career_last_year",
    "public_legacy_score",
    "public_legacy_skill_mass",
    "public_legacy_skill_score",
    "public_legacy_exposure_factor",
    "public_legacy_title_score",
    "public_legacy_title_quality",
    "public_legacy_qualifying_title_wins",
    "public_legacy_resume_score",
    "public_legacy_resume_quality",
    "public_legacy_contender_wins",
    "public_legacy_title_appearances",
    "public_legacy_title_wins",
    "public_legacy_title_defenses",
    "public_legacy_title_win_divisions",
    "public_legacy_multi_division_bonus",
    "public_legacy_ufc_bouts",
    "public_legacy_top_org_bouts",
    "public_legacy_unknown_org_bouts",
    "current_title_score",
    "current_title_wins",
    "current_resume_score",
    "current_contender_wins",
    "current_best_win_mu",
    "current_skill_level",
    "current_skill_score",
    "current_score",
    "last_ufc_event_date",
    "months_since_ufc",
    "ped_confirmed_fights",
    "dq_wins",
    "missed_weight_wins",
];
/// Whole-career coverage counts fighters with at least this many UFC bouts.
const COVERAGE_MIN_UFC: i64 = 3;

/// Rows of `f` reordered to `order` by `fighter`, without the key; absent fighters read null.
fn align(f: &Frame, order: &[String]) -> Result<Frame, Error> {
    let mut at = HashMap::new();
    for (i, fighter) in f.str("fighter")?.into_iter().enumerate() {
        assert!(!fighter.is_empty(), "stage has an empty fighter key");
        assert!(
            at.insert(fighter.clone(), i).is_none(),
            "duplicate stage fighter: {fighter}"
        );
    }
    let unique: HashSet<&String> = order.iter().collect();
    assert_eq!(unique.len(), order.len(), "duplicate target fighter keys");
    let rest: Vec<String> = f.names().into_iter().filter(|c| c != "fighter").collect();
    let rest: Vec<&str> = rest.iter().map(String::as_str).collect();
    f.take(&order.iter().map(|k| at.get(k).copied()).collect::<Vec<_>>())?
        .select(&rest)
}

fn stamp(site: &Path) -> Result<(), Error> {
    let p = site.join("index.html");
    let mut h = read_text(&p)?;
    for a in ASSETS {
        let v = &format!("{:x}", Sha256::digest(read_text(&site.join(a))?.as_bytes()))[..10];
        let re = regex::Regex::new(&format!(r#""{}(\?v=\w+)?""#, regex::escape(a))).unwrap();
        h = re
            .replace_all(&h, format!("\"{a}?v={v}\"").as_str())
            .into_owned();
    }
    write_text(&p, &h)
}

fn build(s: &Path, root: &Path) -> Result<(), Error> {
    let names = Names::load(root)?;
    let prepared = bouts::prepared(s, root, &names)?;
    let rated = bouts::rated(&prepared);
    let staged = bouts::staged(s)?;
    let births = age::births(s)?;

    // Ratings: Glicko streams, WHR path, roster facts; ratings_current is ordered by mu_canonical.
    let g = glicko::run(&rated);
    let w = whr::run(&rated, &births);
    let whr_shift = shift_bound(w.shift);
    let mut history = w.history;
    let apps = mma_rankings::perf::appearances(&rated);
    let max = rated
        .iter()
        .map(|b| b.day)
        .max()
        .ok_or_else(|| Error::at(s.display(), "no rated bouts"))?;
    let base = g.current().frame();
    let (fighter, mu) = (base.str("fighter")?, base.f64("mu_canonical")?);
    let mut ix: Vec<usize> = (0..base.len()).collect();
    ix.sort_by(|&i, &j| {
        mu[j]
            .total_cmp(&mu[i])
            .then_with(|| fighter[i].cmp(&fighter[j]))
    });
    let base = base.take(&ix.iter().map(|&i| Some(i)).collect::<Vec<_>>())?;
    let order = base.str("fighter")?;
    let roster = align(
        &roster::columns(&prepared, &rated, &history, &apps, max)?,
        &order,
    )?;
    let mut cur = base.hstack(&[&align(&w.current.frame(), &order)?, &roster]);
    let female: HashSet<String> = cur
        .str("fighter")?
        .into_iter()
        .zip(cur.str("gender")?)
        .filter(|(_, g)| g == "F")
        .map(|(f, _)| f)
        .collect();
    era::apply(&mut history, |f| female.contains(f));

    // Scores: Prime and career skill, All-time legacy, Current.
    let layoff = Layoff::new(&history);
    let rules = Rules::load(root)?;
    let ctx = rules.context(&rated);
    let era_p = Pricing {
        h: &history,
        rating: |r| r.era,
        layoff: &layoff,
    };
    let mu_p = Pricing {
        h: &history,
        rating: |r| r.mu,
        layoff: &layoff,
    };
    let pools = skill::pools(&cur)?;
    let years = skill::years(&history, |r| r.era, &pools);
    cur = cur.hstack(&[&align(&skill::prime(&history, &cur)?.frame(), &order)?]);
    cur = cur.hstack(&[&align(&skill::career(&years).frame(), &order)?]);
    cur = cur.hstack(&[&align(
        &legacy::score(&cur, &pools, &apps, &rated, &era_p, &rules)?.frame(),
        &order,
    )?]);
    cur = cur.hstack(&[&align(
        &current::score(&cur, &pools, &rated, &prepared, &mu_p, &ctx)?.frame(),
        &order,
    )?]);
    let cur = cur.select(&CURRENT)?;
    cur.write(&s.join("ratings_current.parquet"))?;
    Table::default()
        .str(
            "fighter",
            &history
                .rows()
                .iter()
                .map(|r| r.fighter.as_str())
                .collect::<Vec<_>>(),
        )
        .day(
            "event_date",
            &history
                .rows()
                .iter()
                .map(|r| Some(r.day))
                .collect::<Vec<_>>(),
        )
        .str(
            "event_name",
            &history
                .rows()
                .iter()
                .map(|r| r.event.as_str())
                .collect::<Vec<_>>(),
        )
        .f64(
            "mu_whr",
            &history.rows().iter().map(|r| r.mu).collect::<Vec<_>>(),
        )
        .f64(
            "mu_era",
            &history.rows().iter().map(|r| r.era).collect::<Vec<_>>(),
        )
        .write(&s.join("ratings_history_whr.parquet"))?;
    appearances::write(s, &apps)?;
    let integ = integrity::appearances(&rated).frame();
    integ.write(&s.join("integrity_appearances.parquet"))?;
    let dom = dominance::fighters(s, &rated, &names)?.frame();
    dom.write(&s.join("fighter_dominance.parquet"))?;
    let cal = glicko::calibration(&g, &rated).frame();
    cal.write(&s.join("calibration_residuals.parquet"))?;

    // Boards and the class ledger.
    let b = boards::build(&cur, &history, &rated, &staged, &integ, &apps)?;
    let fr = |t: &Table| t.clone().frame();
    let (at, pr, cu) = (
        b.all_time.each_ref().map(fr),
        b.prime.each_ref().map(fr),
        b.current.each_ref().map(fr),
    );
    let (ledger, ib) = (fr(&b.integrity_ledger), fr(&b.integrity_board));
    for (name, f) in [
        ("completeness_gated_board", &at[0]),
        ("completeness_gated_board_women", &at[1]),
        ("prime_elite_board", &pr[0]),
        ("prime_elite_board_women", &pr[1]),
        ("current_board", &cu[0]),
        ("current_board_women", &cu[1]),
        ("integrity_ledger", &ledger),
        ("integrity_discounted_board", &ib),
    ] {
        f.write(&s.join(format!("{name}.parquet")))?;
    }
    let ranked: HashSet<String> = at
        .iter()
        .map(|f| Ok(f.str("fighter")?.into_iter().zip(f.str("status")?)))
        .collect::<Result<Vec<_>, Error>>()?
        .into_iter()
        .flatten()
        .filter(|(_, st)| st == "ranked")
        .map(|(f, _)| f)
        .collect();
    let class = classes::board(&cur, &pools, &apps, &rated, &era_p, &ctx, &years, &ranked)?.frame();
    class.write(&s.join("class_board.parquet"))?;

    // Run record.
    let cov = Frame::read(
        &s.join("career_coverage.parquet"),
        &["ufc_bouts", "whole_career_merged"],
    )?;
    let eligible: Vec<bool> = cov
        .i64("ufc_bouts")?
        .iter()
        .map(|&n| n >= COVERAGE_MIN_UFC)
        .collect();
    let merged = cov
        .bool("whole_career_merged")?
        .iter()
        .zip(&eligible)
        .filter(|(m, e)| **m && **e)
        .count() as i64;
    let eligible = eligible.iter().filter(|e| **e).count() as i64;
    let events: HashSet<(mma_rankings::frame::Day, &str)> =
        rated.iter().map(|b| (b.day, b.event.as_str())).collect();
    let snapshot = s
        .file_name()
        .ok_or_else(|| Error::at(s.display(), "snapshot path has no folder name"))?
        .to_string_lossy()
        .into_owned();
    let run = json!({
        "rated_bouts": rated.len(),
        "birth_dates": births.len(),
        "history_rows": history.rows().len(),
        "whr_final_shift_below": whr_shift,
        "current_fighters": cur.len(),
        "events_processed": events.len(),
        "career_coverage": {"eligible": eligible, "whole_career_merged": merged},
    });
    write_text(
        &s.join("rating_run.json"),
        &(serde_json::to_string_pretty(&run).map_err(|e| Error::at("rating_run.json", e))? + "\n"),
    )?;

    // RANKINGS.md and README.md: generated blocks, then the README narrative.
    let through = prepared
        .iter()
        .map(|b| b.day)
        .max()
        .map(mma_rankings::frame::iso)
        .ok_or_else(|| Error::at(s.display(), "no bouts"))?;
    let rel = Release {
        snapshot: &snapshot,
        through: &through,
        rated_bouts: rated.len() as i64,
        records: staged.len() as i64,
        eligible,
        merged,
    };
    let blocks = publish::blocks(&b, &cur, &history, &class, &rel)?;
    let rk = root.join("RANKINGS.md");
    write_text(
        &rk,
        &publish::splice(&read_text(&rk)?, &blocks, &publish::RANKINGS),
    )?;
    let elite: HashMap<String, f64> = pr[0]
        .str("fighter")?
        .into_iter()
        .zip(pr[0].f64("elite_level")?)
        .collect();
    let mut readme = publish::splice(
        &read_text(&root.join("README.md"))?,
        &blocks,
        &publish::README,
    );
    let figs = figures::values(&cur, &rated, &era_p, &history, &elite)?;
    for (start, text) in figures::paragraphs(&figs) {
        readme = narrative::splice(&readme, start, &text).map_err(|e| Error::at("README.md", e))?;
    }
    write_text(&root.join("README.md"), &readme)?;

    // Site data, then the asset stamp.
    let market = forecast::market(s, &staged, &births)?;
    let data = site::data(&site::Inputs {
        snapshot: s,
        rated_bouts: rated.len() as i64,
        fighters: cur.len() as i64,
        current: &cur,
        all_time: [&at[0], &at[1]],
        prime: [&pr[0], &pr[1]],
        current_board: [&cu[0], &cu[1]],
        class: &class,
        integrity: &ib,
        ledger: &ledger,
        dominance: &dom,
        calib: &cal,
        history: &history,
        apps: &apps,
        staged: &staged,
        names: &names,
        births: &births,
        years: &years,
        market: &market,
    })?;
    write_text(&root.join("site/data.js"), &data)?;
    stamp(&root.join("site"))?;

    // Top-100 audit.
    let cf = Frame::read(
        &s.join("canonical_fights.parquet"),
        &["fighter_a", "fighter_b"],
    )?;
    let canonical: Vec<(String, String)> = cf
        .str("fighter_a")?
        .into_iter()
        .zip(cf.str("fighter_b")?)
        .collect();
    let out = root.join("data/model_tuning/top100-audit");
    std::fs::create_dir_all(&out).map_err(|e| Error::at(out.display(), e))?;
    audit::write(&out, s, &cur, &history, &rated, &canonical, &births)
}

/// The decade above the WHR fit's largest rating change in its last pass, as text ("1e-12"):
/// the change itself is a last-bit quantity, its order of magnitude is the convergence record.
fn shift_bound(shift: f64) -> String {
    let e = (-12..=1)
        .find(|e| shift < format!("1e{e}").parse::<f64>().unwrap())
        .unwrap_or(2);
    format!("1e{e}")
}

fn run() -> Result<(), Error> {
    let a: Vec<String> = std::env::args().skip(1).collect();
    let io = |e: std::io::Error| Error::at("mma", e);
    match a.iter().map(String::as_str).collect::<Vec<_>>().as_slice() {
        ["stamp"] => release::stamp(&std::env::current_dir().map_err(io)?, stamp).map_err(io),
        ["heldout", s] => {
            let s = Path::new(s);
            let root = release::root_of(s).map_err(io)?;
            let names = Names::load(&root)?;
            let rated = bouts::rated(&bouts::prepared(s, &root, &names)?);
            print!(
                "{}",
                heldout::format(&heldout::compare(
                    &rated,
                    &age::births(s)?,
                    heldout::candidate()
                ))
            );
            Ok(())
        }
        [s] => release::build(Path::new(s), build).map_err(io),
        _ => Err(Error::at(
            "usage",
            "mma <snapshot> | mma heldout <snapshot> | mma stamp",
        )),
    }
}

fn main() {
    if let Err(e) = run() {
        eprintln!("{e}");
        std::process::exit(1);
    }
}
