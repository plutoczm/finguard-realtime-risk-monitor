from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from ai_service.privacy import redact_sensitive_fields


RecommendedAction = Literal[
    "manual_review",
    "step_up_auth",
    "block_recommended",
    "allow_with_monitoring",
]
ActionTaken = Literal[
    "manual_review",
    "step_up_auth",
    "blocked",
    "allowed",
    "escalated",
    "none",
]
Verdict = Literal["true_positive", "false_positive", "uncertain"]
CaseStatus = Literal["open", "investigating", "resolved"]
CasePriority = Literal["low", "medium", "high", "critical"]
DegradationReason = Literal[
    "missing_credentials",
    "provider_error",
    "circuit_open",
    "bulkhead_saturated",
]


class ExplainRequest(BaseModel):
    alert: dict[str, Any]
    transaction: dict[str, Any] | None = None
    recent_events: list[dict[str, Any]] = Field(default_factory=list, max_length=20)
    language: Literal["zh-CN", "en"] = "zh-CN"

    @field_validator("alert", "transaction", "recent_events", mode="before")
    @classmethod
    def redact_explicit_sensitive_fields(cls, value: Any) -> Any:
        return redact_sensitive_fields(value)


class RiskExplanation(BaseModel):
    summary: str
    recommended_action: RecommendedAction
    confidence: float = Field(ge=0.0, le=1.0)
    key_evidence: list[str] = Field(min_length=1, max_length=8)
    investigation_steps: list[str] = Field(min_length=1, max_length=8)
    limitations: list[str] = Field(default_factory=list, max_length=8)
    source: Literal["llm", "fallback"]
    degradation_reason: DegradationReason | None = None
    prompt_version: str
    model: str | None = None


class ExplainResponse(BaseModel):
    request_id: str
    latency_ms: float = Field(ge=0)
    input_fingerprint: str
    explanation: RiskExplanation


class FeedbackRequest(BaseModel):
    request_id: str = Field(min_length=8, max_length=64)
    verdict: Verdict
    accepted_recommendation: bool
    action_taken: ActionTaken = "none"
    analyst_ref: str | None = Field(default=None, max_length=64)


class FeedbackResponse(BaseModel):
    request_id: str
    status: Literal["recorded"] = "recorded"


class InvestigationRecord(BaseModel):
    request_id: str
    created_at: str
    alert_ref: str | None = None
    rule_id: str | None = None
    risk_level: str | None = None
    source: Literal["llm", "fallback"]
    model: str | None = None
    prompt_version: str
    recommended_action: str
    confidence: float
    latency_ms: float
    input_fingerprint: str
    feedback: FeedbackRequest | None = None


class QualitySummary(BaseModel):
    total_investigations: int
    llm_count: int
    fallback_count: int
    feedback_count: int
    accepted_recommendation_count: int
    recommendation_acceptance_rate: float
    false_positive_count: int
    false_positive_rate: float
    average_latency_ms: float


class CaseCreateRequest(BaseModel):
    request_id: str = Field(min_length=8, max_length=64)
    priority: CasePriority | None = None
    assignee_ref: str | None = Field(default=None, max_length=64)
    note: str | None = Field(default=None, max_length=1000)


class CaseUpdateRequest(BaseModel):
    expected_version: int = Field(ge=1)
    status: CaseStatus | None = None
    priority: CasePriority | None = None
    assignee_ref: str | None = Field(default=None, max_length=64)
    resolution_verdict: Verdict | None = None
    accepted_recommendation: bool | None = None
    action_taken: ActionTaken | None = None
    note: str | None = Field(default=None, max_length=1000)
    actor_ref: str | None = Field(default=None, max_length=64)


class CaseRecord(BaseModel):
    case_id: str
    request_id: str
    created_at: str
    updated_at: str
    due_at: str
    resolved_at: str | None = None
    status: CaseStatus
    priority: CasePriority
    assignee_ref: str | None = None
    resolution_verdict: Verdict | None = None
    action_taken: ActionTaken | None = None
    note: str | None = None
    version: int
    sla_breached: bool
    alert_ref: str | None = None
    rule_id: str | None = None
    risk_level: str | None = None
    recommended_action: str
    source: Literal["llm", "fallback"]


class CaseEvent(BaseModel):
    event_id: int
    case_id: str
    event_type: Literal["created", "updated", "resolved", "reopened"]
    actor_ref: str | None = None
    created_at: str
    from_status: CaseStatus | None = None
    to_status: CaseStatus
    version: int
    note: str | None = None


class CaseListResponse(BaseModel):
    items: list[CaseRecord]
    total: int
    limit: int
    offset: int


class CaseSummary(BaseModel):
    open_count: int
    investigating_count: int
    resolved_count: int
    sla_breached_count: int
    unassigned_count: int


class HealthResponse(BaseModel):
    status: Literal["ok"]
    llm_enabled: bool
    model: str
    prompt_version: str
    provider_circuit_open: bool
    provider_inflight: int = Field(ge=0)
    provider_max_concurrency: int = Field(ge=1)


class ReadyResponse(BaseModel):
    status: Literal["ready"]
    audit_store: Literal["ok"]
