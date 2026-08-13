# Performance, Capacity and Benchmarking

FinGuard separates **AI investigation performance** from the **deterministic streaming plane**. The repository does not claim production throughput or p95/p99 latency without a saved benchmark result and a documented environment.

## AI investigation benchmark

Run a local Copilot and execute:

```bash
make ai-benchmark
```

The report captures HTTP success rate, throughput, client/server latency, LLM/fallback share and structured degradation reasons. Provider capacity is protected by the process-local concurrency bulkhead; saturation falls back deterministically instead of creating an unbounded request queue.

CI runs a small credential-free fallback benchmark as a regression gate. Those CI-runner numbers are **not** resume performance claims.

## Streaming-plane benchmark

Start Kafka/Flink, create the transaction topic and submit `RiskMonitorJob`, then run:

```bash
make stream-benchmark
```

`scripts/benchmark_streaming.py` drives the existing Python producer and samples the running system instead of benchmarking isolated helper functions. It records:

- requested events/QPS and producer process achieved QPS;
- Kafka `finguard-risk-monitor` consumer-group lag, including peak and final lag;
- Kafka-source vertex `metrics.write-records` delta and processed ratio;
- maximum Flink `backPressuredTimeMsPerSecond` and `busyTimeMsPerSecond` observed across vertices;
- `lastCheckpointDuration`, completed/failed checkpoint counts and latest checkpoint duration;
- Flink restart delta;
- drain time after the producer finishes;
- commit SHA, Flink version, job ID and source vertex name.

The benchmark gates final lag, processed ratio and restart count. Optional gates can also require completed checkpoints or bound observed backpressure.

The source processed-count intentionally comes from the job-detail vertex I/O counters rather than relying on `numRecordsOut` being registered immediately on a newly started aggregated-metrics endpoint. Backpressure/busy-time still use Flink's aggregated task-metrics surface.

## End-to-end CI evidence

`.github/workflows/streaming-benchmark.yml` runs the real local stack when streaming-related files change and can also be started manually. The PR smoke profile intentionally uses a low-pressure workload long enough to cross the default 60-second checkpoint interval. It verifies:

1. the Kafka consumer group drains to zero lag;
2. the Flink source processes at least the configured ratio of sent records;
3. the job does not restart during the run;
4. at least one checkpoint completes;
5. a JSON benchmark artifact is retained for inspection.

Failure runs also retain a diagnostic archive with Flink job state, exceptions, checkpoints and available vertex metrics. This turns integration failures into inspectable evidence instead of a generic red CI status.

### Current CI reliability baseline

Streaming benchmark run 9 on the GitHub-hosted Ubuntu runner used 6,500 events at a requested 100 QPS and passed all reliability gates:

| Signal | Observed |
|---|---:|
| Producer achieved QPS | 90.963 |
| Source processed records | 6,500 / 6,500 |
| Processed ratio | 1.0000 |
| Peak Kafka consumer-group lag | 1,787 |
| Final Kafka consumer-group lag | 0 |
| Max observed backpressure | 0 ms/s |
| Max observed busy time | 1,000 ms/s |
| Flink restart delta | 0 |
| Completed checkpoints | 2 |
| Failed checkpoints | 0 |
| Max observed checkpoint duration | 482 ms |
| Latest completed checkpoint duration | 311 ms |

This result is a **reliability/regression baseline**, not a capacity limit. The runner is ephemeral, the workload is small, and only one requested QPS level is exercised. It is valid evidence that the real Producer → Kafka → Flink path can process and drain the smoke workload without restart while checkpointing; it is not evidence that 100 QPS is the system maximum or a production SLA.

The E2E workflow also found two cluster-only defects that unit tests had not exposed: a Jackson binary-version conflict and an implicit Map serialization type boundary that allowed `RealtimeMetric` to hit a `RiskAlert` cast. Both were fixed in the runtime dependency/type boundaries rather than hidden by relaxing benchmark gates.

## How to produce resume-grade numbers

Use a fixed machine and commit, then run a stepped load such as 100 → 250 → 500 → 1000 QPS. Keep each stage long enough for multiple checkpoints and record the first stage where any of these deteriorate materially:

- consumer lag no longer returns to zero;
- backpressured time remains elevated;
- checkpoint duration grows sharply or checkpoints fail;
- restart count changes;
- achieved producer QPS falls below requested QPS.

Only then state a tested operating range. Record machine CPU/RAM, Kafka partitions, Flink parallelism, checkpoint interval, event count, requested QPS and the benchmark JSON together with the result.

Do not combine Flink detection-plane latency with LLM investigation latency: the model is deliberately outside the hard real-time payment-risk path.
