from scripts.benchmark_streaming import Sample, parse_consumer_group_lag, parse_metric_rows, summarize_samples


def test_parse_consumer_group_lag_sums_topic_partitions():
    output = '''
GROUP TOPIC PARTITION CURRENT-OFFSET LOG-END-OFFSET LAG CONSUMER-ID HOST CLIENT-ID
finguard-risk-monitor payment_transaction_events 0 100 112 12 - - -
finguard-risk-monitor payment_transaction_events 1 50 53 3 - - -
finguard-risk-monitor other_topic 0 1 99 98 - - -
'''
    assert parse_consumer_group_lag(output, "payment_transaction_events") == 15
    assert parse_consumer_group_lag(output, "missing") is None


def test_parse_metric_rows_handles_aggregates_and_values():
    rows = [
        {"id": "numRecordsOut", "max": "20", "sum": "35"},
        {"id": "numRestarts", "value": "2"},
    ]
    parsed = parse_metric_rows(rows)
    assert parsed["numRecordsOut"] == {"max": 20.0, "sum": 35.0}
    assert parsed["numRestarts"]["value"] == 2.0


def test_summarize_samples_separates_lag_capacity_and_processed_ratio():
    baseline = Sample(0, 0, 100, 0, 10, 20, 1)
    samples = [
        Sample(1, 40, 220, 120, 700, 25, 1),
        Sample(2, 0, 395, 80, 500, 30, 1),
    ]
    result = summarize_samples(samples, baseline, events=300)
    assert result["source_records_out_delta"] == 295.0
    assert result["processed_ratio"] == 0.9833
    assert result["max_consumer_lag"] == 40
    assert result["final_consumer_lag"] == 0
    assert result["max_backpressure_ms_per_second"] == 120
    assert result["max_busy_ms_per_second"] == 700
    assert result["max_checkpoint_duration_ms"] == 30
    assert result["restart_delta"] == 0
