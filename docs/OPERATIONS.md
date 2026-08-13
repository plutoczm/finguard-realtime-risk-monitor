# FinGuard Operations Runbook

This runbook covers the local/portfolio deployment boundary. It documents failure handling without pretending the repository is a full production platform.

## Health checks

| Surface | Check | Healthy signal |
|---|---|---|
| Kafka | `docker compose ps` | broker healthy |
| Flink | `http://127.0.0.1:8081` | JobManager reachable and job running |
| AI liveness | `GET http://127.0.0.1:8091/healthz` | `status=ok` |
| AI readiness | `GET http://127.0.0.1:8091/readyz` | `status=ready`, audit store `ok` |
| AI metrics | `GET http://127.0.0.1:8091/metrics` | counters/gauges returned |
| Case workload | `GET http://127.0.0.1:8091/v1/cases/summary` | active/SLA counts returned |

## Failure modes

### Provider unavailable or slow

Expected behavior: explanation requests fall back to deterministic output. After repeated failures, the circuit breaker pauses upstream model calls for a cooldown period. Flink risk detection is unaffected.

Check `provider_circuit_open` in `/healthz` and `finguard_ai_fallback_total` in `/metrics`.

### Audit store unavailable

`/readyz` returns 503. Explanation requests also return 503 rather than emitting an unaudited AI recommendation. Restore write access or reset the local state volume before retrying.

Docker state is stored in the `finguard_ai_state` named volume. Local `make ai` stores the SQLite file under `data/ai_copilot/` by default.

### Case update conflict

Case mutation uses optimistic concurrency. Every `PATCH /v1/cases/{case_id}` carries `expected_version`.

If another analyst or browser tab has updated the case first, the API returns HTTP 409. The client should refresh the latest case and retry intentionally; it must not blindly overwrite the newer state.

### SLA breach

`GET /v1/cases/summary` reports `sla_breached_count`, and `/metrics` exposes `finguard_cases_sla_breached`.

The local workbench sorts higher-priority cases first and then by due time. A breach is an operational prioritization signal; it does not alter the underlying Flink risk decision.

### Reopened case

Reopening transitions `RESOLVED -> INVESTIGATING`.

The previous resolution remains in `case_events` for audit history, but the current `resolution_verdict`, `action_taken`, `resolved_at` and analyst-feedback label are cleared. This prevents a reopened case from remaining counted as a final labeled outcome.

### Kafka backlog / Flink backpressure

Check Kafka consumer lag, Flink Back Pressure, busy time and checkpoint duration. Only increase partitions/parallelism after identifying an actual bottleneck. The project intentionally avoids speculative scaling components.

### Bad or duplicate analyst feedback

Feedback writes are idempotent by `request_id`. A repeated submission updates the existing verdict. Unknown request IDs return 404 and are not inserted.

## Case workflow operator checks

Useful endpoints:

```text
POST  /v1/cases
GET   /v1/cases?status=investigating&priority=high
GET   /v1/cases/summary
GET   /v1/cases/{case_id}
PATCH /v1/cases/{case_id}
GET   /v1/cases/{case_id}/events
```

Default SLA targets:

| Priority | SLA |
|---|---:|
| critical | 15 min |
| high | 60 min |
| medium | 4 h |
| low | 24 h |

These are portfolio defaults, not claims about a real financial institution's policy.

## Recovery and reset

```bash
make clean
```

This removes Docker volumes plus generated runtime/audit data. It is destructive and intended only for local reset.

## Security boundary

Local Docker ports are bound to `127.0.0.1`. The Copilot container runs as a non-root user. The static Vercel demo contains no model credentials and does not write cases or analyst feedback.

The current SQLite store assumes one AI service instance. Before exposing the service to a shared network or running multiple replicas, add identity/RBAC, secrets management and a shared transactional persistence layer. Those are explicit production prerequisites rather than hidden assumptions.
