from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime
import csv
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterator

from referral_assistant.models import (
    AlertEvent,
    ComplianceEvidence,
    ComplianceStatus,
    DraftRecord,
    DraftStatus,
    GeminiDecision,
    KillSwitchState,
    Opportunity,
    Persona,
    VisibilityCheckResult,
)


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True)


def _json_loads(value: str | None) -> Any:
    if not value:
        return None
    return json.loads(value)


def _parse_datetime(value: str) -> datetime:
    if value.endswith("Z"):
        value = value.replace("Z", "+00:00")
    return datetime.fromisoformat(value)


class Database:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS lead_tracker (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    source_item_id TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    dedupe_key TEXT NOT NULL UNIQUE,
                    community_name TEXT NOT NULL,
                    author_name TEXT NOT NULL,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL,
                    keyword_hits_json TEXT NOT NULL,
                    thread_metadata_json TEXT NOT NULL,
                    discovered_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    compliance_status TEXT NOT NULL,
                    compliance_summary TEXT NOT NULL,
                    compliance_reason_codes_json TEXT NOT NULL,
                    compliance_evidence_json TEXT NOT NULL,
                    compliance_allow_matches_json TEXT NOT NULL,
                    compliance_deny_matches_json TEXT NOT NULL,
                    score REAL NOT NULL,
                    gemini_eligible INTEGER NOT NULL,
                    gemini_reason_codes_json TEXT NOT NULL,
                    chosen_persona TEXT NOT NULL,
                    disclosure_required INTEGER NOT NULL,
                    reply_text TEXT NOT NULL,
                    decision_confidence REAL NOT NULL,
                    decision_rationale TEXT NOT NULL,
                    status TEXT NOT NULL,
                    operator_notes TEXT NOT NULL DEFAULT '',
                    public_post_url TEXT NOT NULL DEFAULT '',
                    manual_published_at TEXT,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    level TEXT NOT NULL,
                    message TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS errors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    error_type TEXT NOT NULL,
                    message TEXT NOT NULL,
                    context_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS visibility_checks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    lead_id INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    checked_url TEXT NOT NULL,
                    expected_snippet TEXT NOT NULL,
                    details TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (lead_id) REFERENCES lead_tracker(id)
                );

                CREATE TABLE IF NOT EXISTS system_state (
                    key TEXT PRIMARY KEY,
                    value_text TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    updated_by TEXT NOT NULL
                );
                """
            )
            connection.execute(
                """
                INSERT INTO system_state (key, value_text, updated_at, updated_by)
                VALUES ('kill_switch', 'false', CURRENT_TIMESTAMP, 'system')
                ON CONFLICT(key) DO NOTHING
                """
            )

    def lead_exists(self, dedupe_key: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM lead_tracker WHERE dedupe_key = ?",
                (dedupe_key,),
            ).fetchone()
        return row is not None

    def save_draft_record(self, record: DraftRecord, score: float) -> int:
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT id FROM lead_tracker WHERE dedupe_key = ?",
                (record.opportunity.dedupe_key,),
            ).fetchone()

            payload = (
                record.opportunity.source,
                record.opportunity.source_item_id,
                record.opportunity.source_url,
                record.opportunity.dedupe_key,
                record.opportunity.community_name,
                record.opportunity.author_name,
                record.opportunity.title,
                record.opportunity.body,
                _json_dumps(record.opportunity.keyword_hits),
                _json_dumps(record.opportunity.thread_metadata),
                record.opportunity.discovered_at.isoformat(),
                record.opportunity.created_at.isoformat(),
                record.compliance.status.value,
                record.compliance.summary,
                _json_dumps(record.compliance.reason_codes),
                _json_dumps(record.compliance.evidence_lines),
                _json_dumps(record.compliance.allow_matches),
                _json_dumps(record.compliance.deny_matches),
                score,
                int(record.decision.eligible),
                _json_dumps(record.decision.reason_codes),
                record.decision.chosen_persona.value,
                int(record.decision.disclosure_required),
                record.decision.reply_text,
                record.decision.confidence,
                record.decision.rationale,
                record.status.value,
                record.operator_notes,
                record.public_post_url,
                record.updated_at.isoformat(),
            )

            if existing:
                connection.execute(
                    """
                    UPDATE lead_tracker
                    SET source = ?, source_item_id = ?, source_url = ?, community_name = ?,
                        author_name = ?, title = ?, body = ?, keyword_hits_json = ?,
                        thread_metadata_json = ?, discovered_at = ?, created_at = ?,
                        compliance_status = ?, compliance_summary = ?,
                        compliance_reason_codes_json = ?, compliance_evidence_json = ?,
                        compliance_allow_matches_json = ?, compliance_deny_matches_json = ?,
                        score = ?, gemini_eligible = ?, gemini_reason_codes_json = ?,
                        chosen_persona = ?, disclosure_required = ?, reply_text = ?,
                        decision_confidence = ?, decision_rationale = ?, status = ?,
                        operator_notes = ?, public_post_url = ?, updated_at = ?
                    WHERE dedupe_key = ?
                    """,
                    payload + (record.opportunity.dedupe_key,),
                )
                record.id = int(existing["id"])
                return record.id

            cursor = connection.execute(
                """
                INSERT INTO lead_tracker (
                    source, source_item_id, source_url, dedupe_key, community_name,
                    author_name, title, body, keyword_hits_json, thread_metadata_json,
                    discovered_at, created_at, compliance_status, compliance_summary,
                    compliance_reason_codes_json, compliance_evidence_json,
                    compliance_allow_matches_json, compliance_deny_matches_json, score,
                    gemini_eligible, gemini_reason_codes_json, chosen_persona,
                    disclosure_required, reply_text, decision_confidence,
                    decision_rationale, status, operator_notes, public_post_url,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                payload,
            )
            record.id = int(cursor.lastrowid)
            return record.id

    def list_draft_records(
        self, statuses: list[DraftStatus] | None = None, limit: int = 100
    ) -> list[DraftRecord]:
        query = "SELECT * FROM lead_tracker"
        params: list[Any] = []
        if statuses:
            placeholders = ",".join("?" for _ in statuses)
            query += f" WHERE status IN ({placeholders})"
            params.extend(status.value for status in statuses)
        query += " ORDER BY score DESC, updated_at DESC LIMIT ?"
        params.append(limit)
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._row_to_draft_record(row) for row in rows]

    def get_draft_record(self, lead_id: int) -> DraftRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM lead_tracker WHERE id = ?",
                (lead_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_draft_record(row)

    def mark_manual_posted(
        self, lead_id: int, public_post_url: str, operator_notes: str = ""
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE lead_tracker
                SET status = ?, public_post_url = ?, operator_notes = ?,
                    manual_published_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (DraftStatus.MANUALLY_POSTED.value, public_post_url, operator_notes, lead_id),
            )

    def dismiss_record(self, lead_id: int, operator_notes: str = "") -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE lead_tracker
                SET status = ?, operator_notes = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (DraftStatus.DISMISSED.value, operator_notes, lead_id),
            )

    def update_visibility_status(self, result: VisibilityCheckResult) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO visibility_checks (
                    lead_id, status, checked_url, expected_snippet, details, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    result.lead_id,
                    result.status.value,
                    result.checked_url,
                    result.expected_snippet,
                    result.details,
                    result.created_at.isoformat(),
                ),
            )
            connection.execute(
                """
                UPDATE lead_tracker
                SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (DraftStatus.VISIBILITY_VERIFIED.value, result.lead_id),
            )

    def log_event(self, event: AlertEvent) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO events (event_type, level, message, metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    event.event_type,
                    event.level.value,
                    event.message,
                    _json_dumps(event.metadata),
                    event.created_at.isoformat(),
                ),
            )

    def log_error(
        self,
        error_type: str,
        message: str,
        context: dict[str, Any] | None = None,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO errors (error_type, message, context_json, created_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (error_type, message, _json_dumps(context or {})),
            )

    def list_recent_events(self, limit: int = 100) -> list[sqlite3.Row]:
        with self._connect() as connection:
            return connection.execute(
                "SELECT * FROM events ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()

    def list_recent_errors(self, limit: int = 100) -> list[sqlite3.Row]:
        with self._connect() as connection:
            return connection.execute(
                "SELECT * FROM errors ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()

    def get_kill_switch_state(self) -> KillSwitchState:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT value_text, updated_at, updated_by FROM system_state WHERE key = 'kill_switch'"
            ).fetchone()
        enabled = str(row["value_text"]).lower() == "true"
        return KillSwitchState(
            enabled=enabled,
            changed_at=_parse_datetime(row["updated_at"]),
            changed_by=row["updated_by"],
        )

    def set_kill_switch(self, enabled: bool, changed_by: str = "dashboard") -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO system_state (key, value_text, updated_at, updated_by)
                VALUES ('kill_switch', ?, CURRENT_TIMESTAMP, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value_text = excluded.value_text,
                    updated_at = excluded.updated_at,
                    updated_by = excluded.updated_by
                """,
                (str(enabled).lower(), changed_by),
            )

    def get_counter(self, counter_name: str, counter_date: date | None = None) -> int:
        target_date = (counter_date or date.today()).isoformat()
        key = f"counter:{counter_name}:{target_date}"
        with self._connect() as connection:
            row = connection.execute(
                "SELECT value_text FROM system_state WHERE key = ?",
                (key,),
            ).fetchone()
        if row is None:
            return 0
        return int(row["value_text"])

    def increment_counter(
        self, counter_name: str, amount: int = 1, counter_date: date | None = None
    ) -> int:
        target_date = (counter_date or date.today()).isoformat()
        key = f"counter:{counter_name}:{target_date}"
        next_value = self.get_counter(counter_name, counter_date) + amount
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO system_state (key, value_text, updated_at, updated_by)
                VALUES (?, ?, CURRENT_TIMESTAMP, 'system')
                ON CONFLICT(key) DO UPDATE SET
                    value_text = excluded.value_text,
                    updated_at = excluded.updated_at
                """,
                (key, str(next_value)),
            )
        return next_value

    def get_overview_metrics(self) -> dict[str, Any]:
        today = date.today().isoformat()
        with self._connect() as connection:
            queued_today = connection.execute(
                """
                SELECT COUNT(*) AS count FROM lead_tracker
                WHERE status = ? AND substr(updated_at, 1, 10) = ?
                """,
                (DraftStatus.QUEUED_FOR_MANUAL_REVIEW.value, today),
            ).fetchone()["count"]
            posted_today = connection.execute(
                """
                SELECT COUNT(*) AS count FROM lead_tracker
                WHERE status IN (?, ?) AND substr(updated_at, 1, 10) = ?
                """,
                (
                    DraftStatus.MANUALLY_POSTED.value,
                    DraftStatus.VISIBILITY_VERIFIED.value,
                    today,
                ),
            ).fetchone()["count"]
            errors_today = connection.execute(
                "SELECT COUNT(*) AS count FROM errors WHERE substr(created_at, 1, 10) = ?",
                (today,),
            ).fetchone()["count"]
            total_leads = connection.execute(
                "SELECT COUNT(*) AS count FROM lead_tracker"
            ).fetchone()["count"]
        return {
            "queued_today": queued_today,
            "posted_today": posted_today,
            "errors_today": errors_today,
            "total_leads": total_leads,
            "kill_switch_enabled": self.get_kill_switch_state().enabled,
            "candidates_processed_today": self.get_counter("candidates"),
            "drafts_created_today": self.get_counter("drafts"),
        }

    def get_persona_distribution(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT chosen_persona, COUNT(*) AS count
                FROM lead_tracker
                WHERE chosen_persona != ?
                GROUP BY chosen_persona
                ORDER BY count DESC
                """,
                (Persona.NONE.value,),
            ).fetchall()
        return [{"persona": row["chosen_persona"], "count": row["count"]} for row in rows]

    def export_leads_to_csv(self, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM lead_tracker ORDER BY id ASC").fetchall()
        if not rows:
            destination.write_text("", encoding="utf-8")
            return destination
        with destination.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
            writer.writeheader()
            for row in rows:
                writer.writerow(dict(row))
        return destination

    def _row_to_draft_record(self, row: sqlite3.Row) -> DraftRecord:
        opportunity = Opportunity(
            source=row["source"],
            source_item_id=row["source_item_id"],
            source_url=row["source_url"],
            community_name=row["community_name"],
            author_name=row["author_name"],
            title=row["title"],
            body=row["body"],
            created_at=_parse_datetime(row["created_at"]),
            discovered_at=_parse_datetime(row["discovered_at"]),
            keyword_hits=_json_loads(row["keyword_hits_json"]) or [],
            thread_metadata=_json_loads(row["thread_metadata_json"]) or {},
        )
        compliance = ComplianceEvidence(
            status=ComplianceStatus(row["compliance_status"]),
            reason_codes=_json_loads(row["compliance_reason_codes_json"]) or [],
            summary=row["compliance_summary"],
            evidence_lines=_json_loads(row["compliance_evidence_json"]) or [],
            allow_matches=_json_loads(row["compliance_allow_matches_json"]) or [],
            deny_matches=_json_loads(row["compliance_deny_matches_json"]) or [],
        )
        decision = GeminiDecision(
            eligible=bool(row["gemini_eligible"]),
            reason_codes=_json_loads(row["gemini_reason_codes_json"]) or [],
            chosen_persona=Persona(row["chosen_persona"]),
            disclosure_required=bool(row["disclosure_required"]),
            reply_text=row["reply_text"],
            confidence=float(row["decision_confidence"]),
            rationale=row["decision_rationale"],
        )
        return DraftRecord(
            id=row["id"],
            opportunity=opportunity,
            compliance=compliance,
            decision=decision,
            status=DraftStatus(row["status"]),
            operator_notes=row["operator_notes"],
            public_post_url=row["public_post_url"],
            created_at=_parse_datetime(row["created_at"]),
            updated_at=_parse_datetime(row["updated_at"]),
        )
