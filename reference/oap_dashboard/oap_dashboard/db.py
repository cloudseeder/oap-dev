"""SQLite data layer for the OAP adoption dashboard."""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS manifests (
    domain        TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    description   TEXT NOT NULL,
    manifest_url  TEXT NOT NULL,
    manifest_hash TEXT NOT NULL,
    first_seen    TEXT NOT NULL,
    last_seen     TEXT NOT NULL,
    last_checked  TEXT NOT NULL,
    oap_version   TEXT NOT NULL,
    invoke_url    TEXT,
    invoke_method TEXT,
    tags          TEXT,  -- JSON array
    publisher_name TEXT,
    health_ok     INTEGER  -- 1/0/NULL
);

CREATE TABLE IF NOT EXISTS snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    domain          TEXT NOT NULL REFERENCES manifests(domain),
    checked_at      TEXT NOT NULL,
    status          TEXT NOT NULL,  -- ok, error, changed
    manifest_hash   TEXT,
    response_time_ms INTEGER
);

CREATE TABLE IF NOT EXISTS stats_daily (
    date    TEXT PRIMARY KEY,
    total   INTEGER NOT NULL,
    new     INTEGER NOT NULL,
    healthy INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_snapshots_domain ON snapshots(domain);
CREATE INDEX IF NOT EXISTS idx_snapshots_checked ON snapshots(checked_at);
"""


class DashboardDB:
    def __init__(self, db_path: str = "dashboard.db"):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def close(self):
        self.conn.close()

    # --- Write operations (used by crawler) ---

    def upsert_manifest(
        self,
        domain: str,
        name: str,
        description: str,
        manifest_url: str,
        manifest_hash: str,
        oap_version: str,
        invoke_url: str | None = None,
        invoke_method: str | None = None,
        tags: list[str] | None = None,
        publisher_name: str | None = None,
        health_ok: bool | None = None,
    ) -> bool:
        """Upsert a manifest. Returns True if this is a new domain."""
        now = datetime.utcnow().isoformat()
        existing = self.conn.execute(
            "SELECT domain FROM manifests WHERE domain = ?", (domain,)
        ).fetchone()

        if existing:
            self.conn.execute(
                """UPDATE manifests SET
                    name=?, description=?, manifest_url=?, manifest_hash=?,
                    last_seen=?, last_checked=?, oap_version=?,
                    invoke_url=?, invoke_method=?, tags=?, publisher_name=?, health_ok=?
                WHERE domain=?""",
                (
                    name, description, manifest_url, manifest_hash,
                    now, now, oap_version,
                    invoke_url, invoke_method,
                    json.dumps(tags) if tags else None,
                    publisher_name,
                    1 if health_ok is True else (0 if health_ok is False else None),
                    domain,
                ),
            )
            self.conn.commit()
            return False
        else:
            self.conn.execute(
                """INSERT INTO manifests
                    (domain, name, description, manifest_url, manifest_hash,
                     first_seen, last_seen, last_checked, oap_version,
                     invoke_url, invoke_method, tags, publisher_name, health_ok)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    domain, name, description, manifest_url, manifest_hash,
                    now, now, now, oap_version,
                    invoke_url, invoke_method,
                    json.dumps(tags) if tags else None,
                    publisher_name,
                    1 if health_ok is True else (0 if health_ok is False else None),
                ),
            )
            self.conn.commit()
            return True

    def add_snapshot(
        self,
        domain: str,
        status: str,
        manifest_hash: str | None = None,
        response_time_ms: int | None = None,
    ):
        now = datetime.utcnow().isoformat()
        self.conn.execute(
            "INSERT INTO snapshots (domain, checked_at, status, manifest_hash, response_time_ms) VALUES (?, ?, ?, ?, ?)",
            (domain, now, status, manifest_hash, response_time_ms),
        )
        self.conn.commit()

    def update_daily_stats(self):
        today = date.today().isoformat()
        total = self.conn.execute("SELECT COUNT(*) FROM manifests").fetchone()[0]
        new = self.conn.execute(
            "SELECT COUNT(*) FROM manifests WHERE first_seen LIKE ?", (today + "%",)
        ).fetchone()[0]
        healthy = self.conn.execute(
            "SELECT COUNT(*) FROM manifests WHERE health_ok = 1"
        ).fetchone()[0]
        self.conn.execute(
            "INSERT OR REPLACE INTO stats_daily (date, total, new, healthy) VALUES (?, ?, ?, ?)",
            (today, total, new, healthy),
        )
        self.conn.commit()

    # --- Read operations (used by API) ---

    def get_stats(self) -> dict:
        row = self.conn.execute(
            "SELECT * FROM stats_daily ORDER BY date DESC LIMIT 1"
        ).fetchone()
        if not row:
            total = self.conn.execute("SELECT COUNT(*) FROM manifests").fetchone()[0]
            healthy = self.conn.execute(
                "SELECT COUNT(*) FROM manifests WHERE health_ok = 1"
            ).fetchone()[0]
            return {"date": date.today().isoformat(), "total": total, "new": 0, "healthy": healthy}
        return dict(row)

    def get_stats_history(self, days: int = 30) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM stats_daily ORDER BY date DESC LIMIT ?", (days,)
        ).fetchall()
        return [dict(r) for r in reversed(rows)]

    def get_manifests(self, page: int = 1, limit: int = 50) -> dict:
        offset = (page - 1) * limit
        total = self.conn.execute("SELECT COUNT(*) FROM manifests").fetchone()[0]
        rows = self.conn.execute(
            "SELECT * FROM manifests ORDER BY last_seen DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        manifests = []
        for r in rows:
            m = dict(r)
            if m.get("tags"):
                m["tags"] = json.loads(m["tags"])
            m["health_ok"] = bool(m["health_ok"]) if m["health_ok"] is not None else None
            manifests.append(m)
        return {"manifests": manifests, "total": total, "page": page, "limit": limit}
