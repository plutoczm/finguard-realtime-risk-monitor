from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from typing import Any

from ai_service.models import (
    CaseCreateRequest,
    CaseEvent,
    CaseListResponse,
    CaseRecord,
    CaseSummary,
    CaseUpdateRequest,
    FeedbackRequest,
    InvestigationRecord,
    QualitySummary,
    RiskExplanation,
)

SCHEMA_VERSION = 2
CASE_SLA_MINUTES = {
    "critical": 15,
    "high": 60,
    "medium": 240,
    "low": 1440,
}
ALLOWED_CASE_TRANSITIONS = {
    "open": {"open", "investigating", "resolved"},
    "investigating": {"open", "investigating", "resolved"},
    "resolved": {"resolved", "investigating"},
}


def context_fingerprint(context: dict[str, Any]) -> str:
    canonical = json.dumps(context, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _default_priority(risk_level: str | None) -> str:
    normalized = str(risk_level or "").upper()
    if normalized == "CRITICAL":
        return "critical"
    if normalized == "HIGH":
        return "high"
    if normalized == "LOW":
        return "low"
    return "medium"


def _due_at(created_at: str, priority: str) -> str:
    return _iso(_parse_iso(created_at) + timedelta(minutes=CASE_SLA_MINUTES[priority]))


class InvestigationStore:
    """Audit and case-management store for local/portfolio deployments.

    Only sanitized model context and structured explanations are persisted. Raw transaction
    payloads are intentionally never written by this component.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        configured = path or os.getenv("FINGUARD_AI_DB_PATH", "data/ai_copilot/finguard_ai.sqlite3")
        self.path = str(configured)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._connection = sqlite3.connect(self.path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        if self.path != ":memory:":
            self._connection.execute("PRAGMA journal_mode = WAL")
        self._initialize()

    def _initialize(self) -> None:
        with self._lock, self._connection:
            current_version = int(self._connection.execute("PRAGMA user_version").fetchone()[0])
            if current_version not in {0, 1, SCHEMA_VERSION}:
                raise RuntimeError(
                    f"unsupported audit schema version {current_version}; expected <= {SCHEMA_VERSION}"
                )
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS investigations (
                    request_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    alert_ref TEXT,
                    rule_id TEXT,
                    risk_level TEXT,
                    source TEXT NOT NULL,
                    model TEXT,
                    prompt_version TEXT NOT NULL,
                    recommended_action TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    latency_ms REAL NOT NULL,
                    input_fingerprint TEXT NOT NULL,
                    context_json TEXT NOT NULL,
                    explanation_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS analyst_feedback (
                    request_id TEXT PRIMARY KEY,
                    verdict TEXT NOT NULL,
                    accepted_recommendation INTEGER NOT NULL,
                    action_taken TEXT NOT NULL,
                    analyst_ref TEXT,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(request_id) REFERENCES investigations(request_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS cases (
                    case_id TEXT PRIMARY KEY,
                    request_id TEXT UNIQUE NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    due_at TEXT NOT NULL,
                    resolved_at TEXT,
                    status TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    assignee_ref TEXT,
                    resolution_verdict TEXT,
                    action_taken TEXT,
                    note TEXT,
                    version INTEGER NOT NULL,
                    FOREIGN KEY(request_id) REFERENCES investigations(request_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS case_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    actor_ref TEXT,
                    created_at TEXT NOT NULL,
                    from_status TEXT,
                    to_status TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    note TEXT,
                    FOREIGN KEY(case_id) REFERENCES cases(case_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_investigations_created_at
                    ON investigations(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_investigations_prompt_source
                    ON investigations(prompt_version, source);
                CREATE INDEX IF NOT EXISTS idx_investigations_rule
                    ON investigations(rule_id, risk_level);
                CREATE INDEX IF NOT EXISTS idx_cases_status_priority
                    ON cases(status, priority, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_cases_assignee
                    ON cases(assignee_ref, status);
                CREATE INDEX IF NOT EXISTS idx_case_events_case
                    ON case_events(case_id, event_id DESC);
                """
            )
            if current_version < SCHEMA_VERSION:
                self._connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def ping(self) -> bool:
        with self._lock:
            row = self._connection.execute("SELECT 1 AS ok").fetchone()
        return bool(row and row["ok"] == 1)

    def record_investigation(
        self,
        *,
        request_id: str,
        sanitized_context: dict[str, Any],
        explanation: RiskExplanation,
        latency_ms: float,
    ) -> str:
        fingerprint = context_fingerprint(sanitized_context)
        alert = sanitized_context.get("alert") or {}
        created_at = _iso(_now())
        context_json = json.dumps(sanitized_context, ensure_ascii=False, sort_keys=True)
        explanation_json = explanation.model_dump_json()
        values = (
            request_id,
            created_at,
            alert.get("alert_ref"),
            alert.get("rule_id"),
            alert.get("risk_level"),
            explanation.source,
            explanation.model,
            explanation.prompt_version,
            explanation.recommended_action,
            explanation.confidence,
            latency_ms,
            fingerprint,
            context_json,
            explanation_json,
        )
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO investigations (
                    request_id, created_at, alert_ref, rule_id, risk_level, source, model,
                    prompt_version, recommended_action, confidence, latency_ms,
                    input_fingerprint, context_json, explanation_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                values,
            )
        return fingerprint

    def record_feedback(self, feedback: FeedbackRequest) -> bool:
        with self._lock, self._connection:
            exists = self._connection.execute(
                "SELECT 1 FROM investigations WHERE request_id = ?",
                (feedback.request_id,),
            ).fetchone()
            if not exists:
                return False
            self._upsert_feedback(
                request_id=feedback.request_id,
                verdict=feedback.verdict,
                accepted_recommendation=feedback.accepted_recommendation,
                action_taken=feedback.action_taken,
                analyst_ref=feedback.analyst_ref,
            )
        return True

    def _upsert_feedback(
        self,
        *,
        request_id: str,
        verdict: str,
        accepted_recommendation: bool,
        action_taken: str,
        analyst_ref: str | None,
    ) -> None:
        self._connection.execute(
            """
            INSERT INTO analyst_feedback (
                request_id, verdict, accepted_recommendation, action_taken,
                analyst_ref, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(request_id) DO UPDATE SET
                verdict = excluded.verdict,
                accepted_recommendation = excluded.accepted_recommendation,
                action_taken = excluded.action_taken,
                analyst_ref = excluded.analyst_ref,
                updated_at = excluded.updated_at
            """,
            (
                request_id,
                verdict,
                int(accepted_recommendation),
                action_taken,
                analyst_ref,
                _iso(_now()),
            ),
        )

    def get_investigation(self, request_id: str) -> InvestigationRecord | None:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT i.*, f.verdict, f.accepted_recommendation, f.action_taken, f.analyst_ref
                FROM investigations i
                LEFT JOIN analyst_feedback f ON f.request_id = i.request_id
                WHERE i.request_id = ?
                """,
                (request_id,),
            ).fetchone()
        if row is None:
            return None
        feedback = None
        if row["verdict"] is not None:
            feedback = FeedbackRequest(
                request_id=row["request_id"],
                verdict=row["verdict"],
                accepted_recommendation=bool(row["accepted_recommendation"]),
                action_taken=row["action_taken"],
                analyst_ref=row["analyst_ref"],
            )
        return InvestigationRecord(
            request_id=row["request_id"],
            created_at=row["created_at"],
            alert_ref=row["alert_ref"],
            rule_id=row["rule_id"],
            risk_level=row["risk_level"],
            source=row["source"],
            model=row["model"],
            prompt_version=row["prompt_version"],
            recommended_action=row["recommended_action"],
            confidence=row["confidence"],
            latency_ms=row["latency_ms"],
            input_fingerprint=row["input_fingerprint"],
            feedback=feedback,
        )

    def create_case(self, request: CaseCreateRequest) -> CaseRecord | None:
        with self._lock, self._connection:
            existing = self._connection.execute(
                "SELECT case_id FROM cases WHERE request_id = ?",
                (request.request_id,),
            ).fetchone()
            if existing:
                return self._get_case_locked(existing["case_id"])

            investigation = self._connection.execute(
                """
                SELECT request_id, alert_ref, rule_id, risk_level, recommended_action, source
                FROM investigations WHERE request_id = ?
                """,
                (request.request_id,),
            ).fetchone()
            if investigation is None:
                return None

            created_at = _iso(_now())
            priority = request.priority or _default_priority(investigation["risk_level"])
            case_id = f"case_{uuid.uuid4().hex[:16]}"
            self._connection.execute(
                """
                INSERT INTO cases (
                    case_id, request_id, created_at, updated_at, due_at, resolved_at,
                    status, priority, assignee_ref, resolution_verdict, action_taken, note, version
                ) VALUES (?, ?, ?, ?, ?, NULL, 'open', ?, ?, NULL, NULL, ?, 1)
                """,
                (
                    case_id,
                    request.request_id,
                    created_at,
                    created_at,
                    _due_at(created_at, priority),
                    priority,
                    request.assignee_ref,
                    request.note,
                ),
            )
            self._insert_case_event(
                case_id=case_id,
                event_type="created",
                actor_ref=request.assignee_ref,
                from_status=None,
                to_status="open",
                version=1,
                note=request.note,
            )
            return self._get_case_locked(case_id)

    def get_case(self, case_id: str) -> CaseRecord | None:
        with self._lock:
            return self._get_case_locked(case_id)

    def _get_case_locked(self, case_id: str) -> CaseRecord | None:
        row = self._connection.execute(
            """
            SELECT c.*, i.alert_ref, i.rule_id, i.risk_level, i.recommended_action, i.source
            FROM cases c
            JOIN investigations i ON i.request_id = c.request_id
            WHERE c.case_id = ?
            """,
            (case_id,),
        ).fetchone()
        return self._case_from_row(row) if row else None

    def list_cases(
        self,
        *,
        status: str | None = None,
        priority: str | None = None,
        assignee_ref: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> CaseListResponse:
        where = []
        params: list[Any] = []
        if status:
            where.append("c.status = ?")
            params.append(status)
        if priority:
            where.append("c.priority = ?")
            params.append(priority)
        if assignee_ref:
            where.append("c.assignee_ref = ?")
            params.append(assignee_ref)
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        with self._lock:
            total = int(
                self._connection.execute(
                    f"SELECT COUNT(*) FROM cases c {clause}",
                    params,
                ).fetchone()[0]
            )
            rows = self._connection.execute(
                f"""
                SELECT c.*, i.alert_ref, i.rule_id, i.risk_level, i.recommended_action, i.source
                FROM cases c
                JOIN investigations i ON i.request_id = c.request_id
                {clause}
                ORDER BY
                    CASE c.priority
                        WHEN 'critical' THEN 0
                        WHEN 'high' THEN 1
                        WHEN 'medium' THEN 2
                        ELSE 3
                    END,
                    c.due_at ASC,
                    c.updated_at DESC
                LIMIT ? OFFSET ?
                """,
                [*params, limit, offset],
            ).fetchall()
        return CaseListResponse(
            items=[self._case_from_row(row) for row in rows],
            total=total,
            limit=limit,
            offset=offset,
        )

    def update_case(self, case_id: str, request: CaseUpdateRequest) -> tuple[str, CaseRecord | None]:
        with self._lock, self._connection:
            row = self._connection.execute(
                "SELECT * FROM cases WHERE case_id = ?",
                (case_id,),
            ).fetchone()
            if row is None:
                return "not_found", None
            if int(row["version"]) != request.expected_version:
                return "version_conflict", self._get_case_locked(case_id)

            current_status = row["status"]
            target_status = request.status or current_status
            if target_status not in ALLOWED_CASE_TRANSITIONS[current_status]:
                return "invalid_transition", self._get_case_locked(case_id)

            priority = request.priority or row["priority"]
            assignee_ref = request.assignee_ref if request.assignee_ref is not None else row["assignee_ref"]
            resolution_verdict = (
                request.resolution_verdict
                if request.resolution_verdict is not None
                else row["resolution_verdict"]
            )
            action_taken = request.action_taken if request.action_taken is not None else row["action_taken"]
            note = request.note if request.note is not None else row["note"]
            resolved_at = row["resolved_at"]

            if target_status == "resolved":
                if resolution_verdict is None or action_taken is None:
                    return "resolution_required", self._get_case_locked(case_id)
                resolved_at = resolved_at or _iso(_now())
            elif current_status == "resolved" and target_status == "investigating":
                resolution_verdict = None
                action_taken = None
                resolved_at = None

            if request.accepted_recommendation is not None:
                if resolution_verdict is None or action_taken is None:
                    return "feedback_requires_resolution", self._get_case_locked(case_id)

            updated_at = _iso(_now())
            next_version = int(row["version"]) + 1
            due_at = _due_at(row["created_at"], priority)
            cursor = self._connection.execute(
                """
                UPDATE cases SET
                    updated_at = ?,
                    due_at = ?, 
                    resolved_at = ?,
                    status = ?,
                    priority = ?,
                    assignee_ref = ?,
                    resolution_verdict = ?, 
                    action_taken = ?, 
                    note = ?,
                    version = ?
                WHERE case_id = ? AND version = ?
                """,
                (
                    updated_at,
                    due_at,
                    resolved_at,
                    target_status,
                    priority,
                    assignee_ref,
                    resolution_verdict,
                    action_taken,
                    note,
                    next_version,
                    case_id,
                    request.expected_version,
                ),
            )
            if cursor.rowcount != 1:
                return "version_conflict", self._get_case_locked(case_id)

            if current_status == "resolved" and target_status == "investigating":
                self._connection.execute(
                    "DELETE FROM analyst_feedback WHERE request_id = ?",
                    (row["request_id"],),
                )

            if request.accepted_recommendation is not None:
                self._upsert_feedback(
                    request_id=row["request_id"],
                    verdict=resolution_verdict,
                    accepted_recommendation=request.accepted_recommendation,
                    action_taken=action_taken,
                    analyst_ref=request.actor_ref or assignee_ref,
                )

            if current_status == "resolved" and target_status == "investigating":
                event_type = "reopened"
            elif target_status == "resolved" and current_status != "resolved":
                event_type = "resolved"
            else:
                event_type = "updated"
            self._insert_case_event(
                case_id=case_id,
                event_type=event_type,
                actor_ref=request.actor_ref or assignee_ref,
                from_status=current_status,
                to_status=target_status,
                version=next_version,
                note=request.note,
            )
            return "updated", self._get_case_locked(case_id)

    def _insert_case_event(
        self,
        *,
        case_id: str,
        event_type: str,
        actor_ref: str | None,
        from_status: str | None,
        to_status: str,
        version: int,
        note: str | None,
    ) -> None:
        self._connection.execute(
            """
            INSERT INTO case_events (
                case_id, event_type, actor_ref, created_at, from_status, to_status, version, note
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                case_id,
                event_type,
                actor_ref,
                _iso(_now()),
                from_status,
                to_status,
                version,
                note,
            ),
        )

    def list_case_events(self, case_id: str) -> list[CaseEvent] | None:
        with self._lock:
            exists = self._connection.execute(
                "SELECT 1 FROM cases WHERE case_id = ?",
                (case_id,),
            ).fetchone()
            if not exists:
                return None
            rows = self._connection.execute(
                """
                SELECT event_id, case_id, event_type, actor_ref, created_at,
                       from_status, to_status, version, note
                FROM case_events
                WHERE case_id = ?
                ORDER BY event_id ASC
                """,
                (case_id,),
            ).fetchall()
        return [CaseEvent(**dict(row)) for row in rows]

    def case_summary(self) -> CaseSummary:
        now = _iso(_now())
        with self._lock:
            row = self._connection.execute(
                """
                SELECT
                    SUM(CASE WHEN status = 'open' THEN 1 ELSE 0 END) AS open_count,
                    SUM(CASE WHEN status = 'investigating' THEN 1 ELSE 0 END) AS investigating_count,
                    SUM(CASE WHEN status = 'resolved' THEN 1 ELSE 0 END) AS resolved_count,
                    SUM(CASE WHEN status != 'resolved' AND due_at < ? THEN 1 ELSE 0 END) AS sla_breached_count,
                    SUM(CASE WHEN status != 'resolved' AND assignee_ref IS NULL THEN 1 ELSE 0 END) AS unassigned_count
                FROM cases
                """,
                (now,),
            ).fetchone()
        return CaseSummary(
            open_count=int(row["open_count"] or 0),
            investigating_count=int(row["investigating_count"] or 0),
            resolved_count=int(row["resolved_count"] or 0),
            sla_breached_count=int(row["sla_breached_count"] or 0),
            unassigned_count=int(row["unassigned_count"] or 0),
        )

    def _case_from_row(self, row: sqlite3.Row) -> CaseRecord:
        return CaseRecord(
            case_id=row["case_id"],
            request_id=row["request_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            due_at=row["due_at"],
            resolved_at=row["resolved_at"],
            status=row["status"],
            priority=row["priority"],
            assignee_ref=row["assignee_ref"],
            resolution_verdict=row["resolution_verdict"],
            action_taken=row["action_taken"],
            note=row["note"],
            version=int(row["version"]),
            sla_breached=row["status"] != "resolved" and _parse_iso(row["due_at"]) < _now(),
            alert_ref=row["alert_ref"],
            rule_id=row["rule_id"],
            risk_level=row["risk_level"],
            recommended_action=row["recommended_action"],
            source=row["source"],
        )

    def quality_summary(self) -> QualitySummary:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN source = 'llm' THEN 1 ELSE 0 END) AS llm_count,
                    SUM(CASE WHEN source = 'fallback' THEN 1 ELSE 0 END) AS fallback_count,
                    AVG(latency_ms) AS avg_latency
                FROM investigations
                """
            ).fetchone()
            feedback = self._connection.execute(
                """
                SELECT
                    COUNT(*) AS feedback_count,
                    SUM(CASE WHEN accepted_recommendation = 1 THEN 1 ELSE 0 END) AS accepted_count,
                    SUM(CASE WHEN verdict = 'false_positive' THEN 1 ELSE 0 END) AS false_positive_count
                FROM analyst_feedback
                """
            ).fetchone()
        total_feedback = int(feedback["feedback_count"] or 0)
        accepted = int(feedback["accepted_count"] or 0)
        false_positives = int(feedback["false_positive_count"] or 0)
        return QualitySummary(
            total_investigations=int(row["total"] or 0),
            llm_count=int(row["llm_count"] or 0),
            fallback_count=int(row["fallback_count"] or 0),
            feedback_count=total_feedback,
            accepted_recommendation_count=accepted,
            recommendation_acceptance_rate=round(accepted / total_feedback, 4) if total_feedback else 0.0,
            false_positive_count=false_positives,
            false_positive_rate=round(false_positives / total_feedback, 4) if total_feedback else 0.0,
            average_latency_ms=round(float(row["avg_latency"] or 0.0), 3),
        )

    def close(self) -> None:
        with self._lock:
            self._connection.close()
