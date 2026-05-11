import argparse
import csv
import json
import time
from pathlib import Path

from enterprise_dataset import map_aml_row_to_transaction


def load_kafka_producer():
    try:
        from kafka import KafkaProducer
    except ImportError as exc:
        raise SystemExit("Missing kafka-python. Run: pip install -r requirements.txt") from exc
    return KafkaProducer


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stream enterprise AML CSV rows into Kafka as FinGuard events.")
    parser.add_argument("--input", default="enterprise_data/raw/amlworld_transactions_prepared.csv")
    parser.add_argument("--bootstrap-server", default="localhost:9092")
    parser.add_argument("--topic", default="payment_transaction_events")
    parser.add_argument("--qps", type=float, default=200)
    parser.add_argument("--limit", type=int, default=100000)
    parser.add_argument("--skip", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    interval = 1.0 / args.qps if args.qps > 0 else 0.0
    producer = None

    if not args.dry_run:
        KafkaProducer = load_kafka_producer()
        producer = KafkaProducer(
            bootstrap_servers=args.bootstrap_server,
            key_serializer=lambda key: key.encode("utf-8"),
            value_serializer=lambda value: json.dumps(value, ensure_ascii=False).encode("utf-8"),
            linger_ms=50,
            retries=5,
        )

    sent = 0
    skipped = 0
    with Path(args.input).open("r", encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        for row in reader:
            if skipped < args.skip:
                skipped += 1
                continue
            if args.limit > 0 and sent >= args.limit:
                break

            event = map_aml_row_to_transaction(row)
            if args.dry_run:
                print(json.dumps(event, ensure_ascii=False))
            else:
                producer.send(args.topic, key=event["user_id"], value=event)

            sent += 1
            if interval > 0:
                time.sleep(interval)

    if producer is not None:
        producer.flush(timeout=60)
        producer.close()

    print(f"Sent {sent} enterprise events to {args.topic}")


if __name__ == "__main__":
    main()
