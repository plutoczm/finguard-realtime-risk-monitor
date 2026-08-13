from scripts.benchmark_ai import RequestResult, latency_summary, percentile, summarize


def test_percentile_and_latency_summary_are_deterministic():
    values = [10.0, 20.0, 30.0, 40.0, 50.0]
    assert percentile(values, 0.50) == 30.0
    assert percentile(values, 0.95) == 48.0
    summary = latency_summary(values)
    assert summary["avg"] == 30.0
    assert summary["p99"] == 49.6
    assert summary["max"] == 50.0


def test_summary_separates_source_and_degradation_reasons():
    results = [
        RequestResult(True, 200, 20.0, 5.0, "fallback", "missing_credentials"),
        RequestResult(True, 200, 30.0, 6.0, "fallback", "bulkhead_saturated"),
        RequestResult(False, 503, 10.0, error="HTTPError:503"),
    ]
    report = summarize(results, elapsed_seconds=1.0, requests=3, concurrency=2, warmup=0, base_url="http://127.0.0.1:8091")
    result = report["result"]
    assert result["success_count"] == 2
    assert result["success_rate"] == 0.6667
    assert result["source_counts"] == {"fallback": 2}
    assert result["degradation_counts"] == {"bulkhead_saturated": 1, "missing_credentials": 1}
    assert result["status_counts"] == {"200": 2, "503": 1}
