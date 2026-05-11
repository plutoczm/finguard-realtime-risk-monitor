import argparse
import json
import random
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path


TRANSACTION_TYPES = ["PAY", "REFUND", "TRANSFER", "WITHDRAW"]
TRANSACTION_STATUSES = ["SUCCESS", "FAILED", "CANCELLED", "PENDING"]
PAYMENT_METHODS = ["BALANCE", "BANK_CARD", "CREDIT_CARD", "DEBIT_CARD", "WALLET"]
CHANNELS = ["APP", "H5", "MINI_PROGRAM", "POS", "API"]
LOCATIONS = [
    ("Shanghai", "Shanghai"),
    ("Beijing", "Beijing"),
    ("Guangdong", "Shenzhen"),
    ("Zhejiang", "Hangzhou"),
    ("Sichuan", "Chengdu"),
    ("Hubei", "Wuhan"),
    ("Jiangsu", "Nanjing"),
]


def iso(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def base_transaction(now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    user_no = random.randint(1, 500)
    device_no = random.randint(1, 700)
    card_no = random.randint(1, 900)
    merchant_no = random.randint(1, 80)
    province, city = random.choice(LOCATIONS)
    amount = round(random.uniform(8, 1200), 2)
    status = random.choices(TRANSACTION_STATUSES, weights=[86, 8, 3, 3], k=1)[0]

    return {
        "event_id": f"evt-{uuid.uuid4()}",
        "transaction_id": f"txn-{uuid.uuid4()}",
        "user_id": f"user-{user_no:05d}",
        "account_id": f"acct-{user_no:05d}",
        "card_id": f"card-{card_no:05d}",
        "merchant_id": f"merchant-{merchant_no:04d}",
        "device_id": f"device-{device_no:05d}",
        "ip": f"10.{random.randint(1, 200)}.{random.randint(1, 250)}.{random.randint(1, 250)}",
        "province": province,
        "city": city,
        "amount": amount,
        "currency": "CNY",
        "payment_method": random.choice(PAYMENT_METHODS),
        "transaction_type": random.choice(TRANSACTION_TYPES),
        "transaction_status": status,
        "event_time": iso(now),
        "process_time": iso(datetime.now(timezone.utc)),
        "channel": random.choice(CHANNELS),
        "app_version": f"{random.randint(5, 7)}.{random.randint(0, 9)}.{random.randint(0, 9)}",
        "is_black_device": False,
        "is_black_card": False,
        "risk_label": "NORMAL",
    }


def abnormal_transaction(mode: str, index: int, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    event = base_transaction(now)

    if mode in {"abnormal", "high_frequency"}:
        event["user_id"] = "user-risk-hf"
        event["account_id"] = "acct-risk-hf"
        event["risk_label"] = "HIGH_FREQUENCY"
        event["amount"] = round(random.uniform(20, 300), 2)

    if mode in {"abnormal", "large_amount"}:
        if index % 4 == 0:
            event["user_id"] = "user-risk-large"
            event["account_id"] = "acct-risk-large"
            event["amount"] = round(random.uniform(22000, 68000), 2)
            event["risk_label"] = "LARGE_AMOUNT"

    if mode in {"abnormal", "black_device"}:
        if index % 7 == 0:
            event["device_id"] = "device-black-001"
            event["is_black_device"] = True
            event["risk_label"] = "BLACK_DEVICE"

    if mode in {"abnormal", "failed"}:
        if index % 5 == 0:
            event["user_id"] = "user-risk-failed"
            event["account_id"] = "acct-risk-failed"
            event["transaction_status"] = "FAILED"
            event["risk_label"] = "CONSECUTIVE_FAILED"

    if mode in {"abnormal", "merchant_spike"}:
        if index % 3 == 0:
            event["merchant_id"] = "merchant-risk-spike"
            event["amount"] = round(random.uniform(6000, 18000), 2)
            event["transaction_status"] = "SUCCESS"
            event["risk_label"] = "MERCHANT_SPIKE"

    if mode in {"abnormal", "device_many_users"}:
        if index % 6 == 0:
            event["device_id"] = "device-risk-shared"
            event["user_id"] = f"user-risk-device-{index % 20:02d}"
            event["account_id"] = f"acct-risk-device-{index % 20:02d}"
            event["risk_label"] = "DEVICE_MANY_USERS"

    if mode in {"abnormal", "card_many_users"}:
        if index % 8 == 0:
            event["card_id"] = "card-risk-shared"
            event["user_id"] = f"user-risk-card-{index % 12:02d}"
            event["account_id"] = f"acct-risk-card-{index % 12:02d}"
            event["risk_label"] = "CARD_MANY_USERS"

    if mode == "remote":
        event["user_id"] = "user-risk-remote"
        event["account_id"] = "acct-risk-remote"
        event["province"], event["city"] = LOCATIONS[index % len(LOCATIONS)]
        event["risk_label"] = "REMOTE_LOCATION"

    return event


def with_late_time(event: dict, minutes: int = 20) -> dict:
    event = dict(event)
    old_time = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    event["event_time"] = iso(old_time)
    event["risk_label"] = "LATE_EVENT"
    return event


def with_out_of_order_time(event: dict, seconds: int) -> dict:
    event = dict(event)
    shifted_time = datetime.now(timezone.utc) - timedelta(seconds=seconds)
    event["event_time"] = iso(shifted_time)
    event["risk_label"] = "OUT_OF_ORDER"
    return event


def generate_transactions(
    count: int,
    mode: str = "mixed",
    abnormal_rate: float = 0.1,
    seed: int | None = None,
) -> list[dict]:
    if seed is not None:
        random.seed(seed)

    events: list[dict] = []
    base_time = datetime.now(timezone.utc)
    duplicate_candidates: list[dict] = []

    for index in range(count):
        now = base_time + timedelta(milliseconds=index * 100)
        use_abnormal = mode != "normal" and random.random() < abnormal_rate

        if mode == "late":
            event = with_late_time(base_transaction(now), minutes=random.randint(15, 60))
        elif mode == "duplicate" and duplicate_candidates and index % 5 == 0:
            event = dict(random.choice(duplicate_candidates))
            event["process_time"] = iso(datetime.now(timezone.utc))
            event["risk_label"] = "DUPLICATE_EVENT"
        elif mode == "out_of_order":
            event = with_out_of_order_time(base_transaction(now), seconds=random.randint(30, 240))
        elif use_abnormal:
            event = abnormal_transaction("abnormal", index, now)
        else:
            event = base_transaction(now)

        if mode == "peak":
            event["risk_label"] = "PEAK_TRAFFIC"

        events.append(event)
        if index % 11 == 0:
            duplicate_candidates.append(event)

    if mode == "mixed" and count >= 20:
        events.extend(build_rule_trigger_events(base_time + timedelta(seconds=2)))

    return events[:count] if len(events) > count else events


def build_rule_trigger_events(start: datetime) -> list[dict]:
    events: list[dict] = []

    for i in range(12):
        event = abnormal_transaction("high_frequency", i, start + timedelta(seconds=i * 3))
        event["user_id"] = "user-demo-hf"
        event["account_id"] = "acct-demo-hf"
        events.append(event)

    for i in range(6):
        event = abnormal_transaction("failed", i, start + timedelta(seconds=90 + i * 5))
        event["user_id"] = "user-demo-failed"
        event["account_id"] = "acct-demo-failed"
        event["transaction_status"] = "FAILED"
        events.append(event)

    for i in range(7):
        event = abnormal_transaction("device_many_users", i, start + timedelta(seconds=180 + i * 15))
        event["device_id"] = "device-demo-shared"
        event["user_id"] = f"user-demo-device-{i:02d}"
        event["account_id"] = f"acct-demo-device-{i:02d}"
        events.append(event)

    for i in range(5):
        event = abnormal_transaction("card_many_users", i, start + timedelta(seconds=300 + i * 20))
        event["card_id"] = "card-demo-shared"
        event["user_id"] = f"user-demo-card-{i:02d}"
        event["account_id"] = f"acct-demo-card-{i:02d}"
        events.append(event)

    for i in range(5):
        event = abnormal_transaction("large_amount", i, start + timedelta(seconds=420 + i * 10))
        event["user_id"] = "user-demo-large"
        event["account_id"] = "acct-demo-large"
        event["amount"] = 5000 + i * 4500
        event["transaction_status"] = "SUCCESS"
        events.append(event)

    return events


def generate_user_event(index: int = 0) -> dict:
    province, city = random.choice(LOCATIONS)
    return {
        "event_id": f"uevt-{uuid.uuid4()}",
        "user_id": f"user-{random.randint(1, 500):05d}",
        "device_id": f"device-{random.randint(1, 700):05d}",
        "ip": f"172.16.{random.randint(1, 250)}.{random.randint(1, 250)}",
        "event_type": random.choice(["LOGIN", "LOGOUT", "BIND_CARD", "UNBIND_CARD", "CHANGE_DEVICE", "CHANGE_PASSWORD"]),
        "event_time": iso(datetime.now(timezone.utc) - timedelta(seconds=index)),
        "province": province,
        "city": city,
        "channel": random.choice(CHANNELS),
    }


def write_json_lines(events: list[dict], output: str) -> None:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for event in events:
            file.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate FinGuard payment transaction events.")
    parser.add_argument("--count", type=int, default=1000)
    parser.add_argument("--output", default="data/sample_events/transactions.json")
    parser.add_argument(
        "--mode",
        choices=[
            "normal",
            "mixed",
            "abnormal",
            "late",
            "duplicate",
            "out_of_order",
            "peak",
            "remote",
            "large_amount",
            "failed",
            "black_device",
            "merchant_spike",
        ],
        default="mixed",
    )
    parser.add_argument("--abnormal-rate", type=float, default=0.15)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    events = generate_transactions(
        count=args.count,
        mode=args.mode,
        abnormal_rate=args.abnormal_rate,
        seed=args.seed,
    )
    write_json_lines(events, args.output)
    print(f"Generated {len(events)} events -> {args.output}")


if __name__ == "__main__":
    main()
