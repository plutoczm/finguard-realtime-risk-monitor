from __future__ import annotations

import hashlib
import json
import os
import time
from threading import BoundedSemaphore, Lock
from typing import Any

from pydantic import ValidationError

from ai_service.models import DegradationReason, ExplainRequest, RiskExplanation

PROMPT_VERSION = "risk-investigator-v3"

SYSTEM_PROMPT = """You are FinGuard's risk-investigation copilot.
Your job is decision support for a human risk analyst, not autonomous payment authorization.
Use only the supplied alert/transaction context. Never invent evidence, identity attributes,
external facts, or causal claims. If evidence is insufficient, say so in limitations.
Prioritize concise, auditable reasoning and concrete investigation steps.
Return only data matching the required JSON schema."""

RULE_ACTIONS = {
    "R006": "block_recommended",
    "R003": "manual_review",
    "R004": "manual_review",
    "R002": "step_up_auth",
    "R008": "manual_review",
}

# These are outcome/supervision fields, not event-time investigation features. Keeping them
# out of model/audit context prevents target leakage and makes offline/live eval meaningful.
POST_EVENT_LABEL_FIELDS = frozenset(
    {
        "risk_label",
        "fraud_label",
        "chargeback_label",
        "analyst_verdict",
        "resolution_verdict",
        "ground_truth",
        "target_label",
    }
)

EXPLANATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "summary": {"type": "string"},
        "recommended_action": {
            "type": "string",
            "enum": [
                "manual_review",
                "step_up_auth",
                "block_recommended",
                "allow_with_monitoring",
            ],
        },
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "key_evidence": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 8},
        "investigation_steps": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
            "maxItems": 8,
        },
        "limitations": {"type": "array", "items": {"type": "string"}, "maxItems": 8},
    },
    "required": [
        "summary",
        "recommended_action",
        "confidence",
        "key_evidence",
        "investigation_steps",
        "limitations",
    ],
}


def _tokenize(value: Any, prefix: str) -> str | None:
    if value in (None, ""):
        return None
    digest = hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:10]
    return f"{prefix}_{digest}"


def _sanitize_evidence(value: Any, key: str = "") -> Any:
    normalized = key.lower()
    if normalized in POST_EVENT_LABEL_FIELDS:
        return None
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for nested_key, nested_value in value.items():
            cleaned = _sanitize_evidence(nested_value, str(nested_key))
            if cleaned is not None:
                sanitized[str(nested_key)] = cleaned
        return sanitized
    if isinstance(value, list):
        sanitized_items = [_sanitize_evidence(item, key) for item in value[:20]]
        return [item for item in sanitized_items if item is not None]
    if normalized in {"ip", "ip_address", "client_ip"}:
        return "[redacted]"
    if normalized.endswith("_id") or normalized in {
        "user",
        "device",
        "merchant",
        "card",
        "account",
        "transaction",
        "event",
    }:
        return _tokenize(value, "ref")
    return value


def sanitize_context(request: ExplainRequest) -> dict[str, Any]:
    """Build event-time, PII-minimized context for model calls and audit records.

    Post-event supervision fields such as risk/fraud/chargeback labels and analyst verdicts
    are intentionally excluded. They belong to offline evaluation/training feedback, not
    to the online investigation features available at decision time.
    """
    alert = request.alert
    tx = request.transaction or {}

    sanitized_alert = {
        "alert_ref": _tokenize(alert.get("alert_id"), "alt"),
        "rule_id": alert.get("rule_id"),
        "rule_name": alert.get("rule_name"),
        "risk_level": alert.get("risk_level"),
        "reason": alert.get("reason"),
        "amount": alert.get("amount"),
        "evidence": _sanitize_evidence(alert.get("evidence") or {}),
        "user_ref": _tokenize(alert.get("user_id"), "usr"),
        "device_ref": _tokenize(alert.get("device_id"), "dev"),
        "merchant_ref": _tokenize(alert.get("merchant_id"), "mch"),
    }
    sanitized_tx = {
        "amount": tx.get("amount"),
        "currency": tx.get("currency"),
        "channel": tx.get("channel"),
        "city": tx.get("city"),
        "transaction_status": tx.get("transaction_status"),
        "is_black_device": bool(tx.get("is_black_device")),
        "is_black_card": bool(tx.get("is_black_card")),
        "user_ref": _tokenize(tx.get("user_id"), "usr"),
        "device_ref": _tokenize(tx.get("device_id"), "dev"),
        "merchant_ref": _tokenize(tx.get("merchant_id"), "mch"),
    }

    recent = []
    for event in request.recent_events[:20]:
        recent.append(
            {
                "amount": event.get("amount"),
                "channel": event.get("channel"),
                "transaction_status": event.get("transaction_status"),
                "user_ref": _tokenize(event.get("user_id"), "usr"),
                "device_ref": _tokenize(event.get("device_id"), "dev"),
            }
        )

    return {
        "language": request.language,
        "alert": {k: v for k, v in sanitized_alert.items() if v is not None},
        "transaction": {k: v for k, v in sanitized_tx.items() if v is not None},
        "recent_events": recent,
    }


def fallback_explanation(
    request: ExplainRequest,
    limitation: str | None = None,
    degradation_reason: DegradationReason | None = None,
) -> RiskExplanation:
    alert = request.alert
    rule_id = str(alert.get("rule_id") or "UNKNOWN")
    level = str(alert.get("risk_level") or "UNKNOWN").upper()
    reason = str(alert.get("reason") or alert.get("rule_name") or "风控规则命中")
    evidence = _sanitize_evidence(alert.get("evidence") or {})

    evidence_items = [f"rule_id={rule_id}", f"risk_level={level}", reason]
    for key, value in list(evidence.items())[:4]:
        evidence_items.append(f"{key}={value}")

    action = RULE_ACTIONS.get(rule_id)
    if action is None:
        action = "manual_review" if level in {"HIGH", "CRITICAL"} else "allow_with_monitoring"

    zh = request.language == "zh-CN"
    steps = (
        [
            "核对该规则命中的原始事件与窗口统计，确认不是重复或迟到数据造成的误报。",
            "检查同一用户、设备、银行卡和商户的近期关联交易，寻找聚集或突变。",
            "结合账户历史与人工审核结果决定是否升级验证、拦截或放行。",
        ]
        if zh
        else [
            "Verify the triggering event and window aggregates to rule out duplicate or late-data artifacts.",
            "Inspect recent linked user, device, card, and merchant activity for clusters or abrupt changes.",
            "Use account history and analyst review to decide whether to step up, block, or allow.",
        ]
    )
    summary = (
        f"规则 {rule_id} 命中，风险等级 {level}。{reason}。该结论仅作为人工风控调查辅助。"
        if zh
        else f"Rule {rule_id} triggered at {level} risk. {reason}. This is analyst decision support only."
    )
    limitations = ["未调用大模型，当前为确定性降级解释。"] if zh else ["LLM not used; deterministic fallback explanation."]
    if limitation:
        limitations.append(limitation)

    return RiskExplanation(
        summary=summary,
        recommended_action=action,
        confidence=0.72 if level in {"HIGH", "CRITICAL"} else 0.62,
        key_evidence=evidence_items[:8],
        investigation_steps=steps,
        limitations=limitations,
        source="fallback",
        degradation_reason=degradation_reason,
        prompt_version=PROMPT_VERSION,
        model=None,
    )


def _http_status(exc: Exception) -> int | None:
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        return status
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    return status if isinstance(status, int) else None


def _classify_provider_error(exc: Exception) -> DegradationReason:
    name = exc.__class__.__name__.casefold()
    status = _http_status(exc)
    if status == 429 or "ratelimit" in name or "rate_limit" in name:
        return "provider_rate_limited"
    if status in {408, 504} or "timeout" in name or "timedout" in name:
        return "provider_timeout"
    return "provider_error"


class RiskExplainer:
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout_seconds: float = 8.0,
        failure_threshold: int | None = None,
        cooldown_seconds: float | None = None,
        max_concurrency: int | None = None,
        bulkhead_wait_ms: float | None = None,
        client: Any | None = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else os.getenv("OPENAI_API_KEY")
        self.model = model or os.getenv("FINGUARD_AI_MODEL", "gpt-5-mini")
        self.timeout_seconds = timeout_seconds
        self.failure_threshold = max(1, failure_threshold or int(os.getenv("FINGUARD_AI_FAILURE_THRESHOLD", "3")))
        self.cooldown_seconds = max(1.0, cooldown_seconds or float(os.getenv("FINGUARD_AI_COOLDOWN_SECONDS", "30")))
        configured_concurrency = max_concurrency if max_concurrency is not None else int(os.getenv("FINGUARD_AI_MAX_CONCURRENCY", "4"))
        configured_wait_ms = bulkhead_wait_ms if bulkhead_wait_ms is not None else float(os.getenv("FINGUARD_AI_BULKHEAD_WAIT_MS", "25"))
        self.max_concurrency = max(1, configured_concurrency)
        self.bulkhead_wait_seconds = max(0.0, configured_wait_ms) / 1000.0
        self._lock = Lock()
        self._inflight_lock = Lock()
        self._provider_slots = BoundedSemaphore(self.max_concurrency)
        self._provider_inflight = 0
        self._consecutive_failures = 0
        self._circuit_open_until = 0.0
        self._client = client
        if self.api_key and self._client is None:
            from openai import OpenAI

            self._client = OpenAI(
                api_key=self.api_key,
                timeout=self.timeout_seconds,
                max_retries=1,
            )

    @property
    def llm_enabled(self) -> bool:
        return bool(self.api_key)

    @property
    def circuit_open(self) -> bool:
        with self._lock:
            return time.monotonic() < self._circuit_open_until

    @property
    def provider_inflight(self) -> int:
        with self._inflight_lock:
            return self._provider_inflight

    def _record_success(self) -> None:
        with self._lock:
            self._consecutive_failures = 0
            self._circuit_open_until = 0.0

    def _record_failure(self) -> None:
        with self._lock:
            self._consecutive_failures += 1
            if self._consecutive_failures >= self.failure_threshold:
                self._circuit_open_until = time.monotonic() + self.cooldown_seconds

    def _enter_provider(self) -> bool:
        acquired = self._provider_slots.acquire(timeout=self.bulkhead_wait_seconds)
        if not acquired:
            return False
        with self._inflight_lock:
            self._provider_inflight += 1
        return True

    def _leave_provider(self) -> None:
        with self._inflight_lock:
            self._provider_inflight -= 1
        self._provider_slots.release()

    def explain(self, request: ExplainRequest) -> RiskExplanation:
        if not self.llm_enabled:
            return fallback_explanation(
                request,
                degradation_reason="missing_credentials",
            )
        if self.circuit_open:
            return fallback_explanation(
                request,
                limitation="LLM circuit breaker open; provider calls temporarily paused.",
                degradation_reason="circuit_open",
            )
        if not self._enter_provider():
            return fallback_explanation(
                request,
                limitation="LLM bulkhead saturated; request served by deterministic fallback.",
                degradation_reason="bulkhead_saturated",
            )

        try:
            payload = sanitize_context(request)
            try:
                response = self._client.responses.create(
                    model=self.model,
                    instructions=SYSTEM_PROMPT,
                    input=json.dumps(payload, ensure_ascii=False),
                    text={
                        "format": {
                            "type": "json_schema",
                            "name": "finguard_risk_explanation",
                            "strict": True,
                            "schema": EXPLANATION_SCHEMA,
                        }
                    },
                )
            except Exception as exc:
                self._record_failure()
                reason = _classify_provider_error(exc)
                return fallback_explanation(
                    request,
                    limitation=(
                        "LLM provider unavailable; fallback activated "
                        f"({exc.__class__.__name__})."
                    ),
                    degradation_reason=reason,
                )

            try:
                parsed = json.loads(response.output_text)
                result = RiskExplanation(
                    **parsed,
                    source="llm",
                    degradation_reason=None,
                    prompt_version=PROMPT_VERSION,
                    model=self.model,
                )
            except (json.JSONDecodeError, ValidationError, TypeError, ValueError, AttributeError) as exc:
                self._record_failure()
                return fallback_explanation(
                    request,
                    limitation=(
                        "LLM returned invalid structured output; fallback activated "
                        f"({exc.__class__.__name__})."
                    ),
                    degradation_reason="invalid_model_output",
                )

            self._record_success()
            return result
        finally:
            self._leave_provider()
