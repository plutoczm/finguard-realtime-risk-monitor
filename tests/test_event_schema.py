import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "producer"))

from generate_transactions import generate_transactions, generate_user_event


def load_schema() -> dict:
    return json.loads((ROOT / "producer" / "event_schema.json").read_text(encoding="utf-8"))


def test_generated_transaction_events_match_schema():
    schema = load_schema()
    validator = Draft202012Validator(schema)
    events = generate_transactions(count=50, mode="mixed", abnormal_rate=0.3, seed=7)

    for event in events:
        errors = sorted(validator.iter_errors(event), key=lambda item: item.path)
        assert errors == []


def test_generated_user_event_matches_schema():
    schema = load_schema()
    validator = Draft202012Validator(schema)
    event = generate_user_event()
    errors = sorted(validator.iter_errors(event), key=lambda item: item.path)
    assert errors == []
