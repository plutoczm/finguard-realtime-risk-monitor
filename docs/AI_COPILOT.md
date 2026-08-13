# AI Risk Copilot

## Why this AI layer exists

The Flink job remains the deterministic, low-latency detection plane. The LLM is deliberately placed after rule detection, where it can improve analyst throughput without becoming a single point of failure for payment authorization.

The Copilot converts a structured `RiskAlert` plus minimized context into an analyst summary, recommended action, grounded evidence, investigation steps and explicit limitations. The analyst then records a final verdict, closing the loop between model output and real human review.

## Runtime flow

```text
RiskAlert
  -> PII minimization
  -> versioned structured prompt
  -> LLM or deterministic fallback
  -> audit record (sanitized context only)
  -> analyst verdict / recommendation acceptance
  -> quality summary for evaluation
```

## Reliability and safety boundaries

1. **No autonomous authorization**: the model cannot approve or reject a payment.
2. **PII minimization**: identifiers are pseudonymized, raw IP is removed and nested evidence is recursively sanitized.
3. **Audit-safe persistence**: SQLite stores only sanitized context, structured output and analyst feedback; raw transaction payloads are not persisted by the Copilot.
4. **Grounding contract**: the prompt forbids facts outside supplied context.
5. **Structured Outputs**: provider output is constrained to a JSON schema.
6. **Deterministic fallback**: missing credentials, timeout, provider error, parse error or schema failure returns a rule-based explanation.
7. **Circuit breaker**: repeated provider failures temporarily stop model calls and keep serving deterministic fallback instead of hammering an unhealthy upstream.
8. **Request traceability**: every explanation has `request_id`, `input_fingerprint`, `prompt_version`, source and latency.
9. **Idempotent analyst feedback**: feedback is keyed by `request_id`; resubmission updates the existing judgment instead of creating duplicates.
10. **Golden-set evaluation**: `python -m ai_service.eval` validates deterministic action/evidence expectations without credentials.

## API surface

- `GET /healthz`: liveness plus model/circuit state.
- `GET /readyz`: readiness check for the local audit store.
- `POST /v1/explanations`: generate and persist an auditable investigation result.
- `POST /v1/feedback`: record or update the analyst verdict for a request.
- `GET /v1/investigations/{request_id}`: retrieve non-sensitive investigation metadata and feedback.
- `GET /v1/quality/summary`: aggregate recommendation acceptance, false-positive and latency metrics.
- `GET /metrics`: Prometheus text format for runtime and feedback metrics.

Without `OPENAI_API_KEY`, the service remains fully usable in deterministic fallback mode, including audit and analyst feedback.

## Quality loop

The project now distinguishes **offline gates** from **online feedback**:

- offline golden cases catch prompt/action regressions before merge;
- online analyst verdicts measure whether suggested actions are actually accepted;
- false-positive feedback identifies rules or explanations that need investigation;
- `prompt_version` and `input_fingerprint` make later comparisons reproducible.

Metrics that still require a real deployment/load test before making claims include p95/p99 latency, token cost per investigation and analyst handling-time reduction.
