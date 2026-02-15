"""SQLite attestation and challenge store."""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .config import DatabaseConfig

log = logging.getLogger("oap.trust.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS attestations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    domain TEXT NOT NULL,
    layer INTEGER NOT NULL,
    jws TEXT NOT NULL,
    manifest_hash TEXT NOT NULL,
    verification_method TEXT,
    issued_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_attestations_domain ON attestations(domain);
CREATE INDEX IF NOT EXISTS idx_attestations_expires ON attestations(expires_at);

CREATE TABLE IF NOT EXISTS challenges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    domain TEXT NOT NULL,
    token TEXT NOT NULL UNIQUE,
    method TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_challenges_domain ON challenges(domain);
CREATE INDEX IF NOT EXISTS idx_challenges_token ON challenges(token);
"""


class TrustStore:
    """SQLite-backed store for attestations and challenges."""

    def __init__(self, cfg: DatabaseConfig) -> None:
        db_path = Path(cfg.path)
        db_path.parent.mkdir(parents=True, exist_ok=True)

        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(SCHEMA)
        log.info("Trust store opened at %s", db_path)

    # --- Challenges ---

    def create_challenge(
        self,
        domain: str,
        token: str,
        method: str,
        expires_at: datetime,
    ) -> None:
        """Store a new challenge."""
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "INSERT INTO challenges (domain, token, method, status, created_at, expires_at) "
            "VALUES (?, ?, ?, 'pending', ?, ?)",
            (domain, token, method, now, expires_at.isoformat()),
        )
        self._conn.commit()

    def get_pending_challenge(self, domain: str) -> dict | None:
        """Get the most recent pending, non-expired challenge for a domain."""
        now = datetime.now(timezone.utc).isoformat()
        row = self._conn.execute(
            "SELECT * FROM challenges "
            "WHERE domain = ? AND status = 'pending' AND expires_at > ? "
            "ORDER BY created_at DESC LIMIT 1",
            (domain, now),
        ).fetchone()
        return dict(row) if row else None

    def mark_challenge_verified(self, token: str) -> None:
        """Mark a challenge as verified."""
        self._conn.execute(
            "UPDATE challenges SET status = 'verified' WHERE token = ?",
            (token,),
        )
        self._conn.commit()

    def cleanup_expired_challenges(self) -> int:
        """Remove expired challenges. Returns count removed."""
        now = datetime.now(timezone.utc).isoformat()
        cursor = self._conn.execute(
            "DELETE FROM challenges WHERE expires_at <= ?", (now,)
        )
        self._conn.commit()
        return cursor.rowcount

    # --- Attestations ---

    def store_attestation(
        self,
        domain: str,
        layer: int,
        jws: str,
        manifest_hash: str,
        verification_method: str | None,
        issued_at: datetime,
        expires_at: datetime,
    ) -> None:
        """Store a signed attestation."""
        self._conn.execute(
            "INSERT INTO attestations "
            "(domain, layer, jws, manifest_hash, verification_method, issued_at, expires_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (domain, layer, jws, manifest_hash, verification_method,
             issued_at.isoformat(), expires_at.isoformat()),
        )
        self._conn.commit()

    def get_attestations(self, domain: str) -> list[dict]:
        """Get all non-expired attestations for a domain."""
        now = datetime.now(timezone.utc).isoformat()
        rows = self._conn.execute(
            "SELECT * FROM attestations WHERE domain = ? AND expires_at > ? "
            "ORDER BY layer, issued_at DESC",
            (domain, now),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_latest_attestation(self, domain: str, layer: int) -> dict | None:
        """Get the most recent non-expired attestation for a domain at a given layer."""
        now = datetime.now(timezone.utc).isoformat()
        row = self._conn.execute(
            "SELECT * FROM attestations "
            "WHERE domain = ? AND layer = ? AND expires_at > ? "
            "ORDER BY issued_at DESC LIMIT 1",
            (domain, layer, now),
        ).fetchone()
        return dict(row) if row else None

    def count_attestations(self) -> int:
        """Total number of non-expired attestations."""
        now = datetime.now(timezone.utc).isoformat()
        row = self._conn.execute(
            "SELECT COUNT(*) FROM attestations WHERE expires_at > ?", (now,)
        ).fetchone()
        return row[0]

    def close(self) -> None:
        self._conn.close()
