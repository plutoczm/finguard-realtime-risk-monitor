from __future__ import annotations

import os
import time
import uuid
from collections import Counter
from threading import Lock

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware

from ai_service.models import (
    CaseCreateRequest,
    CaseEvent,
    CaseListResponse,
    CasePriority,
    CaseRecord,
    CaseStatus,
    CaseSummary,
    CaseUpdateRequest,
    ExplainRequest,
    ExplainResponse,
    FeedbackRequest,
    FeedbackResponse,
    HealthResponse,
    InvestigationRecord,
    QualitySummary,
    ReadyResponse,
)
from ai_service.service import PROMPT_VERSION, RiskExplainer, sanitize_context
from ai_service.store import InvestigationStore

app = FastAPI(
    title="FinGuard AI Risk Copilot",
    version="0.4.0",
    description="Human-in-the-loop risk investigation, case operations, capacity protection and feedback API.",
)

allowed_origins = [
    origin.strip()
    for origin in os.getenv(
        "FINGUARD_CORS_ORIGINS",
        "http://127.0.0.1:8090,http://localhost:8090",
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Content-Type"],
    expose_headers=["X-Request-ID"],
)

explainer = RiskExplainer()
store = InvestigationStore()


class RuntimeMetrics:
    def __init__(self) -> None:
        self.lock = Lock()
        self.requests = 0
        self.fallbacks = 0
        self.total_latency_ms = 0.0
        self.degradations: Counter[str] = Counter()

    def observe(self, source: str, latency_ms: float, degradation_reason: str | None) -> None:
        with self.lock:
            self.requests += 1
            self.fallbacks += int(source == "fallback")
            self.total_latency_ms += latency_ms
            if degradation_reason:
                self.degradations[degradation_reason] += 1

    def render(
        self,
        quality: QualitySummary,
        cases: CaseSummary,
        *,
        provider_inflight: int,
        provider_capacity: int,
    ) -> str:
        with self.lock:
            avg = self.total_latency_ms / self.requests if self.requests else 0.0
            lines = [
                "# TYPE finguard_ai_requests_total counter",
                f"finguard_ai_requests_total {self.requests}",
                "# TYPE finguard_ai_fallback_total counter",
                f"finguard_ai_fallback_total {self.fallbacks}",
                "# TYPE finguard_ai_latency_ms_avg gauge",
                f"finguard_ai_latency_ms_avg {avg:.3f}",
                "# TYPE finguard_ai_provider_inflight gauge",
                f"finguard_ai_provider_inflight {provider_inflight}",
                "# TYPE finguard_ai_provider_capacity gauge",
                f"finguard_ai_provider_capacity {provider_capacity}",
                "# TYPE finguard_ai_degradation_total counter",
            ]
            for reason in (
                "missing_credentials",
                "provider_error",
                "circuit_open",
                "bulkhead_saturated",
            ):
                lines.append(
                    f'finguard_ai_degradation_total{{reason="{reason}"}} {self.degradations[reason]}'
                )
            lines.extend(
                [
                    "# TYPE finguard_ai_feedback_total gauge",
                    f"finguard_ai_feedback_total {quality.feedback_count}",
                    "# TYPE finguard_ai_recommendation_acceptance_ratio gauge",
                    f"finguard_ai_recommendation_acceptance_ratio {quality.recommendation_acceptance_rate:.4f}",
                    "# TYPE finguard_ai_false_positive_ratio gauge",
                    f"finguard_ai_false_positive_ratio {quality.false_positive_rate:.4f}",
                    "# TYPE finguard_cases_open gauge",
                    f"finguard_cases_open {cases.open_count}",
                    "# TYPE finguard_cases_investigating gauge",
                    f"finguard_cases_investigating {cases.investigating_count}",
                    "# TYPE finguard_cases_sla_breached gauge",
                    f"finguard_cases_sla_breached {cases.sla_breached_count}",
                    "# TYPE finguard_cases_unassigned gauge",
                    f"finguard_cases_unassigned {cases.unassigned_count}",
                ]
            )
            return "\n".join(lines) + "\n"


metrics = RuntimeMetrics()


@app.get("/healthz", response_model=HealthResponse)
def healthz() -> HealthResponse:
    return HealthResponse(
        status="ok",
        llm_enabled=explainer.llm_enabled,
        model=explainer.model,
        prompt_version=PROMPT_VERSION,
        provider_circuit_open=explainer.circuit_open,
        provider_inflight=explainer.provider_inflight,
        provider_max_concurrency=explainer.max_concurrency,
    )


@app.get("/readyz", response_model=ReadyResponse)
def readyz() -> ReadyResponse:
    if not store.ping():
        raise HTTPException(status_code=503, detail="audit store unavailable")
    return ReadyResponse(status="ready", audit_store="ok")


@app.post("/v1/explanations", response_model=ExplainResponse)
def explain(request: ExplainRequest, response: Response) -> ExplainResponse:
    request_id = str(uuid.uuid4())
    started = time.perf_counter()
    result = explainer.explain(request)
    latency_ms = round((time.perf_counter() - started) * 1000, 3)
    sanitized_context = sanitize_context(request)
    try:
        fingerprint = store.record_investigation(
            request_id=request_id,
            sanitized_context=sanitized_context,
            explanation=result,
            latency_ms=latency_ms,
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail="audit store unavailable") from exc
    metrics.observe(result.source, latency_ms, result.degradation_reason)
    response.headers["X-Request-ID"] = request_id
    return ExplainResponse(
        request_id=request_id,
        latency_ms=latency_ms,
        input_fingerprint=fingerprint,
        explanation=result,
    )


@app.post("/v1/feedback", response_model=FeedbackResponse)
def record_feedback(feedback: FeedbackRequest) -> FeedbackResponse:
    if not store.record_feedback(feedback):
        raise HTTPException(status_code=404, detail="investigation request_id not found")
    return FeedbackResponse(request_id=feedback.request_id)


@app.get("/v1/investigations/{request_id}", response_model=InvestigationRecord)
def get_investigation(request_id: str) -> InvestigationRecord:
    record = store.get_investigation(request_id)
    if record is None:
        raise HTTPException(status_code=404, detail="investigation request_id not found")
    return record


@app.get("/v1/quality/summary", response_model=QualitySummary)
def quality_summary() -> QualitySummary:
    return store.quality_summary()


@app.post("/v1/cases", response_model=CaseRecord)
def create_case(request: CaseCreateRequest) -> CaseRecord:
    record = store.create_case(request)
    if record is None:
        raise HTTPException(status_code=404, detail="investigation request_id not found")
    return record


@app.get("/v1/cases", response_model=CaseListResponse)
def list_cases(
    status: CaseStatus | None = None,
    priority: CasePriority | None = None,
    assignee_ref: str | None = Query(default=None, max_length=64),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> CaseListResponse:
    return store.list_cases(
        status=status,
        priority=priority,
        assignee_ref=assignee_ref,
        limit=limit,
        offset=offset,
    )


@app.get("/v1/cases/summary", response_model=CaseSummary)
def case_summary() -> CaseSummary:
    return store.case_summary()


@app.get("/v1/cases/{case_id}", response_model=CaseRecord)
def get_case(case_id: str) -> CaseRecord:
    record = store.get_case(case_id)
    if record is None:
        raise HTTPException(status_code=404, detail="case not found")
    return record


@app.patch("/v1/cases/{case_id}", response_model=CaseRecord)
def update_case(case_id: str, request: CaseUpdateRequest) -> CaseRecord:
    status, record = store.update_case(case_id, request)
    if status == "not_found":
        raise HTTPException(status_code=404, detail="case not found")
    if status == "version_conflict":
        raise HTTPException(
            status_code=409,
            detail={
                "message": "case version conflict; refresh before retrying",
                "current_version": record.version if record else None,
            },
        )
    if status == "invalid_transition":
        raise HTTPException(status_code=422, detail="invalid case status transition")
    if status == "resolution_required":
        raise HTTPException(
            status_code=422,
            detail="resolved cases require resolution_verdict and action_taken",
        )
    if status == "feedback_requires_resolution":
        raise HTTPException(
            status_code=422,
            detail="accepted_recommendation requires resolution_verdict and action_taken",
        )
    assert record is not None
    return record


@app.get("/v1/cases/{case_id}/events", response_model=list[CaseEvent])
def list_case_events(case_id: str) -> list[CaseEvent]:
    events = store.list_case_events(case_id)
    if events is None:
        raise HTTPException(status_code=404, detail="case not found")
    return events


@app.get("/metrics")
def prometheus_metrics() -> Response:
    return Response(
        content=metrics.render(
            store.quality_summary(),
            store.case_summary(),
            provider_inflight=explainer.provider_inflight,
            provider_capacity=explainer.max_concurrency,
        ),
        media_type="text/plain; version=0.0.4",
    )
