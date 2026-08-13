from ai_service.models import ExplainRequest
from ai_service.service import RiskExplainer, fallback_explanation, sanitize_context


def test_sanitize_context_removes_raw_identifiers_and_ip():
    request = ExplainRequest(
        alert={
            "rule_id": "R006",
            "risk_level": "HIGH",
            "user_id": "user-secret",
            "device_id": "device-secret",
        },
        transaction={
            "user_id": "user-secret",
            "device_id": "device-secret",
            "merchant_id": "merchant-secret",
            "ip": "10.1.2.3",
            "amount": 99.0,
        },
    )
    payload = str(sanitize_context(request))
    assert "user-secret" not in payload
    assert "device-secret" not in payload
    assert "merchant-secret" not in payload
    assert "10.1.2.3" not in payload
    assert "usr_" in payload
    assert "dev_" in payload


def test_fallback_is_deterministic_and_actionable():
    request = ExplainRequest(
        alert={
            "rule_id": "R006",
            "risk_level": "HIGH",
            "reason": "黑名单设备命中",
            "evidence": {"is_black_device": True},
        }
    )
    result = fallback_explanation(request)
    assert result.source == "fallback"
    assert result.recommended_action == "block_recommended"
    assert result.confidence >= 0.7
    assert result.investigation_steps


def test_missing_api_key_never_attempts_llm():
    explainer = RiskExplainer(api_key="")
    request = ExplainRequest(
        alert={
            "rule_id": "R001",
            "risk_level": "MEDIUM",
            "reason": "高频交易",
            "evidence": {"count": 13},
        }
    )
    result = explainer.explain(request)
    assert result.source == "fallback"
    assert result.model is None
