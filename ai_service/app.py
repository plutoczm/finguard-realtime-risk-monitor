from __future__ import annotations

import os
import time
import uuid
from threading import Lock

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware

from ai_service.models import (
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
    version="0.2.0",
    description="Human-in-the-loop alert explanation, audit and analyst feedback API.",
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
    allow_methods=["GET", "POST"],
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

    def observe(self, source: str, latency_ms: float) -> None:
        with self.lock:
            self.requests += 1
            self.fallbacks += int(source == "fallback")
            self.total_latency_ms += latency_ms

    def render(self, quality: QualitySummary) -> str:
        with self.lock:
            avg = self.total_latency_ms / self.requests if self.requests else 0.0
            return (
                "# TYPE finguard_ai_requests_total counter\n"
                f"finguard_ai_requests_total {self.requests}\n"
                "# TYPE finguard_ai_fallback_total counter\n"
                f"finguard_ai_fallback_total {self.fallbacks}\n"
                "# TYPE finguard_ai_latency_ms_avg gauge\n"
                f"finguard_ai_latency_ms_avg {avg:.3f}\n"
                "# TYPE finguard_ai_feedback_total gauge\n"
                f"finguard_ai_feedback_total {quality.feedback_count}\n"
                "# TYPE finguard_ai_recommendation_acceptance_ratio gauge\n"
                f"finguard_ai_recommendation_acceptance_ratio {quality.recommendation_acceptance_rate:.4f}\n"
                "# TYPE finguard_ai_false_positive_ratio gauge\n"
                f"finguard_ai_false_positive_ratio {quality.false_positive_rate:.4f}\n"
            )


metrics = RuntimeMetrics()


@app.get("/healthz", response_model=HealthResponse)
def healthz() -> HealthResponse:
    return HealthResponse(
        status="ok",
        llm_enabled=explainer.llm_enabled,
        model=explainer.model,
        prompt_version=PROMPT_VERSION,
        provider_circuit_open=explainer.circuit_open,
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
    metrics.observe(result.source, latency_ms)
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


@app.get("/metrics")
def prometheus_metrics() -> Response:
    return Response(
        content=metrics.render(store.quality_summary()),
        media_type="text/plain; version=0.0.4",
    )
