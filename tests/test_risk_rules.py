import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "producer"))

from generate_transactions import abnormal_transaction, base_transaction


def test_user_frequency_threshold_rule():
    start = datetime.now(timezone.utc)
    events = []
    for index in range(11):
        event = base_transaction(start + timedelta(seconds=index * 4))
        event["user_id"] = "user-threshold"
        events.append(event)

    one_minute_events = [
        event for event in events
        if datetime.fromisoformat(event["event_time"].replace("Z", "+00:00")) < start + timedelta(minutes=1)
    ]

    assert len(one_minute_events) == 11
    assert len(one_minute_events) > 10


def test_user_amount_threshold_rule():
    start = datetime.now(timezone.utc)
    events = []
    for index, amount in enumerate([3000, 4500, 5000, 6000, 2500]):
        event = base_transaction(start + timedelta(seconds=index * 30))
        event["user_id"] = "user-amount"
        event["amount"] = amount
        event["transaction_status"] = "SUCCESS"
        events.append(event)

    assert sum(event["amount"] for event in events) > 20000


def test_black_device_rule():
    event = abnormal_transaction("black_device", 7)
    assert event["is_black_device"] is True
    assert event["device_id"] == "device-black-001"


def test_consecutive_failure_rule():
    failures = []
    for index in range(5):
        event = abnormal_transaction("failed", 5)
        event["user_id"] = "user-failure"
        event["transaction_status"] = "FAILED"
        failures.append(event)

    assert all(event["transaction_status"] == "FAILED" for event in failures)
    assert len(failures) >= 5
