//! Integrity factors per appearance (`build_integrity_appearances`).
//!
//! A flagged result damps the winner only: PED 0.90, DQ 0.96, missed weight
//! 0.94, composed by product and clamped to [0.90, 1]. A loss is never damped,
//! since damping it would soften the penalty.

use crate::bouts::Bout;
use crate::frame::Table;

pub const PED: f64 = 0.90;
pub const DQ: f64 = 0.96;
pub const MISSED_WEIGHT: f64 = 0.94;
const FLOOR: f64 = 0.90;

/// Two rows per rated bout, every a-side first: fight_url, fighter, the three factors, integrity_weight.
pub fn appearances(rated: &[Bout]) -> Table {
    let rows: Vec<(&Bout, &str)> = rated
        .iter()
        .map(|b| (b, b.a().as_str()))
        .chain(rated.iter().map(|b| (b, b.b().as_str())))
        .collect();
    let factor = |flag: fn(&Bout, &str) -> bool, x: f64| -> Vec<f64> {
        rows.iter()
            .map(|&(b, f)| {
                if b.winner() == f && !b.draw() && flag(b, f) {
                    x
                } else {
                    1.0
                }
            })
            .collect()
    };
    let ped = factor(|b, f| b.ped && b.ped_fighter == f, PED);
    let dq = factor(|b, _| b.dq, DQ);
    let mw = factor(|b, _| b.missed_weight, MISSED_WEIGHT);
    let w: Vec<f64> = (0..rows.len())
        .map(|i| (ped[i] * dq[i] * mw[i]).clamp(FLOOR, 1.0))
        .collect();
    Table::default()
        .str(
            "fight_url",
            &rows.iter().map(|r| r.0.url.as_str()).collect::<Vec<_>>(),
        )
        .str("fighter", &rows.iter().map(|r| r.1).collect::<Vec<_>>())
        .f64("integrity_factor_ped", &ped)
        .f64("integrity_factor_dq", &dq)
        .f64("integrity_factor_missed_weight", &mw)
        .f64("integrity_weight", &w)
}
