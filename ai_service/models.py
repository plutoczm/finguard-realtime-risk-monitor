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
    explanation: RiskExplanation


class HealthResponse(BaseModel):
    status: Literal["ok"]
    llm_enabled: bool
    model: str
    prompt_version: str
