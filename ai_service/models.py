from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ExplainRequest(BaseModel):
    alert: dict[str, Any]
    transaction: dict[str, Any] | None = None
    recent_events: list[dict[str, Any]] = Field(default_factory=list, max_length=20)
    language: Literal["zh-CN", "en"] = "zh-CN"


class RiskExplanation(BaseModel):
    summary: str
    recommended_action: Literal[
        "manual_review",
        "step_up_auth",
        "block_recommended",
        "allow_with_monitoring",
    ]
    confidence: float = Field(ge=0.0, le=1.0)
    key_evidence: list[str] = Field(min_length=1, max_length=8)
    investigation_steps: list[str] = Field(min_length=1, max_length=8)
    limitations: list[str] = Field(default_factory=list, max_length=8)
    source: Literal["llm", "fallback"]
    prompt_version: str
    model: str | None = None


class ExplainResponse(BaseModel):
    request_id: str
    latency_ms: float = Field(ge=0)
    input_fingerprint: str
    explanation: RiskExplanation


class FeedbackRequest(BaseModel):
    request_id: str = Field(min_length=8, max_length=64)
    verdict: Literal["true_positive", "false_positive", "uncertain"]
    accepted_recommendation: bool
    action_taken: Literal[
        "manual_review",
        "step_up_auth",
        "blocked",
        "allowed",
        "escalated",
        "none",
    ] = "none"
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


class HealthResponse(BaseModel):
    status: Literal["ok"]
    llm_enabled: bool
    model: str
    prompt_version: str
    provider_circuit_open: bool


class ReadyResponse(BaseModel):
    status: Literal["ready"]
    audit_store: Literal["ok"]
