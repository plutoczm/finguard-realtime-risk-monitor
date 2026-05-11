import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "producer"))

from enterprise_dataset import map_aml_row_to_transaction


def test_aml_row_maps_to_finguard_transaction_schema():
    row = {
        "record_key": "sample-record",
        "timestamp": "2022-09-01T00:08:00Z",
        "from_bank": "Savings Bank of Madison",
        "from_account": "8000ECA90",
        "from_country": "US",
        "to_bank": "Savings Bank of Madison",
        "to_account": "8000ECA90",
        "to_country": "US",
        "amount_received": "3195403.0",
        "receiving_currency": "USD",
        "amount_paid": "3195403.0",
        "payment_currency": "USD",
        "payment_format": "Reinvestment",
        "is_laundering": "True",
        "predicted_alert": "True",
        "model_score": "0.991",
        "is_dashboard_sample": "False",
    }

    event = map_aml_row_to_transaction(row)

    assert event["event_id"].startswith("evt-aml-")
    assert event["transaction_id"].startswith("txn-aml-")
    assert event["amount"] == 3195403.0
    assert event["currency"] == "USD"
    assert event["transaction_type"] == "TRANSFER"
    assert event["risk_label"] == "AML_LAUNDERING"
    assert event["is_black_device"] is True
    assert event["is_black_card"] is True
