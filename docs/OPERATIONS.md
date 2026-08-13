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

## Failure modes

### Provider unavailable or slow

Expected behavior: explanation requests fall back to deterministic output. After repeated failures, the circuit breaker pauses upstream model calls for a cooldown period. Flink risk detection is unaffected.

Check `provider_circuit_open` in `/healthz` and `finguard_ai_fallback_total` in `/metrics`.

### Audit store unavailable

`/readyz` returns 503. Explanation requests also return 503 rather than emitting an unaudited AI recommendation. Restore write access or reset the local state volume before retrying.

Docker state is stored in the `finguard_ai_state` named volume. Local `make ai` stores the SQLite file under `data/ai_copilot/` by default.

### Kafka backlog / Flink backpressure

Check Kafka consumer lag, Flink Back Pressure, busy time and checkpoint duration. Only increase partitions/parallelism after identifying an actual bottleneck. The project intentionally avoids speculative scaling components.

### Bad or duplicate analyst feedback

Feedback writes are idempotent by `request_id`. A repeated submission updates the existing verdict. Unknown request IDs return 404 and are not inserted.

## Recovery and reset

```bash
make clean
```

This removes Docker volumes plus generated runtime/audit data. It is destructive and intended only for local reset.

## Security boundary

Local Docker ports are bound to `127.0.0.1`. The Copilot container runs as a non-root user. The static Vercel demo contains no model credentials and does not write analyst feedback.
