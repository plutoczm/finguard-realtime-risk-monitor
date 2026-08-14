import json

from ai_service.models import ExplainRequest
from ai_service.service import RiskExplainer, fallback_explanation, sanitize_context


def _request() -> ExplainRequest:
    return ExplainRequest(
        alert={
            "rule_id": "R002",
            "risk_level": "HIGH",
            "reason": "window amount exceeded",
            "evidence": {
                "window_amount": 25000,
                "risk_label": "fraud-outcome",
                "nested": {"ground_truth": "confirmed-fraud"},
            },
        },
        transaction={
            "amount": 8000,
            "risk_label": "transaction-fraud-label",
            "fraud_label": "fraud-positive",
        },
        recent_events=[
            {
                "amount": 5000,
                "risk_label": "recent-fraud-label",
                "chargeback_label": "future-chargeback",
            }
        ],
    )


def test_post_event_supervision_labels_never_enter_online_context():
    rendered = json.dumps(sanitize_context(_request()), ensure_ascii=False, sort_keys=True)
    for forbidden in [
        "risk_label",
        "fraud_label",
        "chargeback_label",
        "ground_truth",
        "fraud-outcome",
        "confirmed-fraud",
        "transaction-fraud-label",
        "fraud-positive",
        "recent-fraud-label",
        "future-chargeback",
    ]:
        assert forbidden not in rendered


class _RaisingResponses:
    def __init__(self, exc: Exception):
        self.exc = exc

    def create(self, **kwargs):
        raise self.exc


class _StaticResponses:
    def __init__(self, output_text: str):
        self.output_text = output_text

    def create(self, **kwargs):
        return type("Response", (), {"output_text": self.output_text})()


class _Client:
    def __init__(self, responses):
        self.responses = responses


def test_provider_timeout_has_specific_degradation_reason():
    explainer = RiskExplainer(
        api_key="test-key",
        client=_Client(_RaisingResponses(TimeoutError("upstream timed out"))),
    )
    result = explainer.explain(_request())
    assert result.source == "fallback"
    assert result.degradation_reason == "provider_timeout"
    assert explainer.provider_inflight == 0


def test_provider_rate_limit_has_specific_degradation_reason():
    error = RuntimeError("rate limited")
    error.status_code = 429
    explainer = RiskExplainer(
        api_key="test-key",
        client=_Client(_RaisingResponses(error)),
    )
    result = explainer.explain(_request())
    assert result.source == "fallback"
    assert result.degradation_reason == "provider_rate_limited"


def test_invalid_json_is_not_misclassified_as_provider_failure():
    explainer = RiskExplainer(
        api_key="test-key",
        client=_Client(_StaticResponses("not-json")),
    )
    result = explainer.explain(_request())
    assert result.source == "fallback"
    assert result.degradation_reason == "invalid_model_output"


def test_schema_invalid_output_is_classified_as_invalid_model_output():
    invalid = json.dumps(
        {
            "summary": "missing required structured fields",
            "recommended_action": "manual_review",
        }
    )
    explainer = RiskExplainer(
        api_key="test-key",
        client=_Client(_StaticResponses(invalid)),
    )
    result = explainer.explain(_request())
    assert result.source == "fallback"
    assert result.degradation_reason == "invalid_model_output"


def test_default_fallback_reason_uses_correct_chinese_copy():
    request = ExplainRequest(alert={"rule_id": "R001", "risk_level": "MEDIUM"})
    result = fallback_explanation(request)
    assert "风控规则命中" in result.summary
