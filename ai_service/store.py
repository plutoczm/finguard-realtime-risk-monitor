from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

from ai_service.models import FeedbackRequest, InvestigationRecord, QualitySummary, RiskExplanation

SCHEMA_VERSION = 1


def context_fingerprint(context: dict[str, Any]) -> str:
    canonical = json.dumps(context, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]


class InvestigationStore:
    """Small audit store for local/portfolio deployments.

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
            if current_version not in {0, SCHEMA_VERSION}:
                raise RuntimeError(
                    f"unsupported audit schema version {current_version}; expected {SCHEMA_VERSION}"
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

                CREATE INDEX IF NOT EXISTS idx_investigations_created_at
                    ON investigations(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_investigations_prompt_source
                    ON investigations(prompt_version, source);
                CREATE INDEX IF NOT EXISTS idx_investigations_rule
                    ON investigations(rule_id, risk_level);
                """
            )
            if current_version == 0:
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
        created_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
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
                    feedback.request_id,
                    feedback.verdict,
                    int(feedback.accepted_recommendation),
                    feedback.action_taken,
                    feedback.analyst_ref,
                    datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                ),
            )
        return True

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
