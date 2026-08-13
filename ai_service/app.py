from __future__ import annotations

import os
import time
import uuid
from threading import Lock

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware

from ai_service.models import ExplainRequest, ExplainResponse, HealthResponse
from ai_service.service import PROMPT_VERSION, RiskExplainer

app = FastAPI(
    title="FinGuard AI Risk Copilot",
    version="0.1.0",
    description="Human-in-the-loop alert explanation and investigation API.",
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
)

explainer = RiskExplainer()


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

    def render(self) -> str:
        with self.lock:
            avg = self.total_latency_ms / self.requests if self.requests else 0.0
            return (
                "# TYPE finguard_ai_requests_total counter\n"
                f"finguard_ai_requests_total {self.requests}\n"
                "# TYPE finguard_ai_fallback_total counter\n"
                f"finguard_ai_fallback_total {self.fallbacks}\n"
                "# TYPE finguard_ai_latency_ms_avg gauge\n"
                f"finguard_ai_latency_ms_avg {avg:.3f}\n"
            )


metrics = RuntimeMetrics()


@app.get("/healthz", response_model=HealthResponse)
def healthz() -> HealthResponse:
    return HealthResponse(
        status="ok",
        llm_enabled=explainer.llm_enabled,
        model=explainer.model,
        prompt_version=PROMPT_VERSION,
    )


@app.post("/v1/explanations", response_model=ExplainResponse)
def explain(request: ExplainRequest) -> ExplainResponse:
    started = time.perf_counter()
    result = explainer.explain(request)
    latency_ms = round((time.perf_counter() - started) * 1000, 3)
    metrics.observe(result.source, latency_ms)
    return ExplainResponse(
        request_id=str(uuid.uuid4()),
        latency_ms=latency_ms,
        explanation=result,
    )


@app.get("/metrics")
def prometheus_metrics() -> Response:
    return Response(content=metrics.render(), media_type="text/plain; version=0.0.4")
