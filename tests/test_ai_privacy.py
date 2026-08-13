from ai_service.models import ExplainRequest
from ai_service.service import fallback_explanation, sanitize_context


def test_explicit_sensitive_fields_are_redacted_before_model_or_audit_boundary():
    request = ExplainRequest(
        alert={
            "rule_id": "R006",
            "risk_level": "HIGH",
            "reason": "black device",
            "evidence": {
                "email": "alice@example.com",
                "phone": "13800000000",
                "nested": {
                    "full_name": "Sensitive Person",
                    "address": "Secret Street 1",
                    "access_token": "token-secret",
                    "account_id": "acct-secret",
                },
            },
        },
        recent_events=[
            {
                "user_id": "recent-user",
                "device_id": "recent-device",
                "email": "recent@example.com",
            }
        ],
    )

    sanitized = str(sanitize_context(request))
    rendered = str(fallback_explanation(request))
    for secret in [
        "alice@example.com",
        "13800000000",
        "Sensitive Person",
        "Secret Street 1",
        "token-secret",
        "acct-secret",
        "recent-user",
        "recent-device",
        "recent@example.com",
    ]:
        assert secret not in sanitized
        assert secret not in rendered

    assert "[redacted]" in sanitized
    assert "ref_" in sanitized
