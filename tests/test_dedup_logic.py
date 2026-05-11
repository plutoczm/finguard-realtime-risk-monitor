import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "producer"))

from generate_transactions import base_transaction, with_late_time


def deduplicate(events):
    seen = set()
    output = []
    for event in events:
        if event["event_id"] in seen:
            continue
        seen.add(event["event_id"])
        output.append(event)
    return output


def is_late_event(event, watermark):
    event_time = datetime.fromisoformat(event["event_time"].replace("Z", "+00:00"))
    return event_time < watermark


def test_event_id_deduplication():
    event = base_transaction()
    duplicate = dict(event)
    duplicate["process_time"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    assert len(deduplicate([event, duplicate])) == 1


def test_late_event_detection():
    event = with_late_time(base_transaction(), minutes=30)
    watermark = datetime.now(timezone.utc) - timedelta(minutes=5)

    assert is_late_event(event, watermark)
