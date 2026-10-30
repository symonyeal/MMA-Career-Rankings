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
from typing_extensions import Self

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

    def __enter__(self) -> Self:
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
