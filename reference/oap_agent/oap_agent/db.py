"""SQLite data layer for the OAP Agent service."""

from __future__ import annotations

import json
import math
import sqlite3
import struct
import threading
import uuid
from datetime import datetime


SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id         TEXT PRIMARY KEY,
    title      TEXT NOT NULL,
    model      TEXT NOT NULL DEFAULT 'qwen3:14b',
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
    model      TEXT NOT NULL DEFAULT 'qwen3:14b',
    enabled    INTEGER NOT NULL DEFAULT 1,
    incremental INTEGER NOT NULL DEFAULT 1,
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

CREATE TABLE IF NOT EXISTS agent_settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_facts (
    id              TEXT PRIMARY KEY,
    fact            TEXT NOT NULL UNIQUE,
    source_message  TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    last_referenced TEXT NOT NULL,
    reference_count INTEGER NOT NULL DEFAULT 1,
    pinned          INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS llm_usage (
    id              TEXT PRIMARY KEY,
    conversation_id TEXT REFERENCES conversations(id) ON DELETE CASCADE,
    message_id      TEXT,
    provider        TEXT NOT NULL,
    model           TEXT NOT NULL,
    input_tokens    INTEGER NOT NULL DEFAULT 0,
    output_tokens   INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_llm_usage_conversation ON llm_usage(conversation_id);
CREATE INDEX IF NOT EXISTS idx_llm_usage_created ON llm_usage(created_at);

CREATE TABLE IF NOT EXISTS notifications (
    id         TEXT PRIMARY KEY,
    type       TEXT NOT NULL,
    title      TEXT NOT NULL,
    body       TEXT NOT NULL DEFAULT '',
    source     TEXT,
    task_id    TEXT REFERENCES tasks(id) ON DELETE CASCADE,
    run_id     TEXT,
    priority   INTEGER NOT NULL DEFAULT 0,
    dismissed  INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_notifications_pending ON notifications(dismissed, created_at);
"""


_EMBEDDING_DIM = 768
_EMBEDDING_STRUCT = struct.Struct(f"<{_EMBEDDING_DIM}f")  # 3072 bytes


def _pack_embedding(vec: list[float]) -> bytes:
    """Pack a 768-dim float vector into a compact BLOB."""
    return _EMBEDDING_STRUCT.pack(*vec)


def _unpack_embedding(blob: bytes) -> list[float]:
    """Unpack a BLOB back to a list of floats."""
    return list(_EMBEDDING_STRUCT.unpack(blob))


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two vectors. Returns 0.0 on degenerate input."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


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
        self._migrate()
        self._seed_defaults()

    def _migrate(self):
        """Add columns that may be missing from older databases."""
        cols = {r[1] for r in self.conn.execute("PRAGMA table_info(user_facts)").fetchall()}
        if "pinned" not in cols:
            self.conn.execute("ALTER TABLE user_facts ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0")
            self.conn.commit()

        if "embedding" not in cols:
            self.conn.execute("ALTER TABLE user_facts ADD COLUMN embedding BLOB")
            self.conn.commit()

        task_cols = {r[1] for r in self.conn.execute("PRAGMA table_info(tasks)").fetchall()}
        if "incremental" not in task_cols:
            self.conn.execute("ALTER TABLE tasks ADD COLUMN incremental INTEGER NOT NULL DEFAULT 1")
            self.conn.commit()

    def _seed_defaults(self):
        """Insert default settings, adding any missing keys to existing databases."""
        defaults = {
            "persona_name": "",
            "persona_description": "",
            "memory_enabled": "false",
            "voice_input_enabled": "true",
            "voice_auto_send": "false",
            "voice_auto_speak": "false",
            "voice_tts_voice": "",
            "voice_wake_word": "",
        }
        for key, value in defaults.items():
            self.conn.execute(
                "INSERT OR IGNORE INTO agent_settings (key, value) VALUES (?, ?)",
                (key, value),
            )
            self.conn.commit()

    def close(self):
        self.conn.close()

    # --- Conversations ---

    def create_conversation(self, title: str = "New Conversation", model: str = "qwen3:14b") -> dict:
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
        model: str = "qwen3:14b",
        incremental: bool = True,
    ) -> dict:
        task_id = _new_id("task_")
        now = _now()
        with self._lock:
            self.conn.execute(
                """INSERT INTO tasks (id, name, prompt, schedule, model, enabled, incremental, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?)""",
                (task_id, name, prompt, schedule, model, int(incremental), now, now),
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
        t["incremental"] = bool(t.get("incremental", 1))
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
            t["incremental"] = bool(t.get("incremental", 1))
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
        incremental: bool | None = None,
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
        if incremental is not None:
            fields.append("incremental = ?")
            values.append(1 if incremental else 0)
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

    def get_last_successful_run(self, task_id: str) -> dict | None:
        """Return the most recent successful run for a task, or None."""
        row = self.conn.execute(
            """SELECT * FROM task_runs
               WHERE task_id = ? AND status = 'success'
               ORDER BY finished_at DESC LIMIT 1""",
            (task_id,),
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

    def get_recent_successful_runs(self, since: str) -> list[dict]:
        """Return successful task runs finished after *since* (ISO timestamp)."""
        rows = self.conn.execute(
            """SELECT tr.*, t.name AS task_name
               FROM task_runs tr
               JOIN tasks t ON t.id = tr.task_id
               WHERE tr.status = 'success' AND tr.finished_at >= ? AND t.enabled = 1
               ORDER BY tr.finished_at DESC""",
            (since,),
        ).fetchall()
        return [self._decode_run(dict(r)) for r in rows]

    def cleanup_old_runs(self, max_per_task: int = 100) -> int:
        """Delete task runs beyond the newest *max_per_task* per task.

        Returns total number of rows deleted.
        """
        task_ids = [
            row[0] for row in self.conn.execute("SELECT DISTINCT task_id FROM task_runs").fetchall()
        ]
        deleted = 0
        with self._lock:
            for tid in task_ids:
                cur = self.conn.execute(
                    """DELETE FROM task_runs WHERE task_id = ? AND id NOT IN (
                           SELECT id FROM task_runs WHERE task_id = ?
                           ORDER BY started_at DESC LIMIT ?
                       )""",
                    (tid, tid, max_per_task),
                )
                deleted += cur.rowcount
            if deleted:
                self.conn.commit()
        return deleted

    def _decode_run(self, row: dict) -> dict:
        if row.get("tool_calls"):
            row["tool_calls"] = json.loads(row["tool_calls"])
        return row

    # --- Settings ---

    def get_settings(self) -> dict:
        """Return all agent settings as a key-value dict."""
        rows = self.conn.execute("SELECT key, value FROM agent_settings").fetchall()
        return {row["key"]: row["value"] for row in rows}

    def set_setting(self, key: str, value: str) -> None:
        """Upsert a single agent setting."""
        with self._lock:
            self.conn.execute(
                "INSERT INTO agent_settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
            self.conn.commit()

    # --- LLM Usage ---

    def record_llm_usage(
        self,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        conversation_id: str | None = None,
        message_id: str | None = None,
    ) -> dict:
        usage_id = _new_id("usage_")
        now = _now()
        with self._lock:
            self.conn.execute(
                """INSERT INTO llm_usage
                   (id, conversation_id, message_id, provider, model, input_tokens, output_tokens, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (usage_id, conversation_id, message_id, provider, model, input_tokens, output_tokens, now),
            )
            self.conn.commit()
        return {
            "id": usage_id,
            "provider": provider,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "created_at": now,
        }

    def get_usage_summary(self, days: int = 30) -> dict:
        """Get aggregated usage stats for the last N days."""
        from datetime import datetime, timedelta
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat() + "Z"

        rows = self.conn.execute(
            """SELECT provider, model,
                      COUNT(*) as requests,
                      SUM(input_tokens) as total_input,
                      SUM(output_tokens) as total_output
               FROM llm_usage
               WHERE created_at >= ?
               GROUP BY provider, model
               ORDER BY total_output DESC""",
            (cutoff,),
        ).fetchall()

        total_input = 0
        total_output = 0
        by_model: list[dict] = []
        for r in rows:
            entry = {
                "provider": r["provider"],
                "model": r["model"],
                "requests": r["requests"],
                "input_tokens": r["total_input"],
                "output_tokens": r["total_output"],
            }
            by_model.append(entry)
            total_input += r["total_input"]
            total_output += r["total_output"]

        return {
            "period_days": days,
            "total_requests": sum(m["requests"] for m in by_model),
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "by_model": by_model,
        }

    # --- User Facts ---

    def get_all_facts(self) -> list[dict]:
        """Return all user facts ordered by pinned DESC, reference_count DESC."""
        rows = self.conn.execute(
            "SELECT * FROM user_facts ORDER BY pinned DESC, reference_count DESC"
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d.pop("embedding", None)  # Don't leak BLOBs to callers
            result.append(d)
        return result

    def add_facts(self, facts: list[str], source_message: str, max_facts: int = 500) -> int:
        """Insert new facts with UNIQUE dedup, evict excess unpinned. Returns count added."""
        import sqlite3 as _sqlite3
        now = _now()
        added = 0
        with self._lock:
            for fact in facts:
                fact = fact.strip()
                if not fact:
                    continue
                try:
                    self.conn.execute(
                        "INSERT INTO user_facts (id, fact, source_message, created_at, "
                        "last_referenced, reference_count, pinned) VALUES (?, ?, ?, ?, ?, 1, 0)",
                        (_new_id("fact_"), fact, source_message[:500], now, now),
                    )
                    added += 1
                except _sqlite3.IntegrityError:
                    pass  # duplicate fact
            if added:
                self.conn.commit()
                # Only evict unpinned facts
                unpinned = self.conn.execute(
                    "SELECT COUNT(*) FROM user_facts WHERE pinned = 0"
                ).fetchone()[0]
                if unpinned > max_facts:
                    excess = unpinned - max_facts
                    self.conn.execute(
                        "DELETE FROM user_facts WHERE id IN ("
                        "  SELECT id FROM user_facts WHERE pinned = 0 "
                        "  ORDER BY reference_count ASC, last_referenced ASC "
                        "  LIMIT ?"
                        ")",
                        (excess,),
                    )
                    self.conn.commit()
        return added

    def pin_fact(self, fact_id: str, pinned: bool = True) -> bool:
        """Pin or unpin a user fact. Returns True if updated."""
        with self._lock:
            cur = self.conn.execute(
                "UPDATE user_facts SET pinned = ? WHERE id = ?",
                (1 if pinned else 0, fact_id),
            )
            self.conn.commit()
        return cur.rowcount > 0

    def update_fact(self, fact_id: str, new_text: str) -> bool:
        """Update fact text by ID. Clears embedding so it gets re-embedded. Returns True if updated."""
        new_text = new_text.strip()
        if not new_text:
            return False
        now = _now()
        with self._lock:
            cur = self.conn.execute(
                "UPDATE user_facts SET fact = ?, last_referenced = ?, embedding = NULL WHERE id = ?",
                (new_text, now, fact_id),
            )
            self.conn.commit()
        return cur.rowcount > 0

    def delete_fact(self, fact_id: str) -> bool:
        """Delete a user fact by ID. Returns True if deleted."""
        with self._lock:
            cur = self.conn.execute("DELETE FROM user_facts WHERE id = ?", (fact_id,))
            self.conn.commit()
        return cur.rowcount > 0

    def touch_facts(self, fact_ids: list[str]) -> None:
        """Bump reference_count and last_referenced for the given fact IDs."""
        now = _now()
        with self._lock:
            for fid in fact_ids:
                self.conn.execute(
                    "UPDATE user_facts SET reference_count = reference_count + 1, "
                    "last_referenced = ? WHERE id = ?",
                    (now, fid),
                )
            self.conn.commit()

    def count_facts(self) -> int:
        """Total number of stored user facts."""
        return self.conn.execute("SELECT COUNT(*) FROM user_facts").fetchone()[0]

    def set_embedding(self, fact_id: str, embedding: list[float]) -> bool:
        """Store an embedding BLOB for a single fact. Returns True if updated."""
        blob = _pack_embedding(embedding)
        with self._lock:
            cur = self.conn.execute(
                "UPDATE user_facts SET embedding = ? WHERE id = ?", (blob, fact_id)
            )
            self.conn.commit()
        return cur.rowcount > 0

    def set_embeddings_batch(self, pairs: list[tuple[str, list[float]]]) -> int:
        """Store embeddings for multiple facts in one transaction. Returns count updated."""
        updated = 0
        with self._lock:
            for fact_id, embedding in pairs:
                blob = _pack_embedding(embedding)
                cur = self.conn.execute(
                    "UPDATE user_facts SET embedding = ? WHERE id = ?", (blob, fact_id)
                )
                updated += cur.rowcount
            self.conn.commit()
        return updated

    def get_facts_without_embeddings(self) -> list[dict]:
        """Return facts that have no embedding (NULL)."""
        rows = self.conn.execute(
            "SELECT id, fact FROM user_facts WHERE embedding IS NULL"
        ).fetchall()
        return [dict(r) for r in rows]

    def search_facts(
        self, query_embedding: list[float], top_k: int = 10, min_similarity: float = 0.3
    ) -> list[dict]:
        """Cosine similarity search over embedded facts.

        Pinned facts are ALWAYS included regardless of similarity score.
        Returns pinned facts first, then top-K learned facts above min_similarity.
        """
        rows = self.conn.execute(
            "SELECT * FROM user_facts WHERE embedding IS NOT NULL OR pinned = 1"
        ).fetchall()

        pinned: list[dict] = []
        scored: list[tuple[float, dict]] = []

        for row in rows:
            fact = dict(row)
            if fact.get("pinned"):
                pinned.append(fact)
                continue
            blob = fact.get("embedding")
            if not blob:
                continue
            vec = _unpack_embedding(blob)
            sim = _cosine_similarity(query_embedding, vec)
            if sim >= min_similarity:
                scored.append((sim, fact))

        scored.sort(key=lambda x: x[0], reverse=True)
        top_learned = [f for _, f in scored[:top_k]]

        # Strip embedding BLOBs from results
        for f in pinned + top_learned:
            f.pop("embedding", None)

        return pinned + top_learned

    # --- Notifications ---

    def add_notification(
        self,
        type: str,
        title: str,
        body: str = "",
        source: str | None = None,
        task_id: str | None = None,
        run_id: str | None = None,
        priority: int = 0,
    ) -> dict:
        """Create a notification. Returns the notification dict."""
        nid = _new_id("notif_")
        now = _now()
        with self._lock:
            self.conn.execute(
                """INSERT INTO notifications
                   (id, type, title, body, source, task_id, run_id, priority, dismissed, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?)""",
                (nid, type, title, body, source, task_id, run_id, priority, now),
            )
            self.conn.commit()
        return {
            "id": nid, "type": type, "title": title, "body": body,
            "source": source, "task_id": task_id, "run_id": run_id,
            "priority": priority, "dismissed": False, "created_at": now,
        }

    def get_pending_notifications(self, limit: int = 50) -> list[dict]:
        """Return undismissed notifications, newest first."""
        rows = self.conn.execute(
            "SELECT * FROM notifications WHERE dismissed = 0 ORDER BY priority DESC, created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [self._decode_notification(dict(r)) for r in rows]

    def count_pending_notifications(self) -> int:
        return self.conn.execute(
            "SELECT COUNT(*) FROM notifications WHERE dismissed = 0"
        ).fetchone()[0]

    def dismiss_notification(self, notif_id: str) -> bool:
        with self._lock:
            cur = self.conn.execute(
                "UPDATE notifications SET dismissed = 1 WHERE id = ?", (notif_id,)
            )
            self.conn.commit()
        return cur.rowcount > 0

    def dismiss_all_notifications(self) -> int:
        with self._lock:
            cur = self.conn.execute("UPDATE notifications SET dismissed = 1 WHERE dismissed = 0")
            self.conn.commit()
        return cur.rowcount

    def cleanup_notifications(self, days: int = 7) -> int:
        """Delete dismissed notifications older than N days."""
        from datetime import timedelta
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat() + "Z"
        with self._lock:
            cur = self.conn.execute(
                "DELETE FROM notifications WHERE dismissed = 1 AND created_at < ?", (cutoff,)
            )
            self.conn.commit()
        return cur.rowcount

    def _decode_notification(self, row: dict) -> dict:
        row["dismissed"] = bool(row.get("dismissed"))
        return row
