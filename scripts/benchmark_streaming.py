from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_JOB_NAME = "FinGuard Realtime Risk Monitor"
TASK_METRICS = ("backPressuredTimeMsPerSecond", "busyTimeMsPerSecond", "idleTimeMsPerSecond")
JOB_METRICS = ("lastCheckpointDuration", "numRestarts")


@dataclass
class Sample:
    timestamp: float
    lag: int | None
    source_records_out: float | None
    max_backpressure_ms_per_second: float | None
    max_busy_ms_per_second: float | None
    last_checkpoint_duration_ms: float | None
    num_restarts: float | None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def http_json(url: str, timeout: float = 5.0) -> Any:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.load(response)


def finite_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def parse_consumer_group_lag(output: str, topic: str) -> int | None:
    total = 0
    matched = False
    for raw_line in output.splitlines():
        parts = re.split(r"\s+", raw_line.strip())
        if not parts or parts[0] in {"GROUP", "Consumer"} or len(parts) < 6:
            continue
        if parts[1] != topic or parts[5] == "-":
            continue
        try:
            total += int(parts[5])
            matched = True
        except ValueError:
            continue
    return total if matched else None


def parse_metric_rows(rows: Any) -> dict[str, dict[str, float]]:
    parsed: dict[str, dict[str, float]] = {}
    if not isinstance(rows, list):
        return parsed
    for row in rows:
        if not isinstance(row, dict) or "id" not in row:
            continue
        values: dict[str, float] = {}
        for key in ("value", "min", "max", "sum", "avg"):
            value = finite_float(row.get(key))
            if value is not None:
                values[key] = value
        parsed[str(row["id"])] = values
    return parsed


def get_git_commit() -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True
        ).stdout.strip()
    except Exception:
        return None


def get_kafka_lag(compose: str, group: str, topic: str) -> int | None:
    result = subprocess.run(
        [
            *compose.split(), "exec", "-T", "kafka", "kafka-consumer-groups",
            "--bootstrap-server", "localhost:9092", "--describe", "--group", group,
        ],
        capture_output=True,
        text=True,
    )
    text = f"{result.stdout}\n{result.stderr}"
    if result.returncode != 0 and "does not exist" not in text.lower():
        raise RuntimeError(f"consumer-group command failed: {text.strip()}")
    return parse_consumer_group_lag(text, topic)


def wait_for_running_job(flink_url: str, job_name: str = DEFAULT_JOB_NAME, timeout_seconds: float = 90.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            jobs = http_json(f"{flink_url.rstrip('/')}/jobs/overview").get("jobs", [])
            running = [job for job in jobs if job.get("state") == "RUNNING" and job.get("name") == job_name]
            if running:
                return max(running, key=lambda item: item.get("start-time", 0))
        except Exception as exc:
            last_error = exc
        time.sleep(1.0)
    raise RuntimeError(f"running Flink job not found: {last_error}")


def job_vertices(flink_url: str, job_id: str) -> list[dict[str, Any]]:
    payload = http_json(f"{flink_url.rstrip('/')}/jobs/{job_id}")
    return [item for item in payload.get("vertices", []) if isinstance(item, dict) and item.get("id")]


def find_source_vertex(vertices: list[dict[str, Any]]) -> dict[str, Any]:
    for vertex in vertices:
        if "Kafka transaction source" in str(vertex.get("name", "")):
            return vertex
    raise RuntimeError("Kafka transaction source vertex not found")


def source_write_records(vertices: list[dict[str, Any]], source_vertex_id: str) -> float | None:
    for vertex in vertices:
        if str(vertex.get("id")) == source_vertex_id:
            return finite_float((vertex.get("metrics") or {}).get("write-records"))
    return None


def metric_rows(flink_url: str, job_id: str, vertex_id: str) -> dict[str, dict[str, float]]:
    query = urllib.parse.urlencode({"get": ",".join(TASK_METRICS), "agg": "max,sum"})
    return parse_metric_rows(http_json(f"{flink_url.rstrip('/')}/jobs/{job_id}/vertices/{vertex_id}/subtasks/metrics?{query}"))


def job_metric_values(flink_url: str, job_id: str) -> dict[str, float]:
    query = urllib.parse.urlencode({"get": ",".join(JOB_METRICS)})
    parsed = parse_metric_rows(http_json(f"{flink_url.rstrip('/')}/jobs/{job_id}/metrics?{query}"))
    return {name: values["value"] for name, values in parsed.items() if "value" in values}


def checkpoint_summary(flink_url: str, job_id: str) -> dict[str, Any]:
    payload = http_json(f"{flink_url.rstrip('/')}/jobs/{job_id}/checkpoints")
    counts = payload.get("counts", {})
    completed = (payload.get("latest") or {}).get("completed")
    return {
        "completed": int(counts.get("completed", 0) or 0),
        "failed": int(counts.get("failed", 0) or 0),
        "latest_end_to_end_duration_ms": completed.get("end_to_end_duration") if isinstance(completed, dict) else None,
    }


def take_sample(flink_url: str, job_id: str, vertices: list[dict[str, Any]], source_vertex_id: str, compose: str, group: str, topic: str) -> Sample:
    backpressure: list[float] = []
    busy: list[float] = []
    for vertex in vertices:
        metrics = metric_rows(flink_url, job_id, str(vertex["id"]))
        if "max" in metrics.get("backPressuredTimeMsPerSecond", {}):
            backpressure.append(metrics["backPressuredTimeMsPerSecond"]["max"])
        if "max" in metrics.get("busyTimeMsPerSecond", {}):
            busy.append(metrics["busyTimeMsPerSecond"]["max"])
    job_metrics = job_metric_values(flink_url, job_id)
    return Sample(
        time.time(),
        get_kafka_lag(compose, group, topic),
        source_write_records(job_vertices(flink_url, job_id), source_vertex_id),
        max(backpressure) if backpressure else None,
        max(busy) if busy else None,
        job_metrics.get("lastCheckpointDuration"),
        job_metrics.get("numRestarts"),
    )


def summarize_samples(samples: list[Sample], baseline: Sample, events: int) -> dict[str, Any]:
    final = samples[-1] if samples else baseline
    source_delta = None
    if baseline.source_records_out is not None and final.source_records_out is not None:
        source_delta = max(0.0, final.source_records_out - baseline.source_records_out)
    lags = [s.lag for s in samples if s.lag is not None]
    backpressure = [s.max_backpressure_ms_per_second for s in samples if s.max_backpressure_ms_per_second is not None]
    busy = [s.max_busy_ms_per_second for s in samples if s.max_busy_ms_per_second is not None]
    checkpoints = [s.last_checkpoint_duration_ms for s in samples if s.last_checkpoint_duration_ms is not None]
    restart_delta = None
    if baseline.num_restarts is not None and final.num_restarts is not None:
        restart_delta = max(0.0, final.num_restarts - baseline.num_restarts)
    return {
        "source_records_out_delta": round(source_delta, 3) if source_delta is not None else None,
        "processed_ratio": round(source_delta / events, 4) if source_delta is not None and events else None,
        "max_consumer_lag": max(lags) if lags else None,
        "final_consumer_lag": final.lag,
        "max_backpressure_ms_per_second": round(max(backpressure), 3) if backpressure else None,
        "max_busy_ms_per_second": round(max(busy), 3) if busy else None,
        "max_checkpoint_duration_ms": round(max(checkpoints), 3) if checkpoints else None,
        "restart_delta": int(restart_delta) if restart_delta is not None else None,
        "sample_count": len(samples),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark Producer -> Kafka -> Flink with live metrics.")
    parser.add_argument("--flink-url", default="http://127.0.0.1:8081")
    parser.add_argument("--bootstrap-server", default="localhost:9092")
    parser.add_argument("--compose", default="docker compose")
    parser.add_argument("--consumer-group", default="finguard-risk-monitor")
    parser.add_argument("--topic", default="payment_transaction_events")
    parser.add_argument("--events", type=int, default=1000)
    parser.add_argument("--qps", type=float, default=100.0)
    parser.add_argument("--sample-interval", type=float, default=1.0)
    parser.add_argument("--drain-timeout", type=float, default=60.0)
    parser.add_argument("--job-wait-timeout", type=float, default=90.0)
    parser.add_argument("--max-final-lag", type=int, default=0)
    parser.add_argument("--min-processed-ratio", type=float, default=0.95)
    parser.add_argument("--max-restarts", type=int, default=0)
    parser.add_argument("--min-completed-checkpoints", type=int, default=0)
    parser.add_argument("--max-backpressure-ms", type=float, default=None)
    parser.add_argument("--output", default="reports/benchmarks/streaming-latest.json")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.events <= 0 or args.qps <= 0:
        raise SystemExit("--events and --qps must be positive")
    job = wait_for_running_job(args.flink_url, timeout_seconds=args.job_wait_timeout)
    job_id = str(job["jid"])
    vertices = job_vertices(args.flink_url, job_id)
    source = find_source_vertex(vertices)
    baseline = take_sample(args.flink_url, job_id, vertices, str(source["id"]), args.compose, args.consumer_group, args.topic)
    command = [
        sys.executable, "producer/kafka_producer.py", "--bootstrap-server", args.bootstrap_server,
        "--topic", args.topic, "--count", str(args.events), "--qps", str(args.qps),
        "--duration", "0", "--mode", "mixed", "--abnormal-rate", "0.15",
    ]
    started = time.monotonic()
    producer = subprocess.Popen(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    samples: list[Sample] = []
    finished_at: float | None = None
    deadline: float | None = None
    while True:
        sample = take_sample(args.flink_url, job_id, vertices, str(source["id"]), args.compose, args.consumer_group, args.topic)
        samples.append(sample)
        if producer.poll() is not None and finished_at is None:
            finished_at = time.monotonic()
            deadline = finished_at + args.drain_timeout
        if finished_at is not None:
            processed = baseline.source_records_out is not None and sample.source_records_out is not None and sample.source_records_out - baseline.source_records_out >= args.events * args.min_processed_ratio
            drained = sample.lag is not None and sample.lag <= args.max_final_lag
            if processed and drained:
                break
            if deadline is not None and time.monotonic() >= deadline:
                break
        time.sleep(max(0.1, args.sample_interval))
    stdout, stderr = producer.communicate(timeout=10)
    if producer.returncode != 0:
        raise RuntimeError(f"producer failed: {(stderr or stdout).strip()}")
    finished_at = finished_at or time.monotonic()
    elapsed = finished_at - started
    result = summarize_samples(samples, baseline, args.events)
    checkpoints = checkpoint_summary(args.flink_url, job_id)
    cluster = http_json(f"{args.flink_url.rstrip('/')}/overview")
    report = {
        "benchmark": "streaming_plane",
        "generated_at": utc_now(),
        "config": {
            "events": args.events,
            "requested_qps": args.qps,
            "topic": args.topic,
            "consumer_group": args.consumer_group,
            "sample_interval_seconds": args.sample_interval,
            "drain_timeout_seconds": args.drain_timeout,
        },
        "environment": {
            "git_commit": get_git_commit(),
            "flink_version": cluster.get("flink-version") if isinstance(cluster, dict) else None,
            "job_id": job_id,
            "job_name": job.get("name"),
            "source_vertex": source.get("name"),
        },
        "result": {
            "producer_elapsed_seconds": round(elapsed, 3),
            "producer_achieved_qps": round(args.events / elapsed, 3),
            "drain_seconds": round(max(0.0, time.monotonic() - finished_at), 3),
            **result,
            "checkpoint_counts": checkpoints,
        },
        "producer_stdout": stdout.strip().splitlines()[-1] if stdout.strip() else "",
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)

    failures: list[str] = []
    if result["final_consumer_lag"] is None or result["final_consumer_lag"] > args.max_final_lag:
        failures.append(f"final lag {result['final_consumer_lag']} > {args.max_final_lag}")
    if result["processed_ratio"] is None or result["processed_ratio"] < args.min_processed_ratio:
        failures.append(f"processed ratio {result['processed_ratio']} < {args.min_processed_ratio}")
    if result["restart_delta"] is None or result["restart_delta"] > args.max_restarts:
        failures.append(f"restart delta {result['restart_delta']} > {args.max_restarts}")
    if checkpoints["completed"] < args.min_completed_checkpoints:
        failures.append(f"completed checkpoints {checkpoints['completed']} < {args.min_completed_checkpoints}")
    if args.max_backpressure_ms is not None:
        value = result["max_backpressure_ms_per_second"]
        if value is None or value > args.max_backpressure_ms:
            failures.append(f"max backpressure {value} > {args.max_backpressure_ms}ms/s")
    if failures:
        raise SystemExit("benchmark gate failed: " + "; ".join(failures))


if __name__ == "__main__":
    main()
