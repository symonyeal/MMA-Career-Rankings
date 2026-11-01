//! Fighter-perspective bout rows: two per rated bout, the a-sides of every
//! bout in bout order first, then the b-sides (`performance_appearances.parquet`).

use std::path::Path;

use crate::frame::{Day, Frame, Table};

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

pub fn read(snapshot: &Path) -> Vec<Appearance> {
    let f = Frame::read(&snapshot.join(FILE));
    let s = |c: &str| f.str(c);
    let (url, event, fighter, opponent, division, method) =
        (s("fight_url"), s("event_name"), s("fighter"), s("opponent"), s("division"), s("method_class"));
    let (day, score) = (f.day("event_date"), f.f64("actual_score"));
    let b = |c: &str| f.bool(c);
    let (won, draw, title, interim, champion, interim_champion) = (
        b("is_winner"), b("is_draw"), b("is_championship_bout"), b("is_interim_title_bout"),
        b("fighter_entered_as_champion"), b("fighter_entered_as_interim_champion"),
    );
    (0..f.len())
        .map(|i| Appearance {
            url: url[i].clone(),
            day: day[i].unwrap(),
            event: event[i].clone(),
            fighter: fighter[i].clone(),
            opponent: opponent[i].clone(),
            division: division[i].clone(),
            won: won[i],
            draw: draw[i],
            score: score[i],
            method: method[i].clone(),
            title: title[i],
            interim: interim[i],
            champion: champion[i],
            interim_champion: interim_champion[i],
        })
        .collect()
}

pub fn write(snapshot: &Path, a: &[Appearance]) {
    let s = |g: fn(&Appearance) -> &str| a.iter().map(g).collect::<Vec<_>>();
    let b = |g: fn(&Appearance) -> bool| a.iter().map(g).collect::<Vec<_>>();
    Table::default()
        .str("fight_url", &s(|x| &x.url))
        .day("event_date", &a.iter().map(|x| Some(x.day)).collect::<Vec<_>>())
        .str("event_name", &s(|x| &x.event))
        .str("fighter", &s(|x| &x.fighter))
        .str("opponent", &s(|x| &x.opponent))
        .opt_str("division", &s(|x| &x.division))
        .bool("is_winner", &b(|x| x.won))
        .bool("is_draw", &b(|x| x.draw))
        .f64("actual_score", &a.iter().map(|x| x.score).collect::<Vec<_>>())
        .str("method_class", &s(|x| &x.method))
        .bool("is_championship_bout", &b(|x| x.title))
        .bool("is_interim_title_bout", &b(|x| x.interim))
        .bool("fighter_entered_as_champion", &b(|x| x.champion))
        .bool("fighter_entered_as_interim_champion", &b(|x| x.interim_champion))
        .write(&snapshot.join(FILE));
}
