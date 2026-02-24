"""SQLite FTS5 manifest store — keyword search with BM25 ranking."""

from __future__ import annotations

import json
import logging
import sqlite3
from typing import Any

log = logging.getLogger("oap.fts")


class FTSStore:
    """Full-text search store using SQLite FTS5.

    Mirrors the ManifestStore (db.py) interface so discovery.py can use
    either interchangeably.  No embeddings needed — just keywords + BM25.
    """

    def __init__(self, db_path: str) -> None:
        self._conn = sqlite3.connect(db_path)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._create_schema()

    def _create_schema(self) -> None:
        cur = self._conn.cursor()
        cur.executescript("""
            CREATE TABLE IF NOT EXISTS manifests (
                domain TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL,
                manifest_json TEXT NOT NULL,
                invoke_method TEXT NOT NULL,
                invoke_url TEXT NOT NULL,
                tags TEXT NOT NULL DEFAULT ''
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS manifests_fts USING fts5(
                name, description, tags,
                content='manifests',
                content_rowid='rowid'
            );

            CREATE TRIGGER IF NOT EXISTS manifests_ai AFTER INSERT ON manifests BEGIN
                INSERT INTO manifests_fts(rowid, name, description, tags)
                VALUES (new.rowid, new.name, new.description, new.tags);
            END;

            CREATE TRIGGER IF NOT EXISTS manifests_ad AFTER DELETE ON manifests BEGIN
                INSERT INTO manifests_fts(manifests_fts, rowid, name, description, tags)
                VALUES ('delete', old.rowid, old.name, old.description, old.tags);
            END;

            CREATE TRIGGER IF NOT EXISTS manifests_au AFTER UPDATE ON manifests BEGIN
                INSERT INTO manifests_fts(manifests_fts, rowid, name, description, tags)
                VALUES ('delete', old.rowid, old.name, old.description, old.tags);
                INSERT INTO manifests_fts(rowid, name, description, tags)
                VALUES (new.rowid, new.name, new.description, new.tags);
            END;
        """)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def upsert_manifest(self, domain: str, manifest: dict[str, Any]) -> None:
        """Insert or replace a manifest (triggers keep FTS in sync)."""
        self._conn.execute(
            """INSERT OR REPLACE INTO manifests
               (domain, name, description, manifest_json, invoke_method, invoke_url, tags)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                domain,
                manifest["name"],
                manifest["description"],
                json.dumps(manifest),
                manifest["invoke"]["method"],
                manifest["invoke"]["url"],
                ",".join(manifest.get("tags") or []),
            ),
        )
        self._conn.commit()

    def search(self, query: str, n_results: int = 10) -> list[dict[str, Any]]:
        """FTS5 MATCH with BM25 ranking.

        Returns same dict shape as ManifestStore.search():
        {domain, name, description, manifest, score}.
        Score is negated BM25 rank (lower = better, matching ChromaDB's
        cosine distance convention).
        """
        # FTS5 special characters that need quoting
        # Wrap each token in double quotes so punctuation is treated as literal
        tokens = query.split()
        if not tokens:
            return []
        fts_query = " OR ".join(f'"{t}"' for t in tokens)

        try:
            rows = self._conn.execute(
                """SELECT m.domain, m.name, m.description, m.manifest_json,
                          rank
                   FROM manifests_fts fts
                   JOIN manifests m ON m.rowid = fts.rowid
                   WHERE manifests_fts MATCH ?
                   ORDER BY rank
                   LIMIT ?""",
                (fts_query, n_results),
            ).fetchall()
        except sqlite3.OperationalError:
            log.warning("FTS query failed for %r", query)
            return []

        hits = []
        for domain, name, description, manifest_json, rank in rows:
            hits.append(
                {
                    "domain": domain,
                    "name": name,
                    "description": description,
                    "manifest": json.loads(manifest_json),
                    "score": rank,  # BM25 rank (negative, lower = better)
                }
            )
        return hits

    def get_manifest(self, domain: str) -> dict[str, Any] | None:
        """Get a specific manifest by domain."""
        row = self._conn.execute(
            "SELECT manifest_json FROM manifests WHERE domain = ?",
            (domain,),
        ).fetchone()
        if row is None:
            return None
        return json.loads(row[0])

    def list_domains(self) -> list[dict[str, str]]:
        """List all indexed domains with names."""
        rows = self._conn.execute(
            "SELECT domain, name, description FROM manifests"
        ).fetchall()
        return [
            {"domain": d, "name": n, "description": desc}
            for d, n, desc in rows
        ]

    def count(self) -> int:
        """Return number of indexed manifests."""
        row = self._conn.execute("SELECT COUNT(*) FROM manifests").fetchone()
        return row[0]
