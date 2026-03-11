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
    cached_at   TEXT,
    category    TEXT
);

CREATE INDEX IF NOT EXISTS idx_messages_received ON messages(received_at);
CREATE INDEX IF NOT EXISTS idx_messages_folder ON messages(folder);
CREATE INDEX IF NOT EXISTS idx_messages_thread ON messages(thread_id);
CREATE INDEX IF NOT EXISTS idx_messages_uid ON messages(folder, uid);
CREATE INDEX IF NOT EXISTS idx_messages_category ON messages(category);
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
        self._migrate()
        self._lock = threading.Lock()
        log.info("Email DB opened: %s", db_path)

    def _migrate(self):
        cols = {r[1] for r in self.conn.execute("PRAGMA table_info(messages)").fetchall()}
        if "category" not in cols:
            self.conn.execute("ALTER TABLE messages ADD COLUMN category TEXT")
            self.conn.commit()

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
        category: str | None = None,
        limit: int = 20,
    ) -> list[dict]:
        conditions = ["folder = ?"]
        params: list = [folder]
        if since:
            conditions.append("received_at >= ?")
            params.append(since)
        if unread:
            conditions.append("is_read = 0")
        if category:
            conditions.append("category = ?")
            params.append(category.lower())
        if query:
            query_sql, query_params = self._parse_query(query)
            conditions.append(query_sql)
            params.extend(query_params)

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

    def get_uncategorized(self, limit: int = 50) -> list[dict]:
        """Return messages without a category."""
        rows = self.conn.execute(
            "SELECT id, from_name, from_email, subject, snippet FROM messages "
            "WHERE category IS NULL ORDER BY received_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def set_category(self, msg_id: str, category: str) -> None:
        with self._lock:
            self.conn.execute(
                "UPDATE messages SET category = ? WHERE id = ?",
                (category, msg_id),
            )
            self.conn.commit()

    # ------------------------------------------------------------------
    # Query parser — supports OR, field prefixes (from:, subject:, body:)
    # ------------------------------------------------------------------

    _FIELD_MAP = {
        "from": ["from_name", "from_email"],
        "sender": ["from_name", "from_email"],
        "to": ["to_addrs"],
        "subject": ["subject"],
        "body": ["body_text"],
    }

    def _parse_query(self, query: str) -> tuple[str, list[str]]:
        """Parse a query string with OR support and field prefixes.

        Examples:
            "Amy Brooks OR Keric Brooks"
            "from:amy@netgate.net"
            "from:Amy subject:car"
            "FROM Amy Brooks OR FROM Kai Brooks"
        """
        import re

        # Split on OR (case-insensitive, surrounded by whitespace)
        or_groups = re.split(r"\s+OR\s+", query, flags=re.IGNORECASE)

        or_clauses = []
        params: list[str] = []

        for group in or_groups:
            group = group.strip()
            if not group:
                continue

            # Extract field-prefixed terms: "from:value" or "FROM value"
            # Also handle "SUBJECT value", "BODY value" etc.
            and_clauses = []
            remaining = group

            # Match prefix:value (colon style)
            for match in re.finditer(r"(\w+):(\S+)", group):
                field_key = match.group(1).lower()
                value = match.group(2)
                columns = self._FIELD_MAP.get(field_key)
                if columns:
                    col_likes = " OR ".join(f"{c} LIKE ?" for c in columns)
                    and_clauses.append(f"({col_likes})")
                    params.extend([f"%{value}%"] * len(columns))
                    remaining = remaining.replace(match.group(0), "", 1)

            # Match PREFIX word... (space style, e.g. "FROM Amy Brooks")
            prefix_match = re.match(
                r"(from|sender|to|subject|body)\s+(.+)",
                remaining.strip(),
                re.IGNORECASE,
            )
            if prefix_match:
                field_key = prefix_match.group(1).lower()
                value = prefix_match.group(2).strip()
                columns = self._FIELD_MAP.get(field_key)
                if columns and value:
                    col_likes = " OR ".join(f"{c} LIKE ?" for c in columns)
                    and_clauses.append(f"({col_likes})")
                    params.extend([f"%{value}%"] * len(columns))
                    remaining = ""

            # Anything left is a general search across all fields
            remaining = remaining.strip()
            if remaining:
                and_clauses.append(
                    "(subject LIKE ? OR from_name LIKE ? OR from_email LIKE ? OR body_text LIKE ?)"
                )
                params.extend([f"%{remaining}%"] * 4)

            if and_clauses:
                or_clauses.append("(" + " AND ".join(and_clauses) + ")")

        if not or_clauses:
            return "1=1", []

        return "(" + " OR ".join(or_clauses) + ")", params

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
