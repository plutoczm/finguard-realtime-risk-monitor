# Performance, Capacity and Benchmarking

FinGuard uses reproducible benchmarks and does not claim production performance without measured evidence.

Run `make ai-benchmark` against a running Copilot. The report captures HTTP success rate, throughput, client/server latency, LLM/fallback share and degradation reasons.

Provider capacity is protected by a process-local concurrency bulkhead. If no provider slot is available within `FINGUARD_AI_BULKHEAD_WAIT_MS`, the request uses deterministic fallback with `degradation_reason=bulkhead_saturated` instead of waiting indefinitely.

CI runs a small fallback-mode live HTTP smoke benchmark with a loose gate. It is a regression check, not a production SLO claim.

Before using performance numbers on a resume, record the machine, commit SHA, Kafka partitions, Flink parallelism, input QPS, AI model/fallback mode, concurrency, warmup and request count. Keep Flink detection latency separate from AI investigation latency because the model is outside the hard realtime detection path.
