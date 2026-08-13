# FinGuard Operations Runbook

This runbook covers the local/portfolio deployment boundary without pretending the repository is a full production platform.

## Health checks

| Surface | Check | Healthy signal |
|---|---|---|
| Kafka | `docker compose ps` | broker healthy |
| Flink | `http://127.0.0.1:8081` | JobManager reachable and job running |
| AI liveness | `GET /healthz` | process/model/capacity state returned |
| AI readiness | `GET /readyz` | audit store `ok` |
| AI metrics | `GET /metrics` | request/degradation/capacity metrics returned |
| Case workload | `GET /v1/cases/summary` | active/SLA counts returned |

`/healthz` also exposes `provider_circuit_open`, `provider_inflight` and `provider_max_concurrency`.

## Provider unavailable or slow

Explanation requests fall back deterministically. Repeated failures open the circuit breaker for a cooldown period. Flink risk detection is unaffected. Check the provider circuit state and `finguard_ai_degradation_total{reason="provider_error"}`.

## Provider capacity saturated

The Copilot uses a process-local provider bulkhead. At most `FINGUARD_AI_MAX_CONCURRENCY` model calls can be in flight. If no slot is available within `FINGUARD_AI_BULKHEAD_WAIT_MS`, the request uses deterministic fallback instead of building an unbounded wait queue.

Expected result: `source=fallback`, `degradation_reason=bulkhead_saturated`.

Increase concurrency only after measuring provider quota, latency and local resource behavior.

## Audit store unavailable

`/readyz` returns 503. Explanation requests also return 503 rather than emitting an unaudited recommendation. Docker state is stored in `finguard_ai_state`; local `make ai` uses `data/ai_copilot/` by default.

## Case conflict, SLA and reopen semantics

Every `PATCH /v1/cases/{case_id}` carries `expected_version`; stale updates return HTTP 409. `GET /v1/cases/summary` reports SLA breaches. Reopening `RESOLVED -> INVESTIGATING` preserves historical events but clears the current resolution and feedback label until resolution happens again.

## Kafka backlog / Flink backpressure

Check Kafka consumer lag, Flink Back Pressure, busy time and checkpoint duration. Increase partitions or parallelism only after identifying an actual bottleneck.

## Benchmark and capacity checks

Run `make ai-benchmark` against a running Copilot. Credential-free fallback mode is appropriate for infrastructure testing. A benchmark against a real provider key can incur actual model usage.

CI runs a small live fallback-mode benchmark with a deliberately loose regression gate: 100% success and client p95 below 2000 ms. This is not a production SLO claim. See `docs/PERFORMANCE.md`.

## Recovery and scaling boundary

`make clean` removes Docker volumes and generated runtime/audit data; it is destructive and intended only for local reset.

Local ports bind to `127.0.0.1`; the Copilot container runs as non-root. SQLite and the provider bulkhead are single-instance mechanisms. Before multi-replica/shared-network deployment, add identity/RBAC, secrets management, shared transactional persistence and a provider-wide quota/capacity policy.
