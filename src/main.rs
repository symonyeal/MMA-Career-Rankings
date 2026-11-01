//! `mma <snapshot>`: rebuild every published output from a staged snapshot.

fn main() {
    let snap = std::env::args().nth(1).expect("usage: mma <snapshot-dir>");
    eprintln!("{snap}: pipeline not wired yet");
}
