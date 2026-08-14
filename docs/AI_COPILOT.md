# AI Risk Copilot

## Why this AI layer exists

The Flink job remains the deterministic, low-latency detection plane. The LLM is deliberately placed after rule detection, where it can improve analyst throughput without becoming a single point of failure for payment authorization.

The Copilot converts a structured `RiskAlert` plus minimized **event-time available context** into an analyst summary, recommended action, grounded evidence, investigation steps and explicit limitations. Investigations that need continuing ownership can be promoted into a case, then resolved by a human analyst.

## Runtime flow

```text
RiskAlert
  -> event-time feature / post-event label boundary
  -> PII minimization
  -> versioned structured prompt
  -> LLM or deterministic fallback
  -> audit record (sanitized context only)
  -> optional Case: OPEN -> INVESTIGATING -> RESOLVED
  -> analyst verdict / recommendation acceptance
  -> quality + case workload metrics
```

## Model-input timing policy

A risk model or Copilot can only be evaluated honestly if it sees information that would actually exist at investigation time. FinGuard therefore separates **online features** from **post-event supervision labels**.

Allowed model context includes rule id/level/reason, event-time amounts, channel/city/status, blacklist indicators, window evidence and pseudonymized entity references.

The online prompt/audit context explicitly drops outcome fields such as:

- `risk_label` / `fraud_label`;
- `chargeback_label`;
- `analyst_verdict` / `resolution_verdict`;
- `ground_truth` / `target_label`.

This denylist is recursive for nested alert evidence and also applies to transaction/recent-event context. Those labels may be used later for offline evaluation, dataset construction or feedback analysis, but they must never leak back into the input that produced the prediction/explanation being scored.

## Reliability and safety boundaries

1. **No autonomous authorization**: the model cannot approve or reject a payment.
2. **Event-time feature boundary**: post-event labels/verdicts are excluded from online model and sanitized audit context to prevent target leakage.
3. **PII minimization**: identifiers are pseudonymized, raw IP is removed and nested evidence is recursively sanitized.
4. **Audit-safe persistence**: SQLite stores only sanitized context, structured output, case metadata and analyst feedback; raw transaction payloads are not persisted by the Copilot.
5. **Grounding contract**: the prompt forbids facts outside supplied context.
6. **Structured Outputs**: provider output is constrained to a JSON schema and validated again by Pydantic.
7. **Typed degradation**: missing credentials, provider timeout, rate limit, generic provider error, invalid structured output, circuit-open and bulkhead saturation are distinguishable operational reasons rather than one undifferentiated fallback bucket.
8. **Deterministic fallback**: all typed failure modes continue to return an auditable rule-based explanation.
9. **Circuit breaker**: repeated provider or invalid-output failures temporarily stop model calls and keep serving deterministic fallback instead of hammering an unhealthy upstream.
10. **Request traceability**: every explanation has `request_id`, `input_fingerprint`, `prompt_version`, source and latency.
11. **Idempotent analyst feedback**: feedback is keyed by `request_id`; resubmission updates the existing judgment instead of creating duplicates.
12. **Case concurrency control**: case mutation requires `expected_version`; stale updates fail with HTTP 409.
13. **Case event history**: creation, update, resolution and reopen are retained as append-only workflow events.
14. **Golden-set evaluation**: `python -m ai_service.eval` validates deterministic action/evidence expectations without credentials.

## Investigation vs Case

An Investigation is the immutable AI/audit unit tied to one `request_id`.

A Case is optional operational state for investigations that need continuing work:

- unique per investigation;
- status: `open`, `investigating`, `resolved`;
- priority + SLA;
- optional analyst assignment;
- explicit resolution verdict and action;
- versioned updates;
- event history.

This distinction avoids turning every model call into a fake ticket while still supporting realistic analyst operations.

## API surface

Investigation and quality:

- `GET /healthz`: liveness plus model/circuit state.
- `GET /readyz`: readiness check for the local audit store.
- `POST /v1/explanations`: generate and persist an auditable investigation result.
- `POST /v1/feedback`: record or update the analyst verdict for a request.
- `GET /v1/investigations/{request_id}`: retrieve non-sensitive investigation metadata and feedback.
- `GET /v1/quality/summary`: aggregate recommendation acceptance, false-positive and latency metrics.

Case workflow:

- `POST /v1/cases`: idempotently promote an investigation into a case.
- `GET /v1/cases`: filter/paginate cases.
- `GET /v1/cases/summary`: active workload, SLA breach and assignment summary.
- `GET /v1/cases/{case_id}`: retrieve a case.
- `PATCH /v1/cases/{case_id}`: version-checked case mutation.
- `GET /v1/cases/{case_id}/events`: retrieve workflow history.

Observability:

- `GET /metrics`: Prometheus text format for runtime, feedback and case metrics.

Without `OPENAI_API_KEY`, the service remains fully usable in deterministic fallback mode, including audit, case management and analyst feedback.

## Case SLA defaults

| Priority | SLA |
|---|---:|
| critical | 15 min |
| high | 60 min |
| medium | 4 h |
| low | 24 h |

Risk level maps to priority by default, but the analyst can change priority. Changing priority recalculates the target due time from case creation time.

## Resolution semantics

A case cannot become `resolved` without:

- `resolution_verdict`;
- `action_taken`.

If `accepted_recommendation` is supplied at resolution, case disposition and AI-quality feedback are written in the same transaction.

Reopening a resolved case clears the current final disposition/feedback label but preserves historical case events.

## Quality loop

The project distinguishes **offline gates**, **online model inputs** and **post-event feedback**:

- offline golden cases catch prompt/action regressions before merge;
- online model inputs contain only event-time available, minimized context;
- analyst verdicts, recommendation acceptance, chargeback/fraud outcomes and similar labels are downstream supervision signals, not features for the request they evaluate;
- online analyst verdicts measure whether suggested actions are actually accepted;
- false-positive feedback identifies rules or explanations that need investigation;
- case SLA/workload metrics measure operational handling, not model quality;
- `prompt_version` and `input_fingerprint` make later comparisons reproducible.

Metrics that still require a real deployment/load test before making claims include p95/p99 latency, token cost per investigation and analyst handling-time reduction.

## Deployment boundary

SQLite is intentionally used for the current single-process local/portfolio runtime. It is not presented as a horizontally scalable shared case database. A multi-replica/network deployment would require shared transactional persistence plus authentication/RBAC before rollout.
