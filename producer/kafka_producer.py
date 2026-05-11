import argparse
import json
import time
from datetime import datetime, timezone

from generate_transactions import generate_transactions


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send FinGuard events to Kafka.")
    parser.add_argument("--bootstrap-server", default="localhost:9092")
    parser.add_argument("--topic", default="payment_transaction_events")
    parser.add_argument("--count", type=int, default=0, help="0 means generate until duration ends.")
    parser.add_argument("--qps", type=float, default=20)
    parser.add_argument("--duration", type=int, default=60)
    parser.add_argument("--mode", default="mixed")
    parser.add_argument("--abnormal-rate", type=float, default=0.15)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def load_kafka_producer():
    try:
        from kafka import KafkaProducer
    except ImportError as exc:
        raise SystemExit("Missing kafka-python. Run: pip install -r requirements.txt") from exc
    return KafkaProducer


def main() -> None:
    args = parse_args()
    interval = 1.0 / args.qps if args.qps > 0 else 0
    total = args.count if args.count > 0 else int(args.qps * args.duration)
    events = generate_transactions(total, mode=args.mode, abnormal_rate=args.abnormal_rate)

    producer = None
    if not args.dry_run:
        KafkaProducer = load_kafka_producer()
        producer = KafkaProducer(
            bootstrap_servers=args.bootstrap_server,
            key_serializer=lambda key: key.encode("utf-8"),
            value_serializer=lambda value: json.dumps(value, ensure_ascii=False).encode("utf-8"),
            linger_ms=20,
            retries=5,
        )

    started_at = time.time()
    sent = 0
    for event in events:
        if args.duration > 0 and time.time() - started_at > args.duration:
            break

        event["process_time"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        key = event.get("user_id") or event.get("device_id") or event["event_id"]

        if args.dry_run:
            print(json.dumps(event, ensure_ascii=False))
        else:
            producer.send(args.topic, key=key, value=event)

        sent += 1
        if interval > 0:
            time.sleep(interval)

    if producer is not None:
        producer.flush(timeout=30)
        producer.close()

    print(f"Sent {sent} events to topic={args.topic}, bootstrap={args.bootstrap_server}")


if __name__ == "__main__":
    main()
