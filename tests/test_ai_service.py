from ai_service.models import ExplainRequest
from ai_service.service import RiskExplainer, fallback_explanation, sanitize_context


def test_sanitize_context_removes_raw_identifiers_and_ip():
    request = ExplainRequest(
        alert={
            "alert_id": "alert-secret",
            "rule_id": "R006",
            "risk_level": "HIGH",
            "user_id": "user-secret",
            "device_id": "device-secret",
            "evidence": {
                "card_id": "card-secret",
                "nested": {"ip": "192.168.1.9", "account_id": "acct-secret"},
            },
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
    for secret in [
        "alert-secret",
        "user-secret",
        "device-secret",
        "merchant-secret",
        "10.1.2.3",
        "card-secret",
        "192.168.1.9",
        "acct-secret",
    ]:
        assert secret not in payload
    assert "[redacted]" in payload
    assert "alt_" in payload
    assert "usr_" in payload
    assert "dev_" in payload


def test_fallback_is_deterministic_actionable_and_pii_safe():
    request = ExplainRequest(
        alert={
            "rule_id": "R006",
            "risk_level": "HIGH",
            "reason": "黑名单设备命中",
            "evidence": {"is_black_device": True, "card_id": "card-secret"},
        }
    )
    result = fallback_explanation(request)
    assert result.source == "fallback"
    assert result.recommended_action == "block_recommended"
    assert result.confidence >= 0.7
    assert result.investigation_steps
    assert "card-secret" not in str(result.key_evidence)
    assert "ref_" in str(result.key_evidence)


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


class _FailingResponses:
    def __init__(self):
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        raise RuntimeError("provider unavailable")


class _FailingClient:
    def __init__(self):
        self.responses = _FailingResponses()


def test_provider_circuit_breaker_stops_repeated_failed_calls():
    client = _FailingClient()
    explainer = RiskExplainer(
        api_key="test-key",
        client=client,
        failure_threshold=2,
        cooldown_seconds=60,
    )
    request = ExplainRequest(alert={"rule_id": "R002", "risk_level": "HIGH", "reason": "大额交易"})

    first = explainer.explain(request)
    second = explainer.explain(request)
    third = explainer.explain(request)

    assert first.source == second.source == third.source == "fallback"
    assert client.responses.calls == 2
    assert explainer.circuit_open is True
    assert any("circuit breaker" in item for item in third.limitations)
