//! Accepted file generations and recoverable projection into the checkout.
//!
//! Readers requiring a consistent release pin `target/releases/accepted.json`
//! and read its immutable `root`. The checkout is a compatibility projection:
//! it is rolled back on failure, but concurrent readers of separate checkout
//! files are not given a transaction. Pages publishes the accepted generation.
//! Asset-only stamps use `accepted-site.json`; they never replace the full
//! model release pointer.

use std::collections::BTreeMap;
use std::fs::{self, File, OpenOptions};
use std::io::{self, Write};
use std::path::{Component, Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};

use serde_json::{json, Value};
use sha2::{Digest, Sha256};

const EXTERNAL: [&str; 4] = [
    "data/external/aliases/fighter_aliases.csv",
    "data/external/crossorg/identity_overrides.csv",
    "data/external/fightmatrix/organization_normalization.csv",
    "data/external/integrity/ped_bouts.csv",
];
const TABLES: [&str; 17] = [
    "ratings_current.parquet",
    "ratings_history_whr.parquet",
    "performance_appearances.parquet",
    "integrity_appearances.parquet",
    "fighter_dominance.parquet",
    "calibration_residuals.parquet",
    "completeness_gated_board.parquet",
    "completeness_gated_board_women.parquet",
    "prime_elite_board.parquet",
    "prime_elite_board_women.parquet",
    "current_board.parquet",
    "current_board_women.parquet",
    "integrity_ledger.parquet",
    "integrity_discounted_board.parquet",
    "class_board.parquet",
    "rating_run.json",
    "release_manifest.json",
];
const AUDIT: [&str; 5] = [
    "top100_score_comparison.parquet",
    "top100_audit.parquet",
    "top100_audit.csv",
    "public_anchor_missing_from_model_top100.csv",
    "top100_audit.json",
];

fn invalid(message: impl Into<String>) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, message.into())
}

fn relative(path: &Path) -> io::Result<()> {
    if path.as_os_str().is_empty()
        || path
            .components()
            .any(|c| !matches!(c, Component::Normal(_)))
    {
        return Err(invalid(
            "release paths must be relative, without parent traversal",
        ));
    }
    Ok(())
}

fn copy(from: &Path, to: &Path) -> io::Result<()> {
    fs::create_dir_all(to.parent().unwrap())?;
    fs::copy(from, to)?;
    Ok(())
}

fn files(root: &Path) -> io::Result<Vec<PathBuf>> {
    let mut out = Vec::new();
    for entry in fs::read_dir(root)? {
        let entry = entry?;
        if entry.file_type()?.is_dir() {
            for p in files(&entry.path())? {
                out.push(PathBuf::from(entry.file_name()).join(p));
            }
        } else if entry.file_type()?.is_file() {
            out.push(PathBuf::from(entry.file_name()));
        } else {
            return Err(invalid(
                "release inputs must be regular files or directories",
            ));
        }
    }
    out.sort();
    Ok(out)
}

fn digest(path: &Path) -> io::Result<String> {
    Ok(format!("{:x}", Sha256::digest(fs::read(path)?)))
}

fn receipt(root: &Path, paths: &[PathBuf]) -> io::Result<BTreeMap<String, String>> {
    paths
        .iter()
        .map(|p| {
            relative(p)?;
            Ok((
                p.to_string_lossy().replace('\\', "/"),
                digest(&root.join(p))?,
            ))
        })
        .collect()
}

/// Optimistic protection for authored files outside the cooperating writer lock.
/// Their original bytes are checked separately from reproducible model receipts:
/// README and RANKINGS contain generated blocks and cannot be manifest inputs.
struct Authored {
    docs: bool,
    hashes: BTreeMap<String, String>,
}

impl Authored {
    fn capture(root: &Path, docs: bool) -> io::Result<Self> {
        let mut paths = files(&root.join("site"))?
            .into_iter()
            .map(|p| PathBuf::from("site").join(p))
            .collect::<Vec<_>>();
        if docs {
            paths.extend(["README.md", "RANKINGS.md"].map(PathBuf::from));
        }
        Ok(Self {
            docs,
            hashes: receipt(root, &paths)?,
        })
    }

    fn check(&self, root: &Path) -> io::Result<()> {
        if Self::capture(root, self.docs)?.hashes != self.hashes {
            return Err(invalid(
                "authored site or documentation changed during generation",
            ));
        }
        Ok(())
    }

    fn copy(&self, root: &Path, stage: &Path, omit_data: bool) -> io::Result<()> {
        for (p, hash) in &self.hashes {
            if omit_data && p == "site/data.js" {
                continue;
            }
            copy(&root.join(p), &stage.join(p))?;
            if digest(&stage.join(p))? != *hash {
                return Err(invalid("authored file changed while being copied"));
            }
        }
        self.check(root)
    }
}

#[derive(Clone, Copy)]
enum Pointer {
    Release,
    Site,
}

impl Pointer {
    fn file(self) -> &'static str {
        match self {
            Self::Release => "accepted.json",
            Self::Site => "accepted-site.json",
        }
    }

    fn from_journal(value: Option<&Value>) -> io::Result<Self> {
        match value.and_then(Value::as_str) {
            None if value.is_none() => Ok(Self::Release), // interrupted older releases
            Some("accepted.json") => Ok(Self::Release),
            Some("accepted-site.json") => Ok(Self::Site),
            _ => Err(invalid("unknown acceptance pointer")),
        }
    }
}

/// Write beside the destination, sync file contents, then replace its name.
/// Directory-entry durability across power loss remains filesystem dependent.
fn replace(path: &Path, bytes: &[u8]) -> io::Result<()> {
    fs::create_dir_all(path.parent().unwrap())?;
    let pending = path.with_extension("mma-building");
    let mut f = File::create(&pending)?;
    f.write_all(bytes)?;
    f.sync_all()?;
    drop(f);
    fs::rename(pending, path)
}

fn json_file(path: &Path) -> io::Result<Value> {
    serde_json::from_slice(&fs::read(path)?).map_err(|e| invalid(e.to_string()))
}

struct Writer {
    root: PathBuf,
    store: PathBuf,
    // OS ownership is released on normal exit, unwind and process death.
    _lock: File,
}

impl Writer {
    fn new(root: &Path) -> io::Result<Self> {
        let root = root.canonicalize()?;
        let store = root.join("target/releases");
        fs::create_dir_all(&store)?;
        let lock = OpenOptions::new()
            .read(true)
            .write(true)
            .create(true)
            .truncate(false)
            .open(store.join("writer.lock"))?;
        lock.try_lock().map_err(|e| {
            io::Error::other(format!("another release writer owns this checkout: {e}"))
        })?;
        let writer = Self {
            root,
            store,
            _lock: lock,
        };
        writer.recover()?;
        Ok(writer)
    }

    fn recover(&self) -> io::Result<()> {
        let pending = self.store.join("pending.json");
        if !pending.exists() {
            return Ok(());
        }
        let journal = json_file(&pending)?;
        let id = journal["generation"]
            .as_str()
            .ok_or_else(|| invalid("missing generation"))?;
        relative(Path::new(id))?;
        let pointer = Pointer::from_journal(journal.get("pointer"))?;
        let accepted = self.store.join(pointer.file());
        if accepted.exists() && json_file(&accepted)?["generation"] == id {
            fs::remove_file(pending)?;
            return Ok(());
        }
        let entries = journal["files"]
            .as_array()
            .ok_or_else(|| invalid("missing rollback entries"))?;
        for entry in entries {
            let p = Path::new(
                entry["path"]
                    .as_str()
                    .ok_or_else(|| invalid("missing rollback path"))?,
            );
            relative(p)?;
            if entry["existed"]
                .as_bool()
                .ok_or_else(|| invalid("missing rollback state"))?
            {
                let old = fs::read(self.store.join(id).join("rollback").join(p))?;
                replace(&self.root.join(p), &old)?;
            } else if self.root.join(p).exists() {
                fs::remove_file(self.root.join(p))?;
            }
        }
        fs::remove_file(pending)
    }

    fn generation(&self) -> io::Result<(String, PathBuf)> {
        static NEXT: AtomicU64 = AtomicU64::new(0);
        let id = format!(
            "{}-{}-{}",
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos(),
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        );
        let root = self.store.join(&id).join("root");
        fs::create_dir_all(&root)?;
        Ok((id, root))
    }

    fn promote(
        &self,
        id: &str,
        paths: &[PathBuf],
        pointer: Pointer,
        fail_after: Option<usize>,
    ) -> io::Result<()> {
        let generation = self.store.join(id);
        let mut entries = Vec::new();
        for p in paths {
            relative(p)?;
            let existed = self.root.join(p).exists();
            if existed {
                copy(&self.root.join(p), &generation.join("rollback").join(p))?;
            }
            entries
                .push(json!({"path": p.to_string_lossy().replace('\\', "/"), "existed": existed}));
        }
        replace(
            &self.store.join("pending.json"),
            &serde_json::to_vec(
                &json!({"generation": id, "pointer": pointer.file(), "files": entries}),
            )?,
        )?;
        let result = (|| {
            for (i, p) in paths.iter().enumerate() {
                if fail_after == Some(i) {
                    return Err(io::Error::other("injected projection failure"));
                }
                replace(
                    &self.root.join(p),
                    &fs::read(generation.join("root").join(p))?,
                )?;
            }
            if fail_after == Some(paths.len()) {
                return Err(io::Error::other("injected acceptance failure"));
            }
            replace(
                &self.store.join(pointer.file()),
                &serde_json::to_vec_pretty(
                    &json!({"generation": id, "root": format!("target/releases/{id}/root")}),
                )?,
            )
        })();
        if let Err(error) = result {
            self.recover()?;
            return Err(error);
        }
        self.recover()
    }
}

/// Only `<root>/data/snapshots/<date>` is a release snapshot; resolve it before I/O.
pub fn root_of(snapshot: &Path) -> io::Result<PathBuf> {
    let snapshot = snapshot.canonicalize()?;
    let snapshots = snapshot
        .parent()
        .ok_or_else(|| invalid("missing snapshots directory"))?;
    let data = snapshots
        .parent()
        .ok_or_else(|| invalid("missing data directory"))?;
    if !snapshot.is_dir()
        || snapshots.file_name().is_none_or(|s| s != "snapshots")
        || data.file_name().is_none_or(|s| s != "data")
    {
        return Err(invalid("snapshot must be <root>/data/snapshots/<date>"));
    }
    Ok(data
        .parent()
        .ok_or_else(|| invalid("missing project root"))?
        .to_path_buf())
}

/// Compute entirely off-tree, validate a required inventory, then accept its projection.
pub fn build(snapshot: &Path, compute: impl FnOnce(&Path, &Path)) -> io::Result<()> {
    let root = root_of(snapshot)?;
    let snapshot = snapshot.canonicalize()?;
    let relative_snapshot = snapshot
        .strip_prefix(&root)
        .map_err(|e| invalid(e.to_string()))?;
    let writer = Writer::new(&root)?;
    let (id, stage) = writer.generation()?;
    let authored = Authored::capture(&root, true)?;
    authored.copy(&root, &stage, true)?;
    let mut inputs: Vec<PathBuf> = files(&snapshot)?
        .into_iter()
        .filter(|p| !TABLES.iter().any(|name| p == Path::new(name)))
        .map(|p| relative_snapshot.join(p))
        .collect();
    // Previous outputs are not inputs: a forgotten producer must fail admission,
    // rather than silently reuse an old table from the copied snapshot.
    for p in &inputs {
        copy(&root.join(p), &stage.join(p))?;
    }
    for p in EXTERNAL {
        copy(&root.join(p), &stage.join(p))?;
        inputs.push(PathBuf::from(p));
    }
    let mut code = files(&root.join("src"))?
        .into_iter()
        .map(|p| PathBuf::from("src").join(p))
        .collect::<Vec<_>>();
    code.extend([PathBuf::from("Cargo.toml"), PathBuf::from("Cargo.lock")]);
    let source = receipt(&root, &code)?;
    let input_paths = inputs;
    let inputs = receipt(&stage, &input_paths)?;
    if receipt(&root, &input_paths)? != inputs {
        return Err(invalid("release inputs changed while being copied"));
    }
    compute(&stage.join(relative_snapshot), &stage);
    if receipt(&root, &input_paths)? != inputs || receipt(&root, &code)? != source {
        return Err(invalid(
            "release inputs or source changed during computation",
        ));
    }
    authored.check(&root)?;
    let mut outputs = TABLES[..TABLES.len() - 1]
        .iter()
        .map(|p| relative_snapshot.join(p))
        .collect::<Vec<_>>();
    outputs.extend(
        [
            "README.md",
            "RANKINGS.md",
            "site/data.js",
            "site/index.html",
        ]
        .map(PathBuf::from),
    );
    outputs.extend(
        files(&stage.join("site"))?
            .into_iter()
            .map(|p| PathBuf::from("site").join(p)),
    );
    outputs.sort();
    outputs.dedup();
    outputs.extend(
        AUDIT
            .iter()
            .map(|p| PathBuf::from("data/model_tuning/top100-audit").join(p)),
    );
    let hashes = receipt(&stage, &outputs)?;
    let manifest = serde_json::to_vec_pretty(
        &json!({"schema": 1, "snapshot": relative_snapshot.to_string_lossy().replace('\\', "/"), "source_sha256": source, "input_sha256": inputs, "output_sha256": hashes}),
    )?;
    let manifest_path = relative_snapshot.join("release_manifest.json");
    fs::write(stage.join(&manifest_path), &manifest)?;
    fs::write(stage.parent().unwrap().join("manifest.json"), &manifest)?;
    outputs.push(manifest_path);
    authored.check(&root)?;
    writer.promote(&id, &outputs, Pointer::Release, None)
}

/// Stamp a copied site under the same writer ownership as a model release.
pub fn stamp(root: &Path, compute: impl FnOnce(&Path)) -> io::Result<()> {
    let writer = Writer::new(root)?;
    let (id, stage) = writer.generation()?;
    let authored = Authored::capture(&writer.root, false)?;
    authored.copy(&writer.root, &stage, false)?;
    compute(&stage.join("site"));
    let paths = files(&stage.join("site"))?
        .into_iter()
        .map(|p| PathBuf::from("site").join(p))
        .collect::<Vec<_>>();
    fs::write(
        stage.parent().unwrap().join("manifest.json"),
        serde_json::to_vec_pretty(
            &json!({"schema": 1, "output_sha256": receipt(&stage, &paths)?}),
        )?,
    )?;
    authored.check(&writer.root)?;
    writer.promote(
        &id,
        &[PathBuf::from("site/index.html")],
        Pointer::Site,
        None,
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    fn fixture() -> PathBuf {
        static NEXT: AtomicU64 = AtomicU64::new(0);
        let base = std::env::var_os("MMA_TEST_ROOT")
            .map(PathBuf::from)
            .unwrap_or_else(|| Path::new(env!("CARGO_MANIFEST_DIR")).join("target/release-tests"));
        let root = base.join(format!(
            "{}-{}-{}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir_all(&root).unwrap();
        root
    }

    #[test]
    fn failed_projection_preserves_old_generation_and_removes_new_files() {
        for fail in 0..=3 {
            let root = fixture();
            fs::write(root.join("a"), b"old-a").unwrap();
            fs::write(root.join("b"), b"old-b").unwrap();
            let writer = Writer::new(&root).unwrap();
            fs::write(
                writer.store.join("accepted.json"),
                br#"{"generation":"old"}"#,
            )
            .unwrap();
            let (id, stage) = writer.generation().unwrap();
            for name in ["a", "b", "c"] {
                fs::write(stage.join(name), b"new").unwrap();
            }
            let paths = ["a", "b", "c"].map(PathBuf::from);
            assert!(writer
                .promote(&id, &paths, Pointer::Release, Some(fail))
                .is_err());
            assert_eq!(fs::read(root.join("a")).unwrap(), b"old-a");
            assert_eq!(fs::read(root.join("b")).unwrap(), b"old-b");
            assert!(!root.join("c").exists());
            assert_eq!(
                json_file(&writer.store.join("accepted.json")).unwrap()["generation"],
                "old"
            );
        }
    }

    #[test]
    fn interrupted_projection_is_recovered_by_next_exclusive_writer() {
        let root = fixture();
        let writer = Writer::new(&root).unwrap();
        let (id, _) = writer.generation().unwrap();
        let old = writer.store.join(&id).join("rollback/a");
        fs::create_dir_all(old.parent().unwrap()).unwrap();
        fs::write(old, b"old").unwrap();
        fs::write(root.join("a"), b"interrupted").unwrap();
        fs::write(
            writer.store.join("pending.json"),
            serde_json::to_vec(&json!({"generation": id, "files": [{"path":"a","existed":true}]}))
                .unwrap(),
        )
        .unwrap();
        drop(writer);
        let writer = Writer::new(&root).unwrap();
        assert_eq!(fs::read(root.join("a")).unwrap(), b"old");
        assert!(!writer.store.join("pending.json").exists());
    }

    #[test]
    fn one_writer_accepts_complete_generation() {
        let root = fixture();
        let writer = Writer::new(&root).unwrap();
        assert!(Writer::new(&root).is_err());
        let (id, stage) = writer.generation().unwrap();
        fs::write(stage.join("a"), b"accepted").unwrap();
        writer
            .promote(&id, &[PathBuf::from("a")], Pointer::Release, None)
            .unwrap();
        assert_eq!(fs::read(root.join("a")).unwrap(), b"accepted");
        assert_eq!(
            json_file(&writer.store.join("accepted.json")).unwrap()["generation"],
            id
        );
        drop(writer);
        assert!(Writer::new(&root).is_ok());
    }

    #[test]
    fn snapshot_root_requires_the_declared_layout() {
        let root = fixture();
        let snapshot = root.join("data/snapshots/2026-10-24");
        fs::create_dir_all(&snapshot).unwrap();
        assert_eq!(root_of(&snapshot).unwrap(), root.canonicalize().unwrap());
        assert!(root_of(&root).is_err());
    }

    #[test]
    fn site_stamp_preserves_model_acceptance_and_detects_concurrent_edits() {
        let root = fixture();
        fs::create_dir_all(root.join("site")).unwrap();
        fs::write(root.join("site/index.html"), b"old").unwrap();
        fs::create_dir_all(root.join("target/releases")).unwrap();
        let accepted = root.join("target/releases/accepted.json");
        let original = br#"{"generation":"model","root":"model/root"}"#;
        fs::write(&accepted, original).unwrap();
        stamp(&root, |site| {
            fs::write(site.join("index.html"), b"new").unwrap()
        })
        .unwrap();
        assert_eq!(fs::read(&accepted).unwrap(), original);
        assert_eq!(fs::read(root.join("site/index.html")).unwrap(), b"new");
        assert!(root.join("target/releases/accepted-site.json").exists());
        assert!(stamp(&root, |site| {
            fs::write(site.join("index.html"), b"staged").unwrap();
            fs::write(root.join("site/index.html"), b"user edit").unwrap();
        })
        .is_err());
        assert_eq!(
            fs::read(root.join("site/index.html")).unwrap(),
            b"user edit"
        );
        assert_eq!(fs::read(accepted).unwrap(), original);
    }

    #[test]
    fn authored_receipt_rejects_document_edits_and_added_assets() {
        let root = fixture();
        fs::create_dir_all(root.join("site")).unwrap();
        for p in ["site/index.html", "README.md", "RANKINGS.md"] {
            fs::write(root.join(p), b"old").unwrap();
        }
        let receipt = Authored::capture(&root, true).unwrap();
        fs::write(root.join("README.md"), b"edit").unwrap();
        assert!(receipt.check(&root).is_err());
        fs::write(root.join("README.md"), b"old").unwrap();
        fs::write(root.join("site/new.js"), b"edit").unwrap();
        assert!(receipt.check(&root).is_err());
    }

    #[test]
    fn a_missing_producer_cannot_reuse_a_previous_snapshot_output() {
        let root = fixture();
        let snapshot = root.join("data/snapshots/2026-10-24");
        fs::create_dir_all(&snapshot).unwrap();
        fs::create_dir_all(root.join("src")).unwrap();
        fs::create_dir_all(root.join("site")).unwrap();
        for p in EXTERNAL {
            fs::create_dir_all(root.join(p).parent().unwrap()).unwrap();
            fs::write(root.join(p), b"source").unwrap();
        }
        for p in [
            "Cargo.toml",
            "Cargo.lock",
            "src/lib.rs",
            "site/index.html",
            "site/data.js",
            "README.md",
            "RANKINGS.md",
        ] {
            fs::write(root.join(p), b"old").unwrap();
        }
        fs::write(snapshot.join("input.json"), b"input").unwrap();
        for p in TABLES {
            fs::write(snapshot.join(p), b"old").unwrap();
        }
        let result = build(&snapshot, |s, stage| {
            // All producers except ratings_current run. The old table must not
            // satisfy the inventory check for this new generation.
            for p in &TABLES[1..TABLES.len() - 1] {
                fs::write(s.join(p), b"new").unwrap();
            }
            fs::create_dir_all(stage.join("data/model_tuning/top100-audit")).unwrap();
            fs::write(
                stage.join("data/model_tuning/top100-audit/audit.json"),
                b"new",
            )
            .unwrap();
            assert!(!s.join("ratings_current.parquet").exists());
            assert!(!stage.join("site/data.js").exists());
        });
        assert!(result.is_err());
        assert_eq!(
            fs::read(snapshot.join("ratings_current.parquet")).unwrap(),
            b"old"
        );
        assert_eq!(fs::read(root.join("README.md")).unwrap(), b"old");
        assert!(!root.join("target/releases/accepted.json").exists());
    }
}
