from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass
class RequestResult:
    ok: bool
    status: int
    client_latency_ms: float
    server_latency_ms: float | None = None
    source: str | None = None
    degradation_reason: str | None = None
    error: str | None = None


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return round(ordered[0], 3)
    rank = (len(ordered) - 1) * pct
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return round(ordered[low], 3)
    weight = rank - low
    return round(ordered[low] * (1 - weight) + ordered[high] * weight, 3)


def latency_summary(values: list[float]) -> dict[str, float]:
    if not values:
        return {"avg": 0.0, "p50": 0.0, "p95": 0.0, "p99": 0.0, "max": 0.0}
    return {
        "avg": round(statistics.fmean(values), 3),
        "p50": percentile(values, 0.50),
        "p95": percentile(values, 0.95),
        "p99": percentile(values, 0.99),
        "max": round(max(values), 3),
    }


def make_payload(index: int) -> dict[str, Any]:
    return {
        "alert": {
            "alert_id": f"benchmark-alert-{index}",
            "rule_id": "R006" if index % 3 == 0 else "R002",
            "risk_level": "HIGH",
            "reason": "benchmark risk signal",
            "evidence": {"is_black_device": index % 3 == 0, "window_count": 12 + (index % 5)},
        },
        "transaction": {
            "amount": 1000 + index,
            "currency": "CNY",
            "channel": "APP",
            "user_id": f"benchmark-user-{index}",
            "device_id": f"benchmark-device-{index}",
        },
        "language": "en",
    }


def send_request(base_url: str, index: int, timeout_seconds: float) -> RequestResult:
    body = json.dumps(make_payload(index)).encode("utf-8")
    request = Request(
        f"{base_url.rstrip('/')}/v1/explanations",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
            elapsed = (time.perf_counter() - started) * 1000
            explanation = payload.get("explanation") or {}
            return RequestResult(
                ok=200 <= response.status < 300,
                status=response.status,
                client_latency_ms=round(elapsed, 3),
                server_latency_ms=float(payload.get("latency_ms", 0.0)),
                source=explanation.get("source"),
                degradation_reason=explanation.get("degradation_reason"),
            )
    except HTTPError as exc:
        elapsed = (time.perf_counter() - started) * 1000
        return RequestResult(False, exc.code, round(elapsed, 3), error=f"HTTPError:{exc.code}")
    except (URLError, TimeoutError, OSError) as exc:
        elapsed = (time.perf_counter() - started) * 1000
        return RequestResult(False, 0, round(elapsed, 3), error=exc.__class__.__name__)


def summarize(results: list[RequestResult], *, elapsed_seconds: float, requests: int, concurrency: int, warmup: int, base_url: str) -> dict[str, Any]:
    successes = [item for item in results if item.ok]
    source_counts = Counter(item.source or "unknown" for item in successes)
    degradation_counts = Counter(item.degradation_reason or "none" for item in successes)
    status_counts = Counter(str(item.status) for item in results)
    error_counts = Counter(item.error or "none" for item in results if not item.ok)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "benchmark": "ai_explanation_http",
        "config": {"base_url": base_url, "requests": requests, "concurrency": concurrency, "warmup": warmup},
        "result": {
            "success_count": len(successes),
            "error_count": len(results) - len(successes),
            "success_rate": round(len(successes) / len(results), 4) if results else 0.0,
            "elapsed_seconds": round(elapsed_seconds, 3),
            "throughput_rps": round(len(results) / elapsed_seconds, 3) if elapsed_seconds > 0 else 0.0,
            "client_latency_ms": latency_summary([item.client_latency_ms for item in successes]),
            "server_latency_ms": latency_summary([float(item.server_latency_ms) for item in successes if item.server_latency_ms is not None]),
            "source_counts": dict(sorted(source_counts.items())),
            "degradation_counts": dict(sorted(degradation_counts.items())),
            "status_counts": dict(sorted(status_counts.items())),
            "error_counts": dict(sorted(error_counts.items())),
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load-test FinGuard AI explanation API and emit a reproducible JSON report.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8091")
    parser.add_argument("--requests", type=int, default=50)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--warmup", type=int, default=3)
    parser.add_argument("--timeout-seconds", type=float, default=10.0)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--min-success-rate", type=float, default=0.0)
    parser.add_argument("--max-p95-ms", type=float)
    parser.add_argument("--expect-source", choices=["any", "llm", "fallback"], default="any")
    args = parser.parse_args()
    if args.requests < 1 or args.concurrency < 1 or args.warmup < 0:
        parser.error("requests/concurrency must be positive and warmup must be non-negative")
    if not 0.0 <= args.min_success_rate <= 1.0:
        parser.error("min-success-rate must be between 0 and 1")
    return args


def main() -> int:
    args = parse_args()
    for index in range(args.warmup):
        send_request(args.base_url, -index - 1, args.timeout_seconds)
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        futures = [executor.submit(send_request, args.base_url, index, args.timeout_seconds) for index in range(args.requests)]
        results = [future.result() for future in as_completed(futures)]
    report = summarize(results, elapsed_seconds=time.perf_counter() - started, requests=args.requests, concurrency=args.concurrency, warmup=args.warmup, base_url=args.base_url)
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    result = report["result"]
    failures: list[str] = []
    if result["success_rate"] < args.min_success_rate:
        failures.append(f"success_rate {result['success_rate']} < {args.min_success_rate}")
    if args.max_p95_ms is not None and result["client_latency_ms"]["p95"] > args.max_p95_ms:
        failures.append(f"client p95 {result['client_latency_ms']['p95']}ms > {args.max_p95_ms}ms")
    if args.expect_source != "any":
        unexpected = sum(count for source, count in result["source_counts"].items() if source != args.expect_source)
        if unexpected:
            failures.append(f"{unexpected} successful responses did not use source={args.expect_source}")
    if failures:
        print("benchmark gate failed: " + "; ".join(failures), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
