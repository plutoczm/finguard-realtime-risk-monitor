from __future__ import annotations

import hashlib
import json
import os
from typing import Any

from ai_service.models import ExplainRequest, RiskExplanation

PROMPT_VERSION = "risk-investigator-v1"

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


def sanitize_context(request: ExplainRequest) -> dict[str, Any]:
    """Minimize PII before any model call while preserving investigation signals."""
    alert = request.alert
    tx = request.transaction or {}

    sanitized_alert = {
        "rule_id": alert.get("rule_id"),
        "rule_name": alert.get("rule_name"),
        "risk_level": alert.get("risk_level"),
        "reason": alert.get("reason"),
        "amount": alert.get("amount"),
        "evidence": alert.get("evidence") or {},
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
        "risk_label": tx.get("risk_label"),
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
                "risk_label": event.get("risk_label"),
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


def fallback_explanation(request: ExplainRequest, limitation: str | None = None) -> RiskExplanation:
    alert = request.alert
    rule_id = str(alert.get("rule_id") or "UNKNOWN")
    level = str(alert.get("risk_level") or "UNKNOWN").upper()
    reason = str(alert.get("reason") or alert.get("rule_name") or "风险规则命中")
    evidence = alert.get("evidence") or {}

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
        prompt_version=PROMPT_VERSION,
        model=None,
    )


class RiskExplainer:
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout_seconds: float = 8.0,
    ) -> None:
        self.api_key = api_key if api_key is not None else os.getenv("OPENAI_API_KEY")
        self.model = model or os.getenv("FINGUARD_AI_MODEL", "gpt-5-mini")
        self.timeout_seconds = timeout_seconds

    @property
    def llm_enabled(self) -> bool:
        return bool(self.api_key)

    def explain(self, request: ExplainRequest) -> RiskExplanation:
        if not self.llm_enabled:
            return fallback_explanation(request)

        try:
            from openai import OpenAI

            client = OpenAI(
                api_key=self.api_key,
                timeout=self.timeout_seconds,
                max_retries=1,
            )
            payload = sanitize_context(request)
            response = client.responses.create(
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
            parsed = json.loads(response.output_text)
            return RiskExplanation(
                **parsed,
                source="llm",
                prompt_version=PROMPT_VERSION,
                model=self.model,
            )
        except Exception as exc:
            return fallback_explanation(
                request,
                limitation=f"LLM unavailable; fallback activated ({exc.__class__.__name__}).",
            )
