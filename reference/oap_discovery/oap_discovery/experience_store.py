"""SQLite store for procedural memory experience records."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from .experience_models import (
    CorrectionEntry,
    DiscoveryRecord,
    ExperienceRecord,
    IntentRecord,
    InvocationRecord,
    OutcomeRecord,
    ParameterMapping,
)

SCHEMA = """\
CREATE TABLE IF NOT EXISTS experiences (
    id              TEXT PRIMARY KEY,
    timestamp       TEXT NOT NULL,
    use_count       INTEGER NOT NULL DEFAULT 1,
    last_used       TEXT NOT NULL,

    -- Intent
    intent_raw          TEXT NOT NULL,
    intent_fingerprint  TEXT NOT NULL,
    intent_domain       TEXT NOT NULL,

    -- Discovery
    discovery_query         TEXT NOT NULL,
    manifest_matched        TEXT NOT NULL,
    manifest_version        TEXT,
    confidence              REAL NOT NULL,

    -- Invocation (JSON for flexibility)
    invocation_json TEXT NOT NULL,

    -- Outcome
    outcome_status      TEXT NOT NULL,
    outcome_http_code   INTEGER,
    outcome_summary     TEXT NOT NULL,
    outcome_latency_ms  INTEGER,

    -- Corrections (JSON array)
    corrections_json    TEXT NOT NULL DEFAULT '[]'
);

CREATE INDEX IF NOT EXISTS idx_exp_fingerprint ON experiences(intent_fingerprint);
CREATE INDEX IF NOT EXISTS idx_exp_domain ON experiences(intent_domain);
CREATE INDEX IF NOT EXISTS idx_exp_manifest ON experiences(manifest_matched);
CREATE INDEX IF NOT EXISTS idx_exp_use_count ON experiences(use_count DESC);
CREATE INDEX IF NOT EXISTS idx_exp_last_used ON experiences(last_used DESC);
CREATE INDEX IF NOT EXISTS idx_exp_confidence ON experiences(confidence DESC);
"""


class ExperienceStore:
    """SQLite persistence for procedural memory experience records."""

    def __init__(self, db_path: str) -> None:
        self._db = sqlite3.connect(db_path)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.executescript(SCHEMA)

    def close(self) -> None:
        self._db.close()

    def save(self, record: ExperienceRecord) -> None:
        """Insert or replace an experience record."""
        invocation_json = json.dumps(record.invocation.model_dump())
        corrections_json = json.dumps(
            [c.model_dump() for c in record.corrections]
        )
        self._db.execute(
            """INSERT OR REPLACE INTO experiences (
                id, timestamp, use_count, last_used,
                intent_raw, intent_fingerprint, intent_domain,
                discovery_query, manifest_matched, manifest_version, confidence,
                invocation_json,
                outcome_status, outcome_http_code, outcome_summary, outcome_latency_ms,
                corrections_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record.id,
                record.timestamp.isoformat(),
                record.use_count,
                record.last_used.isoformat(),
                record.intent.raw,
                record.intent.fingerprint,
                record.intent.domain,
                record.discovery.query_used,
                record.discovery.manifest_matched,
                record.discovery.manifest_version,
                record.discovery.confidence,
                invocation_json,
                record.outcome.status,
                record.outcome.http_code,
                record.outcome.response_summary,
                record.outcome.latency_ms,
                corrections_json,
            ),
        )
        self._db.commit()

    def get(self, experience_id: str) -> ExperienceRecord | None:
        """Fetch an experience record by ID."""
        row = self._db.execute(
            "SELECT * FROM experiences WHERE id = ?", (experience_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_record(row)

    def find_by_fingerprint(
        self, fingerprint: str, limit: int = 5
    ) -> list[ExperienceRecord]:
        """Find records with an exact fingerprint match."""
        rows = self._db.execute(
            """SELECT * FROM experiences
               WHERE intent_fingerprint = ?
               ORDER BY use_count DESC, last_used DESC
               LIMIT ?""",
            (fingerprint, limit),
        ).fetchall()
        return [self._row_to_record(r) for r in rows]

    def find_similar(
        self,
        intent_domain: str,
        fingerprint_prefix: str,
        limit: int = 5,
    ) -> list[ExperienceRecord]:
        """Find records with same domain and fingerprint prefix match."""
        rows = self._db.execute(
            """SELECT * FROM experiences
               WHERE intent_domain = ? AND intent_fingerprint LIKE ?
               ORDER BY use_count DESC, last_used DESC
               LIMIT ?""",
            (intent_domain, f"{fingerprint_prefix}%", limit),
        ).fetchall()
        return [self._row_to_record(r) for r in rows]

    def touch(self, experience_id: str) -> None:
        """Increment use_count and update last_used."""
        now = datetime.now(timezone.utc).isoformat()
        self._db.execute(
            """UPDATE experiences
               SET use_count = use_count + 1, last_used = ?
               WHERE id = ?""",
            (now, experience_id),
        )
        self._db.commit()

    def degrade_confidence(self, experience_id: str, factor: float = 0.7) -> float | None:
        """Multiply confidence by *factor* and mark outcome as failure.

        Returns the new confidence value, or None if the record was not found.
        Default factor 0.7: a single failure drops 0.90 → 0.63 (below the
        0.85 threshold), so the entry won't be served on the next cache hit.
        """
        row = self._db.execute(
            "SELECT confidence FROM experiences WHERE id = ?",
            (experience_id,),
        ).fetchone()
        if row is None:
            return None
        new_confidence = row["confidence"] * factor
        self._db.execute(
            """UPDATE experiences
               SET confidence = ?, outcome_status = 'failure'
               WHERE id = ?""",
            (new_confidence, experience_id),
        )
        self._db.commit()
        return new_confidence

    def list_all(
        self, page: int = 1, limit: int = 50
    ) -> dict[str, Any]:
        """Paginated listing of experience records."""
        offset = (page - 1) * limit
        rows = self._db.execute(
            """SELECT * FROM experiences
               ORDER BY last_used DESC
               LIMIT ? OFFSET ?""",
            (limit, offset),
        ).fetchall()
        total = self.count()
        return {
            "records": [self._row_to_record(r) for r in rows],
            "total": total,
            "page": page,
            "limit": limit,
        }

    def delete(self, experience_id: str) -> bool:
        """Delete an experience record. Returns True if a row was deleted."""
        cursor = self._db.execute(
            "DELETE FROM experiences WHERE id = ?", (experience_id,)
        )
        self._db.commit()
        return cursor.rowcount > 0

    def count(self) -> int:
        """Total number of experience records."""
        row = self._db.execute("SELECT COUNT(*) FROM experiences").fetchone()
        return row[0]

    def stats(self) -> dict[str, Any]:
        """Summary statistics for the experience store."""
        total = self.count()
        if total == 0:
            return {
                "total": 0,
                "avg_confidence": 0.0,
                "success_rate": 0.0,
                "top_domains": [],
                "top_manifests": [],
            }

        avg_conf = self._db.execute(
            "SELECT AVG(confidence) FROM experiences"
        ).fetchone()[0]

        success_count = self._db.execute(
            "SELECT COUNT(*) FROM experiences WHERE outcome_status = 'success'"
        ).fetchone()[0]

        top_domains = self._db.execute(
            """SELECT intent_domain, COUNT(*) as cnt
               FROM experiences GROUP BY intent_domain
               ORDER BY cnt DESC LIMIT 5"""
        ).fetchall()

        top_manifests = self._db.execute(
            """SELECT manifest_matched, COUNT(*) as cnt
               FROM experiences GROUP BY manifest_matched
               ORDER BY cnt DESC LIMIT 5"""
        ).fetchall()

        return {
            "total": total,
            "avg_confidence": round(avg_conf or 0.0, 4),
            "success_rate": round(success_count / total, 4) if total else 0.0,
            "top_domains": [
                {"domain": r["intent_domain"], "count": r["cnt"]}
                for r in top_domains
            ],
            "top_manifests": [
                {"manifest": r["manifest_matched"], "count": r["cnt"]}
                for r in top_manifests
            ],
        }

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> ExperienceRecord:
        """Convert a database row to an ExperienceRecord."""
        invocation_data = json.loads(row["invocation_json"])
        corrections_data = json.loads(row["corrections_json"])

        return ExperienceRecord(
            id=row["id"],
            timestamp=datetime.fromisoformat(row["timestamp"]),
            use_count=row["use_count"],
            last_used=datetime.fromisoformat(row["last_used"]),
            intent=IntentRecord(
                raw=row["intent_raw"],
                fingerprint=row["intent_fingerprint"],
                domain=row["intent_domain"],
            ),
            discovery=DiscoveryRecord(
                query_used=row["discovery_query"],
                manifest_matched=row["manifest_matched"],
                manifest_version=row["manifest_version"],
                confidence=row["confidence"],
            ),
            invocation=InvocationRecord(
                endpoint=invocation_data["endpoint"],
                method=invocation_data["method"],
                parameter_mapping={
                    k: ParameterMapping(**v)
                    for k, v in invocation_data.get("parameter_mapping", {}).items()
                },
                headers_required=invocation_data.get("headers_required", []),
            ),
            outcome=OutcomeRecord(
                status=row["outcome_status"],
                http_code=row["outcome_http_code"],
                response_summary=row["outcome_summary"],
                latency_ms=row["outcome_latency_ms"],
            ),
            corrections=[CorrectionEntry(**c) for c in corrections_data],
        )
