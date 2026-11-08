//! MMA career rankings: ratings, scores, boards and site data from a staged snapshot.

// Row tuples and wide stage signatures mirror the tables they build.
#![allow(
    clippy::type_complexity,
    clippy::too_many_arguments,
    clippy::needless_range_loop
)]

pub mod age;
pub mod appearances;
pub mod audit;
pub mod boards;
pub mod bouts;
pub mod classes;
pub mod connectivity;
pub mod current;
pub mod division;
pub mod divisions;
pub mod dominance;
pub mod era;
pub mod error;
pub mod figures;
pub mod fm;
pub mod forecast;
pub mod frame;
pub mod glicko;
pub mod heldout;
pub mod history;
pub mod integrity;
pub mod layoff;
pub mod legacy;
pub mod names;
pub mod narrative;
pub mod orgs;
pub mod perf;
pub mod policy;
pub mod publish;
pub mod pyjson;
pub mod release;
pub mod roster;
pub mod site;
pub mod skill;
pub mod stats;
pub mod whr;
