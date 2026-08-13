from threading import Event, Thread

from ai_service.models import ExplainRequest
from ai_service.service import RiskExplainer


class BlockingResponses:
    def __init__(self, entered: Event, release: Event):
        self.entered = entered
        self.release = release
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        self.entered.set()
        assert self.release.wait(timeout=2)
        return type(
            "Response",
            (),
            {
                "output_text": (
                    '{"summary":"ok","recommended_action":"manual_review",'
                    '"confidence":0.8,"key_evidence":["rule_id=R003"],'
                    '"investigation_steps":["review"],"limitations":[]}'
                )
            },
        )()


class BlockingClient:
    def __init__(self, entered: Event, release: Event):
        self.responses = BlockingResponses(entered, release)


def test_provider_bulkhead_falls_back_when_capacity_is_exhausted():
    entered = Event()
    release = Event()
    client = BlockingClient(entered, release)
    explainer = RiskExplainer(
        api_key="test-key",
        client=client,
        max_concurrency=1,
        bulkhead_wait_ms=5,
    )
    request = ExplainRequest(
        alert={"rule_id": "R003", "risk_level": "HIGH", "reason": "device linked to many users"}
    )
    first_result = []
    worker = Thread(target=lambda: first_result.append(explainer.explain(request)))
    worker.start()
    assert entered.wait(timeout=1)
    assert explainer.provider_inflight == 1

    second = explainer.explain(request)
    assert second.source == "fallback"
    assert second.degradation_reason == "bulkhead_saturated"
    assert client.responses.calls == 1

    release.set()
    worker.join(timeout=2)
    assert first_result[0].source == "llm"
    assert explainer.provider_inflight == 0
