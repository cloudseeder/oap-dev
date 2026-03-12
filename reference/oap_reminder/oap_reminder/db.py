"""SQLite database for reminders."""

from __future__ import annotations

import calendar
import logging
import sqlite3
import threading
from datetime import date, datetime, timedelta

log = logging.getLogger("oap.reminder.db")

_SCHEMA = """\
CREATE TABLE IF NOT EXISTS reminders (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    title        TEXT NOT NULL,
    notes        TEXT,
    created_at   TEXT NOT NULL,
    due_date     TEXT,
    due_time     TEXT,
    recurring    TEXT,
    status       TEXT NOT NULL DEFAULT 'pending',
    completed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_reminders_status ON reminders(status);
CREATE INDEX IF NOT EXISTS idx_reminders_due ON reminders(due_date);
"""


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def _today() -> str:
    return date.today().isoformat()


def _next_due(due_date: str, recurring: str) -> str:
    """Compute the next due date given a recurrence pattern."""
    d = date.fromisoformat(due_date)
    if recurring == "daily":
        d += timedelta(days=1)
    elif recurring == "weekly":
        d += timedelta(weeks=1)
    elif recurring == "monthly":
        month = d.month % 12 + 1
        year = d.year + (1 if d.month == 12 else 0)
        day = min(d.day, calendar.monthrange(year, month)[1])
        d = d.replace(year=year, month=month, day=day)
    elif recurring == "yearly":
        year = d.year + 1
        day = min(d.day, calendar.monthrange(year, d.month)[1])
        d = d.replace(year=year, day=day)
    return d.isoformat()


class ReminderDB:
    def __init__(self, path: str = "oap_reminder.db"):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._lock = threading.Lock()
        self.conn.executescript(_SCHEMA)
        log.info("Database opened: %s", path)

    def close(self) -> None:
        self.conn.close()

    def create(
        self,
        title: str,
        notes: str | None = None,
        due_date: str | None = None,
        due_time: str | None = None,
        recurring: str | None = None,
    ) -> dict:
        now = _now()
        with self._lock:
            cur = self.conn.execute(
                """INSERT INTO reminders (title, notes, created_at, due_date, due_time, recurring)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (title, notes, now, due_date, due_time, recurring),
            )
            self.conn.commit()
        return self.get(cur.lastrowid)

    def get(self, reminder_id: int) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM reminders WHERE id = ?", (reminder_id,)
        ).fetchone()
        return dict(row) if row else None

    def find_by_title(self, title: str, status: str = "pending") -> dict | None:
        """Find a reminder by case-insensitive substring match on title or notes."""
        row = self.conn.execute(
            "SELECT * FROM reminders WHERE (title LIKE ? OR notes LIKE ?) AND status = ? ORDER BY id DESC LIMIT 1",
            (f"%{title}%", f"%{title}%", status),
        ).fetchone()
        return dict(row) if row else None

    def update(self, reminder_id: int, **fields) -> dict | None:
        if not fields:
            return self.get(reminder_id)
        sets = ", ".join(f"{k} = ?" for k in fields)
        vals = list(fields.values()) + [reminder_id]
        with self._lock:
            self.conn.execute(
                f"UPDATE reminders SET {sets} WHERE id = ?", vals,
            )
            self.conn.commit()
        return self.get(reminder_id)

    def delete(self, reminder_id: int) -> bool:
        with self._lock:
            cur = self.conn.execute(
                "DELETE FROM reminders WHERE id = ?", (reminder_id,)
            )
            self.conn.commit()
        return cur.rowcount > 0

    def complete(self, reminder_id: int) -> dict:
        """Mark a reminder complete. If recurring, create the next occurrence."""
        reminder = self.get(reminder_id)
        if not reminder:
            return None
        now = _now()
        with self._lock:
            self.conn.execute(
                "UPDATE reminders SET status = 'completed', completed_at = ? WHERE id = ?",
                (now, reminder_id),
            )
            self.conn.commit()

        result = self.get(reminder_id)

        # If recurring, schedule the next one
        if reminder["recurring"] and reminder["due_date"]:
            next_date = _next_due(reminder["due_date"], reminder["recurring"])
            next_reminder = self.create(
                title=reminder["title"],
                notes=reminder["notes"],
                due_date=next_date,
                due_time=reminder["due_time"],
                recurring=reminder["recurring"],
            )
            result["next"] = next_reminder

        return result

    def list_all(
        self,
        status: str | None = None,
        due_date: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        clauses: list[str] = []
        params: list = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if due_date:
            clauses.append("due_date = ?")
            params.append(due_date)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""

        total = self.conn.execute(
            f"SELECT COUNT(*) FROM reminders {where}", params,
        ).fetchone()[0]

        rows = self.conn.execute(
            f"SELECT * FROM reminders {where} ORDER BY due_date ASC, due_time ASC LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
        return [dict(r) for r in rows], total

    def list_due(self, before: str | None = None) -> list[dict]:
        """List pending reminders due on or before a date (default: today)."""
        before = before or _today()
        rows = self.conn.execute(
            """SELECT * FROM reminders
               WHERE status = 'pending' AND due_date IS NOT NULL AND due_date <= ?
               ORDER BY due_date ASC, due_time ASC""",
            (before,),
        ).fetchall()
        return [dict(r) for r in rows]

    def cleanup_completed(self, older_than_days: int = 30) -> int:
        """Delete completed reminders older than N days. Returns count deleted."""
        cutoff = (date.today() - timedelta(days=older_than_days)).isoformat()
        with self._lock:
            cur = self.conn.execute(
                """DELETE FROM reminders
                   WHERE status = 'completed' AND completed_at IS NOT NULL
                   AND completed_at < ?""",
                (cutoff,),
            )
            self.conn.commit()
        deleted = cur.rowcount
        if deleted:
            log.info("Cleaned up %d completed reminders older than %d days", deleted, older_than_days)
        return deleted
