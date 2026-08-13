from ai_service.models import ExplainRequest, FeedbackRequest
from ai_service.service import fallback_explanation, sanitize_context
from ai_service.store import InvestigationStore, context_fingerprint


def _request() -> ExplainRequest:
    return ExplainRequest(
        alert={
            "alert_id": "alert-001",
            "rule_id": "R006",
            "risk_level": "HIGH",
            "reason": "黑名单设备命中",
            "user_id": "user-secret",
            "evidence": {"device_id": "device-secret", "is_black_device": True},
        }
    )


def test_store_persists_only_sanitized_context_and_feedback(tmp_path):
    path = tmp_path / "audit.sqlite3"
    store = InvestigationStore(path)
    request = _request()
    sanitized = sanitize_context(request)
    explanation = fallback_explanation(request)

    fingerprint = store.record_investigation(
        request_id="req-12345678",
        sanitized_context=sanitized,
        explanation=explanation,
        latency_ms=12.3,
    )
    assert fingerprint == context_fingerprint(sanitized)

    raw_db = path.read_bytes()
    assert b"user-secret" not in raw_db
    assert b"device-secret" not in raw_db

    recorded = store.record_feedback(
        FeedbackRequest(
            request_id="req-12345678",
            verdict="true_positive",
            accepted_recommendation=True,
            action_taken="blocked",
            analyst_ref="analyst-a",
        )
    )
    assert recorded is True

    record = store.get_investigation("req-12345678")
    assert record is not None
    assert record.feedback is not None
    assert record.feedback.verdict == "true_positive"
    assert record.feedback.accepted_recommendation is True

    summary = store.quality_summary()
    assert summary.total_investigations == 1
    assert summary.feedback_count == 1
    assert summary.recommendation_acceptance_rate == 1.0
    assert summary.false_positive_rate == 0.0
    store.close()


def test_feedback_is_idempotent_update_not_duplicate(tmp_path):
    store = InvestigationStore(tmp_path / "audit.sqlite3")
    request = _request()
    store.record_investigation(
        request_id="req-abcdefgh",
        sanitized_context=sanitize_context(request),
        explanation=fallback_explanation(request),
        latency_ms=5.0,
    )

    first = FeedbackRequest(
        request_id="req-abcdefgh",
        verdict="uncertain",
        accepted_recommendation=False,
        action_taken="manual_review",
    )
    second = FeedbackRequest(
        request_id="req-abcdefgh",
        verdict="false_positive",
        accepted_recommendation=False,
        action_taken="allowed",
    )
    assert store.record_feedback(first) is True
    assert store.record_feedback(second) is True

    summary = store.quality_summary()
    assert summary.feedback_count == 1
    assert summary.false_positive_count == 1
    assert store.get_investigation("req-abcdefgh").feedback.verdict == "false_positive"
    store.close()


def test_feedback_requires_existing_investigation(tmp_path):
    store = InvestigationStore(tmp_path / "audit.sqlite3")
    missing = FeedbackRequest(
        request_id="req-missing1",
        verdict="uncertain",
        accepted_recommendation=False,
        action_taken="none",
    )
    assert store.record_feedback(missing) is False
    store.close()
