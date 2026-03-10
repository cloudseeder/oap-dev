"""SQLite message cache for oap-email."""

from __future__ import annotations

import json
import logging
import sqlite3
import threading

log = logging.getLogger("oap.email.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id          TEXT PRIMARY KEY,
    message_id  TEXT,
    thread_id   TEXT,
    folder      TEXT NOT NULL DEFAULT 'INBOX',
    from_name   TEXT,
    from_email  TEXT,
    to_addrs    TEXT,
    cc_addrs    TEXT,
    subject     TEXT,
    snippet     TEXT,
    body_text   TEXT,
    received_at TEXT,
    is_read     INTEGER DEFAULT 1,
    is_flagged  INTEGER DEFAULT 0,
    has_attachments INTEGER DEFAULT 0,
    attachments TEXT,
    uid         INTEGER,
    cached_at   TEXT
);

CREATE INDEX IF NOT EXISTS idx_messages_received ON messages(received_at);
CREATE INDEX IF NOT EXISTS idx_messages_folder ON messages(folder);
CREATE INDEX IF NOT EXISTS idx_messages_thread ON messages(thread_id);
CREATE INDEX IF NOT EXISTS idx_messages_uid ON messages(folder, uid);
"""


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


class EmailDB:
    def __init__(self, db_path: str):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript(_SCHEMA)
        self.conn.commit()
        self._lock = threading.Lock()
        log.info("Email DB opened: %s", db_path)

    def close(self):
        self.conn.close()

    def upsert_message(
        self,
        id: str,
        message_id: str,
        thread_id: str,
        folder: str,
        from_name: str,
        from_email: str,
        to_addrs: list[dict],
        cc_addrs: list[dict],
        subject: str,
        snippet: str,
        body_text: str,
        received_at: str,
        is_read: bool,
        is_flagged: bool,
        has_attachments: bool,
        attachments: list[dict],
        uid: int,
    ) -> None:
        with self._lock:
            self.conn.execute(
                """INSERT INTO messages
                   (id, message_id, thread_id, folder, from_name, from_email,
                    to_addrs, cc_addrs, subject, snippet, body_text,
                    received_at, is_read, is_flagged, has_attachments,
                    attachments, uid, cached_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                    is_read = excluded.is_read,
                    is_flagged = excluded.is_flagged,
                    cached_at = excluded.cached_at""",
                (
                    id, message_id, thread_id, folder, from_name, from_email,
                    json.dumps(to_addrs), json.dumps(cc_addrs),
                    subject, snippet, body_text,
                    received_at, int(is_read), int(is_flagged),
                    int(has_attachments), json.dumps(attachments),
                    uid, _now(),
                ),
            )
            self.conn.commit()

    def list_messages(
        self,
        folder: str = "INBOX",
        since: str | None = None,
        unread: bool = False,
        query: str | None = None,
        limit: int = 20,
    ) -> list[dict]:
        conditions = ["folder = ?"]
        params: list = [folder]
        if since:
            conditions.append("received_at >= ?")
            params.append(since)
        if unread:
            conditions.append("is_read = 0")
        if query:
            conditions.append("(subject LIKE ? OR from_name LIKE ? OR from_email LIKE ? OR body_text LIKE ?)")
            q = f"%{query}%"
            params.extend([q, q, q, q])

        where = " AND ".join(conditions)
        rows = self.conn.execute(
            f"SELECT * FROM messages WHERE {where} ORDER BY received_at DESC LIMIT ?",
            (*params, limit),
        ).fetchall()
        return [self._decode(dict(r)) for r in rows]

    def get_message(self, msg_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM messages WHERE id = ?", (msg_id,)
        ).fetchone()
        if not row:
            return None
        return self._decode(dict(row))

    def get_thread(self, thread_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM messages WHERE thread_id = ? ORDER BY received_at ASC",
            (thread_id,),
        ).fetchall()
        return [self._decode(dict(r)) for r in rows]

    def get_max_uid(self, folder: str) -> int:
        """Return the highest cached UID for a folder, or 0."""
        row = self.conn.execute(
            "SELECT MAX(uid) FROM messages WHERE folder = ?", (folder,)
        ).fetchone()
        return row[0] or 0

    def count_unread(self, folder: str = "INBOX") -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) FROM messages WHERE folder = ? AND is_read = 0", (folder,)
        ).fetchone()
        return row[0]

    def cleanup(self, max_per_folder: int = 500) -> int:
        """Keep only the newest max_per_folder messages per folder."""
        folders = [
            r[0] for r in self.conn.execute("SELECT DISTINCT folder FROM messages").fetchall()
        ]
        deleted = 0
        with self._lock:
            for folder in folders:
                cur = self.conn.execute(
                    """DELETE FROM messages WHERE folder = ? AND id NOT IN (
                        SELECT id FROM messages WHERE folder = ?
                        ORDER BY received_at DESC LIMIT ?
                    )""",
                    (folder, folder, max_per_folder),
                )
                deleted += cur.rowcount
            if deleted:
                self.conn.commit()
        return deleted

    def _decode(self, row: dict) -> dict:
        for field in ("to_addrs", "cc_addrs", "attachments"):
            if row.get(field):
                try:
                    row[field] = json.loads(row[field])
                except (json.JSONDecodeError, TypeError):
                    row[field] = []
        row["is_read"] = bool(row.get("is_read"))
        row["is_flagged"] = bool(row.get("is_flagged"))
        row["has_attachments"] = bool(row.get("has_attachments"))
        return row
