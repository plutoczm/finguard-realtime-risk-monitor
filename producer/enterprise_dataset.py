import argparse
import csv
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path


COUNTRY_TO_LOCATION = {
    "US": ("California", "San Francisco"),
    "CN": ("Shanghai", "Shanghai"),
    "SG": ("Singapore", "Singapore"),
    "UK": ("England", "London"),
    "DE": ("Hessen", "Frankfurt"),
    "FR": ("Ile-de-France", "Paris"),
    "JP": ("Tokyo", "Tokyo"),
    "KR": ("Seoul", "Seoul"),
    "AU": ("New South Wales", "Sydney"),
    "CA": ("Ontario", "Toronto"),
}


def stable_hash(value: str, length: int = 16) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def stable_int(value: str, modulo: int) -> int:
    return int(stable_hash(value, 8), 16) % modulo


def parse_bool(value: str) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def parse_float(value: str, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def iso_timestamp(value: str) -> str:
    if not value:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    normalized = value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def payment_method(payment_format: str) -> str:
    upper = (payment_format or "").upper()
    if "CARD" in upper or "CREDIT" in upper:
        return "CREDIT_CARD"
    if "CHECK" in upper or "CHEQUE" in upper:
        return "BANK_CARD"
    if "CASH" in upper:
        return "BALANCE"
    return "BANK_CARD"


def transaction_type(payment_format: str) -> str:
    upper = (payment_format or "").upper()
    if "REINVEST" in upper:
        return "TRANSFER"
    if "WITHDRAW" in upper:
        return "WITHDRAW"
    return "PAY"


def country_location(country: str) -> tuple[str, str]:
    return COUNTRY_TO_LOCATION.get((country or "").upper(), ("Global", country or "Unknown"))


def map_aml_row_to_transaction(row: dict) -> dict:
    record_key = row.get("record_key") or "|".join(row.values())
    score = parse_float(row.get("model_score"))
    laundering = parse_bool(row.get("is_laundering"))
    predicted = parse_bool(row.get("predicted_alert"))
    amount = parse_float(row.get("amount_paid") or row.get("amount_received"))
    event_time = iso_timestamp(row.get("timestamp", ""))
    process_time = (
        datetime.fromisoformat(event_time.replace("Z", "+00:00")) + timedelta(seconds=stable_int(record_key, 3600))
    ).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    from_account = row.get("from_account", "unknown_from")
    to_account = row.get("to_account", "unknown_to")
    from_country = row.get("from_country", "US")
    province, city = country_location(from_country)
    event_hash = stable_hash(record_key, 24)
    failure_bucket = stable_int(record_key, 1000)

    if laundering:
        risk_label = "AML_LAUNDERING"
    elif predicted:
        risk_label = "MODEL_ALERT"
    elif score >= 0.85:
        risk_label = "HIGH_MODEL_SCORE"
    else:
        risk_label = "NORMAL"

    return {
        "event_id": f"evt-aml-{event_hash}",
        "transaction_id": f"txn-aml-{event_hash}",
        "user_id": f"user-{stable_hash(from_account, 10)}",
        "account_id": f"acct-{from_account}",
        "card_id": f"card-{stable_hash(from_account + row.get('from_bank', ''), 12)}",
        "merchant_id": f"merchant-{stable_hash(row.get('to_bank', '') + to_account, 12)}",
        "device_id": f"device-{stable_hash(from_account + from_country, 12)}",
        "ip": f"10.{stable_int(from_account, 240) + 1}.{stable_int(to_account, 240) + 1}.{stable_int(record_key, 240) + 1}",
        "province": province,
        "city": city,
        "amount": round(amount, 2),
        "currency": (row.get("payment_currency") or row.get("receiving_currency") or "USD").replace("US Dollar", "USD"),
        "payment_method": payment_method(row.get("payment_format", "")),
        "transaction_type": transaction_type(row.get("payment_format", "")),
        "transaction_status": "FAILED" if failure_bucket < 4 else "SUCCESS",
        "event_time": event_time,
        "process_time": process_time,
        "channel": ["APP", "H5", "API", "POS", "MINI_PROGRAM"][stable_int(record_key, 5)],
        "app_version": f"{6 + stable_int(from_account, 2)}.{stable_int(to_account, 10)}.{stable_int(record_key, 10)}",
        "is_black_device": laundering or score >= 0.97,
        "is_black_card": laundering and amount >= 50000,
        "risk_label": risk_label,
    }


def convert_csv_to_jsonl(input_path: Path, output_path: Path, limit: int, skip: int) -> dict:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    converted = 0
    skipped = 0
    laundering = 0
    total_amount = 0.0
    max_amount = 0.0

    with input_path.open("r", encoding="utf-8", newline="") as source, output_path.open("w", encoding="utf-8") as sink:
        reader = csv.DictReader(source)
        for row in reader:
            if skipped < skip:
                skipped += 1
                continue
            if limit > 0 and converted >= limit:
                break

            event = map_aml_row_to_transaction(row)
            converted += 1
            total_amount += event["amount"]
            max_amount = max(max_amount, event["amount"])
            if event["risk_label"] == "AML_LAUNDERING":
                laundering += 1
            sink.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")

    metadata = {
        "source": str(input_path),
        "output": str(output_path),
        "source_size_bytes": input_path.stat().st_size if input_path.exists() else 0,
        "converted_rows": converted,
        "skipped_rows": skipped,
        "laundering_rows": laundering,
        "total_amount": round(total_amount, 2),
        "max_amount": round(max_amount, 2),
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    metadata_path = output_path.with_suffix(output_path.suffix + ".metadata.json")
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return metadata


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert IBM AML CSV into FinGuard transaction JSON Lines.")
    parser.add_argument("--input", default="enterprise_data/raw/amlworld_transactions_prepared.csv")
    parser.add_argument("--output", default="enterprise_data/processed/finguard_enterprise_transactions.jsonl")
    parser.add_argument("--limit", type=int, default=200000, help="0 means convert the whole file.")
    parser.add_argument("--skip", type=int, default=0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    metadata = convert_csv_to_jsonl(
        input_path=Path(args.input),
        output_path=Path(args.output),
        limit=args.limit,
        skip=args.skip,
    )
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
