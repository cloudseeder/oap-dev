"""SQLite data layer for the OAP Agent service."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime


SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id         TEXT PRIMARY KEY,
    title      TEXT NOT NULL,
    model      TEXT NOT NULL DEFAULT 'qwen3:8b',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id              TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT NOT NULL,
    content         TEXT NOT NULL DEFAULT '',
    tool_calls      TEXT,
    metadata        TEXT,
    created_at      TEXT NOT NULL,
    seq             INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    prompt     TEXT NOT NULL,
    schedule   TEXT,
    model      TEXT NOT NULL DEFAULT 'qwen3:8b',
    enabled    INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS task_runs (
    id          TEXT PRIMARY KEY,
    task_id     TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    started_at  TEXT NOT NULL,
    finished_at TEXT,
    status      TEXT NOT NULL DEFAULT 'running',
    prompt      TEXT NOT NULL,
    response    TEXT,
    tool_calls  TEXT,
    error       TEXT,
    duration_ms INTEGER
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_task_runs_task ON task_runs(task_id);
"""


def _new_id(prefix: str) -> str:
    return prefix + uuid.uuid4().hex[:12]


def _now() -> str:
    return datetime.utcnow().isoformat() + "Z"


class AgentDB:
    def __init__(self, db_path: str = "oap_agent.db"):
        self.db_path = db_path
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript(SCHEMA)

    def close(self):
        self.conn.close()

    # --- Conversations ---

    def create_conversation(self, title: str = "New Conversation", model: str = "qwen3:8b") -> dict:
        conv_id = _new_id("conv_")
        now = _now()
        with self._lock:
            self.conn.execute(
                "INSERT INTO conversations (id, title, model, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (conv_id, title, model, now, now),
            )
            self.conn.commit()
        return self.get_conversation(conv_id)

    def get_conversation(self, conv_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM conversations WHERE id = ?", (conv_id,)
        ).fetchone()
        return dict(row) if row else None

    def list_conversations(self, page: int = 1, limit: int = 50) -> dict:
        page = max(1, page)
        limit = min(max(1, limit), 200)
        offset = (page - 1) * limit
        total = self.conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
        rows = self.conn.execute(
            "SELECT * FROM conversations ORDER BY updated_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        return {
            "conversations": [dict(r) for r in rows],
            "total": total,
            "page": page,
            "limit": limit,
        }

    def update_conversation(self, conv_id: str, title: str | None = None, model: str | None = None) -> dict | None:
        now = _now()
        with self._lock:
            if title is not None and model is not None:
                self.conn.execute(
                    "UPDATE conversations SET title = ?, model = ?, updated_at = ? WHERE id = ?",
                    (title, model, now, conv_id),
                )
            elif title is not None:
                self.conn.execute(
                    "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
                    (title, now, conv_id),
                )
            elif model is not None:
                self.conn.execute(
                    "UPDATE conversations SET model = ?, updated_at = ? WHERE id = ?",
                    (model, now, conv_id),
                )
            else:
                return self.get_conversation(conv_id)
            self.conn.commit()
        return self.get_conversation(conv_id)

    def delete_conversation(self, conv_id: str) -> bool:
        with self._lock:
            cur = self.conn.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
            self.conn.commit()
        return cur.rowcount > 0

    def touch_conversation(self, conv_id: str):
        with self._lock:
            self.conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?", (_now(), conv_id)
            )
            self.conn.commit()

    # --- Messages ---

    def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str = "",
        tool_calls: list | None = None,
        metadata: dict | None = None,
    ) -> dict:
        msg_id = _new_id("msg_")
        now = _now()
        with self._lock:
            seq = self._next_seq(conversation_id)
            self.conn.execute(
                """INSERT INTO messages
                   (id, conversation_id, role, content, tool_calls, metadata, created_at, seq)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    msg_id,
                    conversation_id,
                    role,
                    content,
                    json.dumps(tool_calls) if tool_calls is not None else None,
                    json.dumps(metadata) if metadata is not None else None,
                    now,
                    seq,
                ),
            )
            self.conn.commit()
        self.touch_conversation(conversation_id)
        return self.get_message(msg_id)

    def get_message(self, msg_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM messages WHERE id = ?", (msg_id,)
        ).fetchone()
        if not row:
            return None
        return self._decode_message(dict(row))

    def get_messages(self, conversation_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM messages WHERE conversation_id = ? ORDER BY seq ASC",
            (conversation_id,),
        ).fetchall()
        return [self._decode_message(dict(r)) for r in rows]

    def _next_seq(self, conversation_id: str) -> int:
        row = self.conn.execute(
            "SELECT COALESCE(MAX(seq), -1) FROM messages WHERE conversation_id = ?",
            (conversation_id,),
        ).fetchone()
        return row[0] + 1

    def _decode_message(self, row: dict) -> dict:
        if row.get("tool_calls"):
            row["tool_calls"] = json.loads(row["tool_calls"])
        if row.get("metadata"):
            row["metadata"] = json.loads(row["metadata"])
        return row

    # --- Tasks ---

    def create_task(
        self,
        name: str,
        prompt: str,
        schedule: str | None = None,
        model: str = "qwen3:8b",
    ) -> dict:
        task_id = _new_id("task_")
        now = _now()
        with self._lock:
            self.conn.execute(
                """INSERT INTO tasks (id, name, prompt, schedule, model, enabled, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, 1, ?, ?)""",
                (task_id, name, prompt, schedule, model, now, now),
            )
            self.conn.commit()
        return self.get_task(task_id)

    def get_task(self, task_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
        if not row:
            return None
        t = dict(row)
        t["enabled"] = bool(t["enabled"])
        return t

    def list_tasks(self) -> list[dict]:
        rows = self.conn.execute(
            """SELECT t.*,
                      lr.status      AS last_run_status,
                      lr.finished_at AS last_run_at,
                      lr.error       AS last_run_error
               FROM tasks t
               LEFT JOIN (
                   SELECT task_id, status, finished_at, error,
                          ROW_NUMBER() OVER (PARTITION BY task_id ORDER BY started_at DESC) AS rn
                   FROM task_runs
               ) lr ON lr.task_id = t.id AND lr.rn = 1
               ORDER BY t.created_at DESC"""
        ).fetchall()
        result = []
        for r in rows:
            t = dict(r)
            t["enabled"] = bool(t["enabled"])
            result.append(t)
        return result

    def update_task(
        self,
        task_id: str,
        name: str | None = None,
        prompt: str | None = None,
        schedule: str | None = None,
        model: str | None = None,
        enabled: bool | None = None,
    ) -> dict | None:
        now = _now()
        # Build explicit SET clause from provided fields
        fields: list[str] = []
        values: list = []
        if name is not None:
            fields.append("name = ?")
            values.append(name)
        if prompt is not None:
            fields.append("prompt = ?")
            values.append(prompt)
        if schedule is not None:
            fields.append("schedule = ?")
            values.append(schedule)
        if model is not None:
            fields.append("model = ?")
            values.append(model)
        if enabled is not None:
            fields.append("enabled = ?")
            values.append(1 if enabled else 0)
        if not fields:
            return self.get_task(task_id)
        fields.append("updated_at = ?")
        values.append(now)
        values.append(task_id)
        with self._lock:
            self.conn.execute(
                f"UPDATE tasks SET {', '.join(fields)} WHERE id = ?", values
            )
            self.conn.commit()
        return self.get_task(task_id)

    def delete_task(self, task_id: str) -> bool:
        with self._lock:
            cur = self.conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            self.conn.commit()
        return cur.rowcount > 0

    # --- Task Runs ---

    def create_run(self, task_id: str, prompt: str) -> dict:
        run_id = _new_id("run_")
        now = _now()
        with self._lock:
            self.conn.execute(
                """INSERT INTO task_runs (id, task_id, started_at, status, prompt)
                   VALUES (?, ?, ?, 'running', ?)""",
                (run_id, task_id, now, prompt),
            )
            self.conn.commit()
        return self.get_run(run_id)

    def finish_run(
        self,
        run_id: str,
        status: str,
        response: str | None = None,
        tool_calls: list | None = None,
        error: str | None = None,
        duration_ms: int | None = None,
    ) -> dict | None:
        now = _now()
        with self._lock:
            self.conn.execute(
                """UPDATE task_runs SET
                   finished_at = ?, status = ?, response = ?, tool_calls = ?, error = ?, duration_ms = ?
                   WHERE id = ?""",
                (
                    now,
                    status,
                    response,
                    json.dumps(tool_calls) if tool_calls is not None else None,
                    error,
                    duration_ms,
                    run_id,
                ),
            )
            self.conn.commit()
        return self.get_run(run_id)

    def get_run(self, run_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM task_runs WHERE id = ?", (run_id,)
        ).fetchone()
        if not row:
            return None
        return self._decode_run(dict(row))

    def list_runs(self, task_id: str, page: int = 1, limit: int = 20) -> dict:
        page = max(1, page)
        limit = min(max(1, limit), 200)
        offset = (page - 1) * limit
        total = self.conn.execute(
            "SELECT COUNT(*) FROM task_runs WHERE task_id = ?", (task_id,)
        ).fetchone()[0]
        rows = self.conn.execute(
            "SELECT * FROM task_runs WHERE task_id = ? ORDER BY started_at DESC LIMIT ? OFFSET ?",
            (task_id, limit, offset),
        ).fetchall()
        return {
            "runs": [self._decode_run(dict(r)) for r in rows],
            "total": total,
            "page": page,
            "limit": limit,
        }

    def _decode_run(self, row: dict) -> dict:
        if row.get("tool_calls"):
            row["tool_calls"] = json.loads(row["tool_calls"])
        return row
