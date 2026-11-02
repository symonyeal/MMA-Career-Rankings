//! The published boards: All-time, elite-tested Prime and Current, each per
//! gender, plus the integrity ledger and the integrity-discounted board.
//!
//! A board ranks who clears its evidence gates and withholds everyone else
//! with a status naming the gate failed. Ranked rows come first by score
//! (rank = min rank), then withheld rows in ratings_current order. Men's and
//! women's bouts are disjoint graph components, so each board is built per
//! gender (`divisions::female`; a blank gender is not female).

use std::collections::{BTreeMap, HashMap};

use crate::appearances::Appearance;
use crate::bouts::Bout;
use crate::divisions::female;
use crate::frame::{Day, Frame, Table};
use crate::history::History;
use crate::layoff::Layoff;
use crate::stats::{kahan_mean, psum};

/// `SUSTAINED_PEAK_MIN_FIGHTS`: the rating-period floor of every board.
pub const MIN_PERIODS: i64 = 13;
/// `CONTENDER_LINE_MU`.
pub const CONTENDER: f64 = 1750.0;
/// `MIN_OPPONENT_UFC_BOUTS`: an opponent's tested UFC record, and the Current board's UFC-bout floor.
const MIN_OPPONENT_UFC_BOUTS: usize = 8;
/// `MIN_QUALITY_WINS`.
const MIN_QUALITY_WINS: usize = 4;
/// `CURRENT_WINDOW_MONTHS`.
const CURRENT_MONTHS: f64 = 18.0;
/// `round(JULIAN_YEAR_DAYS · ELITE_DECADE_SPAN_YEARS)`.
const DECADE_DAYS: Day = 3652;
/// `INTEGRITY_PENALTY_SCALE`: Elo removed per discounted win, times the sleeve's relative severity.
const PENALTY_SCALE: f64 = 250.0;
/// Integrity reasons: name, factor, ledger label.
const REASONS: [(&str, f64, &str); 3] = [
    ("ped", 0.90, "PED-confirmed win"),
    ("dq", 0.96, "win by disqualification"),
    ("missed_weight", 0.94, "won after missing weight"),
];

pub const UNRANKED_AT_FLOOR: &str = "unranked (no year above the bar)";

/// The ratings_current columns the boards read, by row.
pub struct Current {
    pub fighter: Vec<String>,
    pub gender: Vec<String>,
    pub periods: Vec<i64>,
    pub legacy: Vec<f64>,
    pub title_wins: Vec<f64>,
    pub title_defenses: Vec<f64>,
    pub ufc_bouts: Vec<f64>,
    pub current_score: Vec<f64>,
    pub months_since_ufc: Vec<f64>,
    pub mu_whr: Vec<f64>,
}

impl Current {
    pub fn new(c: &Frame) -> Current {
        Current {
            fighter: c.str("fighter"),
            gender: c.str("gender"),
            periods: c.i64("rating_periods"),
            legacy: c.f64("public_legacy_score"),
            title_wins: c.f64("public_legacy_title_wins"),
            title_defenses: c.f64("public_legacy_title_defenses"),
            ufc_bouts: c.f64("public_legacy_ufc_bouts"),
            current_score: c.f64("current_score"),
            months_since_ufc: c.f64("months_since_ufc"),
            mu_whr: c.f64("mu_whr"),
        }
    }

    /// Row indices of one gender's population, in table order.
    pub fn population(&self, women: bool) -> Vec<usize> {
        (0..self.fighter.len())
            .filter(|&i| female(&self.gender[i]) == women)
            .collect()
    }

    /// `public_legacy_eligibility_override`: a proven UFC title resume ranks before the period floor.
    fn override_(&self, i: usize) -> bool {
        let z = |x: f64| if x.is_nan() { 0.0 } else { x };
        let (w, d) = (z(self.title_wins[i]), z(self.title_defenses[i]));
        self.periods[i] >= 8
            && z(self.ufc_bouts[i]) >= 8.0
            && z(self.legacy[i]) > 0.0
            && (w >= 3.0 || (w >= 2.0 && d >= 1.0))
    }
}

/// Gates of `completeness_gated_board`, each optional.
#[derive(Default)]
struct Gate<'a> {
    override_: Option<&'a [bool]>,
    /// Evidence count per row, its floor and its label.
    tested: Option<(&'a [f64], usize, &'a str)>,
    /// Months idle per row and its ceiling.
    idle: Option<&'a [f64]>,
    floor: Option<f64>,
}

/// A gated board over a population: rows (positions in the population) in board order.
pub struct Board {
    pub row: Vec<usize>,
    pub rank: Vec<Option<i64>>,
    pub status: Vec<String>,
}

impl Board {
    pub fn ranked(&self) -> impl Iterator<Item = (usize, i64)> + '_ {
        self.row
            .iter()
            .zip(&self.rank)
            .filter_map(|(&r, k)| k.map(|k| (r, k)))
    }
}

fn gate(score: &[f64], periods: &[i64], g: &Gate) -> Board {
    let n = score.len();
    let mut status: Vec<String> = vec!["ranked".into(); n];
    for i in 0..n {
        let eligible = periods[i] >= MIN_PERIODS || g.override_.is_some_and(|o| o[i]);
        if !eligible {
            status[i] =
                format!("insufficient observed history to rank (< {MIN_PERIODS} rating periods)");
        }
        if score[i].is_nan() {
            status[i] = "insufficient observed history to rank (no qualifying period score)".into();
        }
        let ranked = |s: &String| s == "ranked";
        if let Some((w, k, label)) = g.tested {
            if ranked(&status[i]) && (w[i].is_nan() || w[i] < k as f64) {
                status[i] = format!("insufficient proven record to rank (< {k} {label})");
            }
        }
        if let Some(m) = g.idle {
            if ranked(&status[i]) && (m[i].is_nan() || m[i] > CURRENT_MONTHS) {
                status[i] = format!("not currently active enough to rank (last UFC bout over {CURRENT_MONTHS} months ago)");
            }
        }
        if let Some(f) = g.floor {
            if ranked(&status[i]) && !score[i].is_nan() && score[i] <= f {
                status[i] = UNRANKED_AT_FLOOR.into();
            }
        }
    }
    let mut ranked: Vec<usize> = (0..n).filter(|&i| status[i] == "ranked").collect();
    ranked.sort_by(|&a, &b| score[b].total_cmp(&score[a]));
    let mut rank = Vec::with_capacity(n);
    for (p, &i) in ranked.iter().enumerate() {
        let first = ranked[..p].partition_point(|&j| score[j] > score[i]);
        rank.push(Some(first as i64 + 1));
    }
    let withheld: Vec<usize> = (0..n).filter(|&i| status[i] != "ranked").collect();
    rank.extend(withheld.iter().map(|_| None));
    let row: Vec<usize> = ranked.into_iter().chain(withheld).collect();
    let status = row.iter().map(|&i| status[i].clone()).collect();
    Board { row, rank, status }
}

/// Each fighter's best decade of beating tested contenders (`_elite_decade_map`, `best_elite_decade`).
#[derive(Clone, Copy, Debug)]
pub struct Decade {
    pub wins: usize,
    pub level: f64,
    pub start: Day,
    pub end: Day,
}

/// Opponent strength is the opponent's era rating at their last appearance strictly before the bout, less the
/// layoff charge; a win qualifies when that clears the contender line and the opponent has a tested UFC record.
/// The window holding the most qualifying wins wins, ties to the higher mean of the fighter's daily ratings in it.
pub fn decades(
    appearances: &[Appearance],
    history: &History,
    staged: &[Bout],
) -> HashMap<String, Decade> {
    let mut ufc: HashMap<&str, usize> = HashMap::new();
    for b in staged
        .iter()
        .filter(|b| (b.corpus == "ufc" || b.corpus == "pre_unified") && b.model)
    {
        *ufc.entry(&b.a).or_default() += 1;
        *ufc.entry(&b.b).or_default() += 1;
    }
    let layoff = Layoff::new(history);
    let mut wins: BTreeMap<&str, Vec<Day>> = BTreeMap::new();
    for a in appearances {
        if !a.won || ufc.get(a.opponent.as_str()).copied().unwrap_or(0) < MIN_OPPONENT_UFC_BOUTS {
            continue;
        }
        let Some(r) = history.before(&a.opponent, a.day) else {
            continue;
        };
        if layoff.price(r.era, &a.opponent, a.day) >= CONTENDER {
            wins.entry(&a.fighter).or_default().push(a.day);
        }
    }
    let mut out = HashMap::new();
    for (fighter, mut dates) in wins {
        dates.sort();
        // The fighter's own daily mean era ratings, in date order.
        let rows = history.of(fighter);
        let mut own: Vec<(Day, f64)> = Vec::new();
        let mut i = 0;
        while i < rows.len() {
            let j = i + rows[i..]
                .iter()
                .take_while(|r| r.day == rows[i].day)
                .count();
            own.push((
                rows[i].day,
                kahan_mean(&rows[i..j].iter().map(|r| r.era).collect::<Vec<_>>()),
            ));
            i = j;
        }
        let mut best: Option<(usize, f64, Day)> = None;
        for &start in &dates {
            let end = start + DECADE_DAYS;
            let c = dates.partition_point(|&d| d <= end) - dates.partition_point(|&d| d < start);
            let mu: Vec<f64> = own
                .iter()
                .filter(|(d, _)| *d >= start && *d <= end)
                .map(|p| p.1)
                .collect();
            let level = if mu.is_empty() {
                -1e18
            } else {
                psum(&mu) / mu.len() as f64
            };
            if best.is_none_or(|(bc, bl, _)| (c, level) > (bc, bl)) {
                best = Some((c, level, start));
            }
        }
        let (wins, level, start) = best.unwrap();
        out.insert(
            fighter.to_string(),
            Decade {
                wins,
                level: if level > -1e17 { level } else { f64::NAN },
                start,
                end: start + DECADE_DAYS,
            },
        );
    }
    out
}

/// One integrity-ledger row: a winner's flagged appearance.
pub struct Debit {
    pub fighter: String,
    pub url: String,
    pub day: Day,
    pub event: String,
    pub opponent: String,
    pub reason: &'static str,
    pub detail: String,
    pub weight: f64,
    pub pct: f64,
}

/// `integrity_ledger`: one row per flagged appearance, sorted by (fighter, date, reason).
/// `integrity` is integrity_appearances; `rated` supplies each bout's date, names and citations.
pub fn ledger(integrity: &Frame, rated: &[Bout]) -> Vec<Debit> {
    let mut meta: HashMap<&str, &Bout> = HashMap::new();
    for b in rated {
        meta.entry(&b.url).or_insert(b);
    }
    let (url, fighter, weight) = (
        integrity.str("fight_url"),
        integrity.str("fighter"),
        integrity.f64("integrity_weight"),
    );
    let mut out = Vec::new();
    for (reason, factor, label) in REASONS {
        let f = integrity.f64(&format!("integrity_factor_{reason}"));
        for i in (0..f.len()).filter(|&i| !f[i].is_nan() && f[i] < 1.0) {
            let b = meta[url[i].as_str()];
            let extra = match reason {
                "ped" if !b.ped_detail.is_empty() => format!(" — {}", b.ped_detail),
                "missed_weight" if !b.weight_class.is_empty() => format!(" ({})", b.weight_class),
                _ => String::new(),
            };
            out.push(Debit {
                fighter: fighter[i].clone(),
                url: url[i].clone(),
                day: b.day,
                event: b.event.clone(),
                opponent: if fighter[i] == b.a {
                    b.b.clone()
                } else {
                    b.a.clone()
                },
                reason,
                detail: format!("{label}{extra}"),
                weight: weight[i],
                pct: 100.0 * (1.0 - factor),
            });
        }
    }
    out.sort_by(|x, y| (&x.fighter, x.day, x.reason).cmp(&(&y.fighter, y.day, y.reason)));
    out
}

pub struct Boards {
    /// All-time (`completeness_gated_board`), elite Prime, Current; index 0 men, 1 women.
    pub all_time: [Table; 2],
    pub prime: [Table; 2],
    pub current: [Table; 2],
    pub integrity_ledger: Table,
    pub integrity_board: Table,
    /// Ranked positions, fighter → rank, per gender.
    pub all_time_rank: [HashMap<String, i64>; 2],
    pub prime_rank: [HashMap<String, i64>; 2],
    /// Ranked rows in board order: (fighter, rank), per gender.
    pub all_time_top: [Vec<(String, i64)>; 2],
    pub prime_top: [Vec<(String, i64)>; 2],
    pub current_top: [Vec<(String, i64, f64)>; 2],
    pub decades: HashMap<String, Decade>,
    pub prime_ranked: [usize; 2],
}

pub fn build(
    current: &Frame,
    history: &History,
    rated: &[Bout],
    staged: &[Bout],
    integrity: &Frame,
    appearances: &[Appearance],
) -> Boards {
    let c = Current::new(current);
    let decades = decades(appearances, history, staged);
    let pick = |rows: &[usize], v: &[f64]| rows.iter().map(|&i| v[i]).collect::<Vec<f64>>();
    let names = |rows: &[usize], b: &Board| {
        b.row
            .iter()
            .map(|&r| c.fighter[rows[r]].clone())
            .collect::<Vec<_>>()
    };
    let mut all_time = Vec::new();
    let mut prime = Vec::new();
    let mut cur = Vec::new();
    let (mut all_time_rank, mut prime_rank, mut all_time_top, mut prime_top, mut current_top) =
        (Vec::new(), Vec::new(), Vec::new(), Vec::new(), Vec::new());
    let mut prime_ranked = [0, 0];
    for (k, women) in [false, true].into_iter().enumerate() {
        let rows = c.population(women);
        let periods: Vec<i64> = rows.iter().map(|&i| c.periods[i]).collect();
        let ranked_list = |b: &Board| {
            b.ranked()
                .map(|(r, k)| (c.fighter[rows[r]].clone(), k))
                .collect::<Vec<_>>()
        };

        // All-time.
        let score = pick(&rows, &c.legacy);
        let over: Vec<bool> = rows.iter().map(|&i| c.override_(i)).collect();
        let b = gate(
            &score,
            &periods,
            &Gate {
                override_: Some(&over),
                floor: Some(0.0),
                ..Gate::default()
            },
        );
        let at = |v: &[f64]| b.row.iter().map(|&r| v[r]).collect::<Vec<_>>();
        all_time.push(
            Table::default()
                .opt_i64("rank", &b.rank)
                .str("fighter", &names(&rows, &b))
                .f64("public_legacy_score", &at(&score))
                .str("status", &b.status)
                .i64(
                    "rating_periods",
                    &b.row.iter().map(|&r| periods[r]).collect::<Vec<_>>(),
                )
                .bool(
                    "eligibility_override",
                    &b.row.iter().map(|&r| over[r]).collect::<Vec<_>>(),
                ),
        );
        let top = ranked_list(&b);
        all_time_rank.push(top.iter().cloned().collect::<HashMap<_, _>>());
        all_time_top.push(top);

        // Elite-tested Prime: the decade level gates, elite-win mass ranks, anchored at the weakest qualifier.
        let d: Vec<Option<&Decade>> = rows.iter().map(|&i| decades.get(&c.fighter[i])).collect();
        let level: Vec<f64> = d.iter().map(|x| x.map_or(f64::NAN, |x| x.level)).collect();
        let wins: Vec<f64> = d
            .iter()
            .map(|x| x.map_or(f64::NAN, |x| x.wins as f64))
            .collect();
        let tested = Some((&wins[..], MIN_QUALITY_WINS, "wins over tested contenders"));
        let g = gate(
            &level,
            &periods,
            &Gate {
                tested,
                ..Gate::default()
            },
        );
        let anchor = g
            .ranked()
            .map(|(r, _)| level[r])
            .filter(|x| !x.is_nan())
            .fold(f64::INFINITY, f64::min);
        // `clip(lower=0)` keeps a missing level missing.
        let mass: Vec<f64> = (0..rows.len())
            .map(|r| {
                if level[r].is_nan() {
                    f64::NAN
                } else {
                    wins[r].max(0.0) * (level[r] - anchor).max(0.0)
                }
            })
            .collect();
        let b = gate(
            &mass,
            &periods,
            &Gate {
                tested,
                ..Gate::default()
            },
        );
        let at = |v: &[f64]| b.row.iter().map(|&r| v[r]).collect::<Vec<_>>();
        let day = |f: fn(&Decade) -> Day| b.row.iter().map(|&r| d[r].map(f)).collect::<Vec<_>>();
        prime.push(
            Table::default()
                .opt_i64("rank", &b.rank)
                .str("fighter", &names(&rows, &b))
                .f64("elite_prime_score", &at(&mass))
                .str("status", &b.status)
                .i64(
                    "rating_periods",
                    &b.row.iter().map(|&r| periods[r]).collect::<Vec<_>>(),
                )
                .f64("tested_opponent_wins", &at(&wins))
                .f64("elite_level", &at(&level))
                .day("elite_window_start", &day(|x| x.start))
                .day("elite_window_end", &day(|x| x.end)),
        );
        let top = ranked_list(&b);
        prime_ranked[k] = top.len();
        prime_rank.push(top.iter().cloned().collect::<HashMap<_, _>>());
        prime_top.push(top);

        // Current: 13 periods, 8 UFC bouts, a UFC bout inside 18 months, a score above zero.
        let score = pick(&rows, &c.current_score);
        let (bouts, idle) = (pick(&rows, &c.ufc_bouts), pick(&rows, &c.months_since_ufc));
        let gt = Gate {
            tested: Some((&bouts, MIN_OPPONENT_UFC_BOUTS, "UFC bouts")),
            idle: Some(&idle),
            floor: Some(0.0),
            ..Gate::default()
        };
        let b = gate(&score, &periods, &gt);
        let at = |v: &[f64]| b.row.iter().map(|&r| v[r]).collect::<Vec<_>>();
        cur.push(
            Table::default()
                .opt_i64("rank", &b.rank)
                .str("fighter", &names(&rows, &b))
                .f64("current_board_score", &at(&score))
                .str("status", &b.status)
                .i64(
                    "rating_periods",
                    &b.row.iter().map(|&r| periods[r]).collect::<Vec<_>>(),
                )
                .i64(
                    "tested_opponent_wins",
                    &at(&bouts).iter().map(|&x| x as i64).collect::<Vec<_>>(),
                )
                .f64("months_inactive", &at(&idle)),
        );
        current_top.push(
            b.ranked()
                .map(|(r, k)| (c.fighter[rows[r]].clone(), k, score[r]))
                .collect(),
        );
    }

    let debits = ledger(integrity, rated);
    let integrity_ledger = Table::default()
        .str(
            "fighter",
            &debits.iter().map(|x| &x.fighter).collect::<Vec<_>>(),
        )
        .str(
            "fight_url",
            &debits.iter().map(|x| &x.url).collect::<Vec<_>>(),
        )
        .day(
            "event_date",
            &debits.iter().map(|x| Some(x.day)).collect::<Vec<_>>(),
        )
        .str(
            "event_name",
            &debits.iter().map(|x| &x.event).collect::<Vec<_>>(),
        )
        .str(
            "opponent",
            &debits.iter().map(|x| &x.opponent).collect::<Vec<_>>(),
        )
        .str(
            "reason",
            &debits.iter().map(|x| x.reason).collect::<Vec<_>>(),
        )
        .str(
            "detail",
            &debits.iter().map(|x| &x.detail).collect::<Vec<_>>(),
        )
        .f64(
            "integrity_weight",
            &debits.iter().map(|x| x.weight).collect::<Vec<_>>(),
        )
        .f64(
            "discount_pct",
            &debits.iter().map(|x| x.pct).collect::<Vec<_>>(),
        );
    let integrity_board = discounted(&c, &debits);

    let two = |v: Vec<Table>| -> [Table; 2] { v.try_into().ok().unwrap() };
    let two_m =
        |v: Vec<HashMap<String, i64>>| -> [HashMap<String, i64>; 2] { v.try_into().ok().unwrap() };
    Boards {
        all_time: two(all_time),
        prime: two(prime),
        current: two(cur),
        integrity_ledger,
        integrity_board,
        all_time_rank: two_m(all_time_rank),
        prime_rank: two_m(prime_rank),
        all_time_top: all_time_top.try_into().ok().unwrap(),
        prime_top: prime_top.try_into().ok().unwrap(),
        current_top: current_top.try_into().ok().unwrap(),
        decades,
        prime_ranked,
    }
}

/// `integrity_discounted_board`: mu_whr less a stated debit per flagged win, the debit falling on the winner alone.
fn discounted(c: &Current, debits: &[Debit]) -> Table {
    let mut n: HashMap<(&str, &str), i64> = HashMap::new();
    for d in debits {
        *n.entry((&d.fighter, d.reason)).or_default() += 1;
    }
    let rows: Vec<usize> = (0..c.fighter.len())
        .filter(|&i| !c.mu_whr[i].is_nan())
        .collect();
    let count = |i: usize, r: &str| n.get(&(c.fighter[i].as_str(), r)).copied().unwrap_or(0);
    let cost: Vec<f64> = rows
        .iter()
        .map(|&i| {
            REASONS.iter().fold(0.0, |s, (r, f, _)| {
                s + count(i, r) as f64 * ((1.0 - f) * PENALTY_SCALE)
            })
        })
        .collect();
    let rating: Vec<f64> = rows
        .iter()
        .zip(&cost)
        .map(|(&i, k)| c.mu_whr[i] - k)
        .collect();
    let mu: Vec<f64> = rows.iter().map(|&i| c.mu_whr[i]).collect();
    let mut order: Vec<usize> = (0..rows.len()).collect();
    // pandas used an unstable sort here; tied ratings keep ratings_current order.
    order.sort_by(|&a, &b| rating[b].total_cmp(&rating[a]));
    let mut sorted = rating.clone();
    sorted.sort_by(|a, b| b.total_cmp(a));
    let rank: Vec<i64> = order
        .iter()
        .map(|&j| sorted.partition_point(|&y| y > rating[j]) as i64 + 1)
        .collect();
    let undiscounted: Vec<f64> = {
        let mut s = mu.clone();
        s.sort_by(|a, b| b.total_cmp(a));
        order
            .iter()
            .map(|&j| s.partition_point(|&y| y > mu[j]) as f64 + 1.0)
            .collect()
    };
    let by = |r: &str| {
        order
            .iter()
            .map(|&j| count(rows[j], r))
            .collect::<Vec<i64>>()
    };
    let (p, d, m) = (by("ped"), by("dq"), by("missed_weight"));
    Table::default()
        .i64("rank", &rank)
        .str(
            "fighter",
            &order
                .iter()
                .map(|&j| &c.fighter[rows[j]])
                .collect::<Vec<_>>(),
        )
        .f64(
            "integrity_discounted_rating",
            &order.iter().map(|&j| rating[j]).collect::<Vec<_>>(),
        )
        .f64("mu_whr", &order.iter().map(|&j| mu[j]).collect::<Vec<_>>())
        .f64("undiscounted_rank", &undiscounted)
        .f64(
            "rank_change",
            &rank
                .iter()
                .zip(&undiscounted)
                .map(|(r, u)| *r as f64 - u)
                .collect::<Vec<_>>(),
        )
        .f64(
            "integrity_cost",
            &order.iter().map(|&j| cost[j]).collect::<Vec<_>>(),
        )
        .i64(
            "discounted_fights",
            &(0..order.len())
                .map(|i| p[i] + d[i] + m[i])
                .collect::<Vec<_>>(),
        )
        .i64("ped_discounted_fights", &p)
        .i64("dq_discounted_fights", &d)
        .i64("missed_weight_discounted_fights", &m)
}
