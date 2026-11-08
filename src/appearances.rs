//! Fighter-perspective bout rows: two per rated bout, the a-sides of every
//! bout in bout order first, then the b-sides (`performance_appearances.parquet`).

use std::path::Path;

use crate::error::Error;
use crate::frame::{Day, Table};

#[derive(Clone, Debug, Default)]
pub struct Appearance {
    pub url: String,
    pub day: Day,
    pub event: String,
    pub fighter: String,
    pub opponent: String,
    /// Reported division filled from the career; empty when unknown.
    pub division: String,
    pub won: bool,
    pub draw: bool,
    /// 1 win, ½ draw, 0 otherwise.
    pub score: f64,
    pub method: String,
    /// A real UFC title bout (`is_real_ufc_title_bout`).
    pub title: bool,
    pub interim: bool,
    pub champion: bool,
    pub interim_champion: bool,
}

const FILE: &str = "performance_appearances.parquet";

pub fn write(snapshot: &Path, a: &[Appearance]) -> Result<(), Error> {
    let s = |g: fn(&Appearance) -> &str| a.iter().map(g).collect::<Vec<_>>();
    let b = |g: fn(&Appearance) -> bool| a.iter().map(g).collect::<Vec<_>>();
    Table::default()
        .str("fight_url", &s(|x| &x.url))
        .day(
            "event_date",
            &a.iter().map(|x| Some(x.day)).collect::<Vec<_>>(),
        )
        .str("event_name", &s(|x| &x.event))
        .str("fighter", &s(|x| &x.fighter))
        .str("opponent", &s(|x| &x.opponent))
        .opt_str("division", &s(|x| &x.division))
        .bool("is_winner", &b(|x| x.won))
        .bool("is_draw", &b(|x| x.draw))
        .f64(
            "actual_score",
            &a.iter().map(|x| x.score).collect::<Vec<_>>(),
        )
        .str("method_class", &s(|x| &x.method))
        .bool("is_championship_bout", &b(|x| x.title))
        .bool("is_interim_title_bout", &b(|x| x.interim))
        .bool("fighter_entered_as_champion", &b(|x| x.champion))
        .bool(
            "fighter_entered_as_interim_champion",
            &b(|x| x.interim_champion),
        )
        .write(&snapshot.join(FILE))
}
