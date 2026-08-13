import sqlite3

from ai_service.models import CaseCreateRequest, CaseUpdateRequest, RiskExplanation
from ai_service.store import InvestigationStore


def _seed(store: InvestigationStore, request_id: str, risk_level: str = "HIGH") -> None:
    explanation = RiskExplanation(
        summary="test",
        recommended_action="block_recommended",
        confidence=0.8,
        key_evidence=["rule_id=R006"],
        investigation_steps=["review"],
        limitations=[],
        source="fallback",
        prompt_version="test-v1",
    )
    store.record_investigation(
        request_id=request_id,
        sanitized_context={
            "alert": {
                "alert_ref": "alt_test",
                "rule_id": "R006",
                "risk_level": risk_level,
            }
        },
        explanation=explanation,
        latency_ms=5.0,
    )


def test_case_creation_is_idempotent_and_assigns_sla(tmp_path):
    store = InvestigationStore(tmp_path / "audit.sqlite3")
    _seed(store, "req-case-0001")

    first = store.create_case(CaseCreateRequest(request_id="req-case-0001"))
    second = store.create_case(CaseCreateRequest(request_id="req-case-0001"))

    assert first is not None
    assert second is not None
    assert first.case_id == second.case_id
    assert first.priority == "high"
    assert first.status == "open"
    assert first.version == 1
    assert first.due_at > first.created_at

    summary = store.case_summary()
    assert summary.open_count == 1
    assert summary.unassigned_count == 1
    store.close()


def test_case_updates_use_optimistic_locking(tmp_path):
    store = InvestigationStore(tmp_path / "audit.sqlite3")
    _seed(store, "req-case-0002")
    case = store.create_case(CaseCreateRequest(request_id="req-case-0002"))

    status, updated = store.update_case(
        case.case_id,
        CaseUpdateRequest(
            expected_version=1,
            status="investigating",
            assignee_ref="analyst-a",
            actor_ref="analyst-a",
        ),
    )
    assert status == "updated"
    assert updated.version == 2
    assert updated.status == "investigating"

    stale_status, current = store.update_case(
        case.case_id,
        CaseUpdateRequest(expected_version=1, priority="critical"),
    )
    assert stale_status == "version_conflict"
    assert current.version == 2
    assert current.priority == "high"
    store.close()


def test_case_resolution_records_feedback_and_reopen_invalidates_final_label(tmp_path):
    store = InvestigationStore(tmp_path / "audit.sqlite3")
    _seed(store, "req-case-0003")
    case = store.create_case(
        CaseCreateRequest(request_id="req-case-0003", assignee_ref="analyst-a")
    )

    status, investigating = store.update_case(
        case.case_id,
        CaseUpdateRequest(
            expected_version=1,
            status="investigating",
            actor_ref="analyst-a",
        ),
    )
    assert status == "updated"

    status, resolved = store.update_case(
        case.case_id,
        CaseUpdateRequest(
            expected_version=investigating.version,
            status="resolved",
            resolution_verdict="true_positive",
            accepted_recommendation=True,
            action_taken="blocked",
            actor_ref="analyst-a",
        ),
    )
    assert status == "updated"
    assert resolved.status == "resolved"
    assert resolved.resolved_at is not None

    feedback = store.get_investigation("req-case-0003").feedback
    assert feedback is not None
    assert feedback.verdict == "true_positive"
    assert feedback.accepted_recommendation is True

    events = store.list_case_events(case.case_id)
    assert [event.event_type for event in events] == ["created", "updated", "resolved"]

    status, reopened = store.update_case(
        case.case_id,
        CaseUpdateRequest(
            expected_version=resolved.version,
            status="investigating",
            actor_ref="analyst-b",
        ),
    )
    assert status == "updated"
    assert reopened.status == "investigating"
    assert reopened.resolution_verdict is None
    assert reopened.resolved_at is None
    assert store.get_investigation("req-case-0003").feedback is None
    assert store.list_case_events(case.case_id)[-1].event_type == "reopened"
    store.close()


def test_case_resolution_requires_explicit_outcome(tmp_path):
    store = InvestigationStore(tmp_path / "audit.sqlite3")
    _seed(store, "req-case-0004")
    case = store.create_case(CaseCreateRequest(request_id="req-case-0004"))

    status, current = store.update_case(
        case.case_id,
        CaseUpdateRequest(expected_version=1, status="resolved"),
    )
    assert status == "resolution_required"
    assert current.status == "open"
    assert current.version == 1
    store.close()


def test_case_list_filters_and_schema_v1_migrates(tmp_path):
    path = tmp_path / "audit.sqlite3"
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA user_version = 1")
    connection.commit()
    connection.close()

    store = InvestigationStore(path)
    _seed(store, "req-case-0005", risk_level="CRITICAL")
    _seed(store, "req-case-0006", risk_level="MEDIUM")
    critical = store.create_case(CaseCreateRequest(request_id="req-case-0005"))
    medium = store.create_case(
        CaseCreateRequest(request_id="req-case-0006", assignee_ref="analyst-c")
    )

    assert critical.priority == "critical"
    assert medium.priority == "medium"
    filtered = store.list_cases(priority="critical")
    assert filtered.total == 1
    assert filtered.items[0].case_id == critical.case_id

    version = store._connection.execute("PRAGMA user_version").fetchone()[0]
    assert version == 2
    store.close()
