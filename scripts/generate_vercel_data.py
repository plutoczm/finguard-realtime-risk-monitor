"""Generate sample dashboard data for FinGuard Vercel deployment.

Creates dashboard/static/api/dashboard.json with realistic risk monitoring metrics
that the frontend dashboard expects via /api/dashboard.
"""
import json
import math
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

random.seed(2025)

CHANNELS = ["APP", "H5", "API", "POS", "MINI_PROGRAM"]
RISK_LABELS = ["NORMAL", "NORMAL", "NORMAL", "NORMAL", "NORMAL",
               "HIGH_MODEL_SCORE", "AML_LAUNDERING", "LARGE_AMOUNT",
               "BLACK_DEVICE", "MODEL_ALERT"]
RULE_IDS = ["R001", "R002", "R003", "R004", "R005", "R006", "R007", "R008"]
RISK_LEVELS = ["HIGH", "HIGH", "MEDIUM", "MEDIUM", "MEDIUM", "LOW", "LOW", "LOW", "LOW", "CRITICAL"]
MERCHANT_IDS = [f"merchant-{i:03d}" for i in range(1, 31)]
CITIES = ["Shanghai", "Beijing", "San Francisco", "London", "Singapore",
          "Tokyo", "Frankfurt", "Paris", "Sydney", "Toronto",
          "AE", "NL", "HK", "CH", "GB"]
USER_IDS = [f"user-{i:04d}" for i in range(1, 200)]
DEVICE_IDS = [f"device-{i:03d}" for i in range(1, 80)]


def generate_events(count: int = 8000) -> list[dict]:
    """Generate sample transaction events."""
    events = []
    base_time = datetime(2025, 6, 1, 0, 0, 0, tzinfo=timezone.utc)
    for i in range(count):
        offset = timedelta(seconds=random.randint(0, 86400 * 7))
        event_time = base_time + offset
        amount = round(random.expovariate(1 / 500) * 500 + 10, 2)
        amount = min(amount, 50000)
        risk_label = random.choice(RISK_LABELS)
        is_black_device = risk_label == "BLACK_DEVICE"
        is_black_card = random.random() < 0.02
        status = "FAILED" if random.random() < 0.06 else "SUCCESS"

        events.append({
            "event_id": f"evt-{i:06d}",
            "transaction_id": f"txn-{i:06d}",
            "user_id": random.choice(USER_IDS),
            "merchant_id": random.choice(MERCHANT_IDS),
            "device_id": random.choice(DEVICE_IDS),
            "city": random.choice(CITIES),
            "amount": amount,
            "currency": "CNY",
            "payment_method": random.choice(["BANK_CARD", "BALANCE", "QR_CODE"]),
            "transaction_type": random.choice(["PAY", "PAY", "PAY", "REFUND"]),
            "transaction_status": status,
            "event_time": event_time.isoformat().replace("+00:00", "Z"),
            "channel": random.choice(CHANNELS),
            "is_black_device": is_black_device,
            "is_black_card": is_black_card,
            "risk_label": risk_label,
        })
    return events


def generate_alerts(events: list[dict], count: int = 120) -> list[dict]:
    """Generate realistic risk alerts based on event data."""
    alerts = []
    for i in range(count):
        event = random.choice(events)
        rule_id = random.choice(RULE_IDS)
        risk_level = random.choice(RISK_LEVELS)
        rule_names = {
            "R001": "高频交易检测", "R002": "大额交易检测",
            "R003": "设备多账户关联", "R004": "银行卡多账户关联",
            "R005": "连续支付失败", "R006": "黑名单设备交易",
            "R007": "金额突增检测", "R008": "商户收款突增",
        }
        alerts.append({
            "alert_id": f"alert-{i:06d}",
            "rule_id": rule_id,
            "rule_name": rule_names.get(rule_id, rule_id),
            "risk_level": risk_level,
            "reason": f"触发风控规则 {rule_id}",
            "user_id": event["user_id"],
            "device_id": event["device_id"],
            "amount": event["amount"],
            "event_time": event["event_time"],
            "evidence": {
                "device_id": event["device_id"],
                "is_black_device": str(event["is_black_device"]).lower(),
                "amount": event["amount"],
            },
        })
    return alerts


def amount_risk_score(amount: float, is_black_device: bool = False,
                      is_black_card: bool = False, risk_label: str = "NORMAL",
                      status: str = "SUCCESS") -> float:
    score = min(99.0, 18.0 + math.log10(max(float(amount), 1.0)) * 10.0)
    if is_black_device:
        score += 18.0
    if is_black_card:
        score += 10.0
    if str(risk_label).upper() != "NORMAL":
        score += 12.0
    if str(status).upper() == "FAILED":
        score += 7.0
    return round(min(score, 100.0), 2)


def build_time_series(events: list[dict], buckets: int = 36) -> list[dict]:
    sorted_events = sorted(events, key=lambda e: e["event_time"])
    chunk = max(1, len(sorted_events) // buckets)
    rows = []
    for idx in range(0, len(sorted_events), chunk):
        part = sorted_events[idx:idx + chunk]
        if not part:
            continue
        ts = part[-1]["event_time"][11:16] if "T" in part[-1]["event_time"] else part[-1]["event_time"][:5]
        amount = sum(e["amount"] for e in part)
        failed = sum(1 for e in part if e["transaction_status"] == "FAILED")
        risk = sum(amount_risk_score(e["amount"], e["is_black_device"],
                   e["is_black_card"], e["risk_label"], e["transaction_status"])
                   for e in part) / len(part)
        rows.append({
            "time": ts,
            "count": len(part),
            "amount": round(amount, 2),
            "failed": failed,
            "risk": round(risk, 2),
        })
    return rows[:buckets]


def build_scatter(events: list[dict], limit: int = 800) -> list:
    points = []
    step = max(1, len(events) // limit)
    for evt in events[::step][:limit]:
        hour = (datetime.fromisoformat(evt["event_time"].replace("Z", "+00:00")).hour
                if "T" in evt["event_time"] else 12)
        amount = float(evt["amount"])
        risk = amount_risk_score(amount, evt["is_black_device"],
                                 evt["is_black_card"], evt["risk_label"],
                                 evt["transaction_status"])
        points.append([
            hour,
            round(math.log10(max(amount, 1.0)), 4),
            risk,
            evt["channel"],
            evt["risk_label"],
            evt["transaction_id"],
        ])
    return points


def build_heatmap(events: list[dict]) -> dict:
    channels = sorted(set(e["channel"] for e in events))
    labels = sorted(set(e["risk_label"] for e in events))
    c_idx = {v: i for i, v in enumerate(channels)}
    l_idx = {v: j for j, v in enumerate(labels)}
    matrix: dict = {}
    for e in events:
        x, y = c_idx[e["channel"]], l_idx[e["risk_label"]]
        matrix[(x, y)] = matrix.get((x, y), 0) + 1
    return {
        "channels": channels,
        "labels": labels,
        "data": [[x, y, v] for (x, y), v in matrix.items()],
    }


def build_flow_links(events: list[dict], limit: int = 12) -> list[dict]:
    merchant_amounts: dict[str, float] = {}
    city_amounts: dict[str, float] = {}
    for e in events:
        m = e["merchant_id"]
        c = e["city"]
        merchant_amounts[m] = merchant_amounts.get(m, 0) + e["amount"]
        city_amounts[c] = city_amounts.get(c, 0) + e["amount"]
    top_merchants = sorted(merchant_amounts.items(), key=lambda x: x[1], reverse=True)[:limit]
    top_cities = sorted(city_amounts.items(), key=lambda x: x[1], reverse=True)
    city_names = [c[0] for c in top_cities] or ["Global"]
    links = []
    for i, (m, amt) in enumerate(top_merchants):
        links.append({
            "source": city_names[i % len(city_names)],
            "target": m,
            "value": round(amt, 2),
        })
    return links


def main() -> None:
    events = generate_events(8000)
    alerts = generate_alerts(events, 120)
    series = build_time_series(events)
    scatter = build_scatter(events)
    heatmap = build_heatmap(events)
    flow = build_flow_links(events)

    # Aggregate stats
    risk_levels = {}
    for a in alerts:
        rl = a["risk_level"]
        risk_levels[rl] = risk_levels.get(rl, 0) + 1

    rules = {}
    for a in alerts:
        rid = a["rule_id"]
        rules[rid] = rules.get(rid, 0) + 1

    city_amount = {}
    merchant_amount = {}
    channels = {}
    for e in events:
        city_amount[e["city"]] = city_amount.get(e["city"], 0) + e["amount"]
        merchant_amount[e["merchant_id"]] = merchant_amount.get(e["merchant_id"], 0) + e["amount"]
        channels[e["channel"]] = channels.get(e["channel"], 0) + 1

    total_amount = sum(e["amount"] for e in events)
    high_alerts = sum(1 for a in alerts if a["risk_level"] == "HIGH")
    avg_risk = sum(amount_risk_score(e["amount"], e["is_black_device"],
                   e["is_black_card"], e["risk_label"], e["transaction_status"])
                   for e in events) / max(len(events), 1)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "overview": {
            "event_sample_count": len(events),
            "alert_count": len(alerts),
            "high_alert_count": high_alerts,
            "late_file_count": 15,
            "sample_amount": round(total_amount, 2),
            "avg_risk_score": round(avg_risk, 2),
            "enterprise_converted_rows": 6942000,
            "enterprise_source_size_bytes": 1554800640,
            "max_amount": max(e["amount"] for e in events),
        },
        "time_series": series,
        "risk_levels": [{"name": k, "value": v} for k, v in risk_levels.items()],
        "rules": [{"name": k, "value": v} for k, v in
                  sorted(rules.items(), key=lambda x: x[1], reverse=True)],
        "city_amount": [{"name": k, "value": round(v, 2)} for k, v in
                        sorted(city_amount.items(), key=lambda x: x[1], reverse=True)[:10]],
        "merchant_amount": [{"name": k, "value": round(v, 2)} for k, v in
                            sorted(merchant_amount.items(), key=lambda x: x[1], reverse=True)[:10]],
        "channels": [{"name": k, "value": v} for k, v in channels.items()],
        "scatter": scatter,
        "heatmap": heatmap,
        "flow_links": flow,
        "alerts": alerts[-30:][::-1],
        "metrics": [
            {"metric_name": "transaction_count_1m", "value": random.randint(800, 1600)},
            {"metric_name": "transaction_amount_5m", "value": round(random.uniform(200000, 500000), 2)},
            {"metric_name": "channel_success_rate_5m", "dimensions": {"channel": "APP"}, "value": round(random.uniform(0.88, 0.97), 3), "count": random.randint(400, 600)},
            {"metric_name": "risk_alert_count_1m", "value": random.randint(10, 30)},
            {"metric_name": "high_risk_alert_count_1m", "value": random.randint(3, 12)},
        ],
        "insights": [
            f"当前样本综合风险脉冲为 {avg_risk:.0f}/100，建议优先核查三维星图中高金额、高风险聚集区。",
            f"当前存在 {high_alerts} 条高风险告警，应优先处理黑名单设备、多账户关联和银行卡共用风险。",
            f"交易金额峰值出现在 {series[-1]['time'] if series else '--:--'} 附近，可联动商户收款突增规则复核。",
            f"当前主通道为 {max(channels, key=channels.get)}，样本量 {channels[max(channels, key=channels.get)]} 笔，建议同步观察渠道成功率。",
            "若压测时出现消息积压，建议同时提升 Kafka 分区数、Flink 并行度和文件 Sink 滚动粒度。",
        ],
    }

    output_dir = Path(__file__).resolve().parents[1] / "dashboard" / "static" / "api"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "dashboard.json"
    output_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print(f"Generated {output_path} ({output_path.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
