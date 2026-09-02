"""One store for every scraped page, so a cache is one file and not thousands.

Each reader used to drop one file per fetched page into its own directory, in
its own layout: plain HTML here, gzipped HTML there, a third naming scheme
somewhere else. That reached 6,972 files and 254 MB for what is, in every case,
the same thing — the bytes a page returned, kept so a parser can run again
without asking the site again.

This is that thing, once. A store is a single SQLite file holding gzipped page
text under ``(kind, key)``. Compression is per row, so a page still reads back on
its own without unpacking the rest, and the store stays a normal file that can be
copied, backed up, or deleted whole.

Readers address a store through ``open_cache(cache_dir)``, so ``--cache-dir``
still names a directory and the store lives inside it.
"""
from __future__ import annotations

import gzip
import sqlite3
from collections.abc import Iterator
from pathlib import Path

STORE_NAME = "pages.sqlite"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS pages (
    kind        TEXT NOT NULL,
    key         TEXT NOT NULL,
    body        BLOB NOT NULL,
    fetched_utc TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (kind, key)
) WITHOUT ROWID;
"""


class PageCache:
    """Gzipped page bodies keyed by ``(kind, key)`` in one SQLite file."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.path)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.executescript(_SCHEMA)
        self._db.commit()

    # -- reading ------------------------------------------------------------

    def get(self, kind: str, key: str) -> str | None:
        """Page text, or ``None`` when this store has never held it."""
        row = self._db.execute(
            "SELECT body FROM pages WHERE kind = ? AND key = ?", (kind, str(key))
        ).fetchone()
        if row is None:
            return None
        return gzip.decompress(row[0]).decode("utf-8", errors="replace")

    def has(self, kind: str, key: str) -> bool:
        return self._db.execute(
            "SELECT 1 FROM pages WHERE kind = ? AND key = ?", (kind, str(key))
        ).fetchone() is not None

    def keys(self, kind: str) -> list[str]:
        """Every key held under ``kind``, in sorted order."""
        return [
            r[0]
            for r in self._db.execute(
                "SELECT key FROM pages WHERE kind = ? ORDER BY key", (kind,)
            )
        ]

    def items(self, kind: str) -> Iterator[tuple[str, str]]:
        """Every ``(key, page text)`` under ``kind``, one row read at a time."""
        for key, body in self._db.execute(
            "SELECT key, body FROM pages WHERE kind = ? ORDER BY key", (kind,)
        ):
            yield key, gzip.decompress(body).decode("utf-8", errors="replace")

    def counts(self) -> dict[str, int]:
        """Pages held, by kind."""
        return dict(
            self._db.execute("SELECT kind, COUNT(*) FROM pages GROUP BY kind ORDER BY kind")
        )

    # -- writing ------------------------------------------------------------

    def put(self, kind: str, key: str, text: str) -> None:
        body = gzip.compress(text.encode("utf-8"), compresslevel=6)
        self._db.execute(
            "INSERT INTO pages (kind, key, body) VALUES (?, ?, ?) "
            "ON CONFLICT (kind, key) DO UPDATE SET body = excluded.body, "
            "fetched_utc = datetime('now')",
            (kind, str(key), body),
        )
        self._db.commit()

    def close(self) -> None:
        self._db.close()

    def __enter__(self) -> PageCache:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def __repr__(self) -> str:
        return f"PageCache({self.path}, {sum(self.counts().values())} pages)"


def open_cache(cache_dir: Path | str | PageCache) -> PageCache:
    """Open the store inside ``cache_dir``; pass a store through unchanged."""
    if isinstance(cache_dir, PageCache):
        return cache_dir
    return PageCache(Path(cache_dir) / STORE_NAME)


def fold_in_loose_files(
    cache_dir: Path | str,
    layout: dict[str, tuple[str, ...]],
    *,
    remove: bool = False,
) -> dict[str, int]:
    """Move a directory of one-file-per-page caches into the store.

    ``layout`` maps a subdirectory name to the filename suffixes to read from
    it; a subdirectory named ``"."`` means the cache directory itself. The key
    is the filename with its suffix removed. Pages already in the store are left
    alone, so this is safe to re-run.
    """
    cache_dir = Path(cache_dir)
    cache = open_cache(cache_dir)
    folded: dict[str, int] = {}
    for kind, suffixes in layout.items():
        source = cache_dir if kind == "." else cache_dir / kind
        if not source.is_dir():
            continue
        moved = 0
        for suffix in suffixes:
            for path in sorted(source.glob(f"*{suffix}")):
                key = path.name.removesuffix(suffix)
                if cache.has(kind, key):
                    if remove:
                        path.unlink()
                    continue
                if suffix.endswith(".gz"):
                    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as fh:
                        text = fh.read()
                else:
                    text = path.read_text(encoding="utf-8", errors="replace")
                cache.put(kind, key, text)
                moved += 1
                if remove:
                    path.unlink()
        folded[kind] = moved
    return folded
