"""Build the static Vercel dashboard payload from the same aggregation code as local mode."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dashboard.server import (  # noqa: E402
    amount_risk_score,
    build_flow_links,
    build_heatmap,
    build_insights,
    build_scatter,
    build_time_series,
    group_count,
    top_amount,
)
from producer.generate_transactions import generate_transactions  # noqa: E402

RULE_BY_LABEL = {
    "HIGH_FREQUENCY": ("R001", "高频交易检测", "MEDIUM"),
    "LARGE_AMOUNT": ("R002", "大额交易检测", "HIGH"),
    "DEVICE_MANY_USERS": ("R003", "设备多账户关联", "HIGH"),
    "CARD_MANY_USERS": ("R004", "银行卡多账户关联", "HIGH"),
    "CONSECUTIVE_FAILED": ("R005", "连续支付失败", "MEDIUM"),
    "BLACK_DEVICE": ("R006", "黑名单设备交易", "HIGH"),
    "MERCHANT_SPIKE": ("R008", "商户收款突增", "HIGH"),
}


def build_alerts(events: list[dict], limit: int = 120) -> list[dict]:
    alerts: list[dict] = []
    for event in events:
        mapped = RULE_BY_LABEL.get(str(event.get("risk_label") or ""))
        if not mapped:
            continue
        rule_id, rule_name, risk_level = mapped
        alerts.append(
            {
                "alert_id": f"demo-{len(alerts):05d}",
                "rule_id": rule_id,
                "rule_name": rule_name,
                "risk_level": risk_level,
                "reason": f"演示样本触发 {rule_name}",
                "user_id": event.get("user_id"),
                "device_id": event.get("device_id"),
                "merchant_id": event.get("merchant_id"),
                "card_id": event.get("card_id"),
                "amount": event.get("amount"),
                "event_time": event.get("event_time"),
                "evidence": {
                    "risk_label": event.get("risk_label"),
                    "amount": event.get("amount"),
                    "is_black_device": bool(event.get("is_black_device")),
                },
            }
        )
        if len(alerts) >= limit:
            break
    return alerts


def build_payload() -> dict:
    events = generate_transactions(4000, mode="mixed", abnormal_rate=0.22, seed=2025)
    alerts = build_alerts(events)
    series = build_time_series(events)
    metadata = {"converted_rows": 0, "laundering_rows": 0, "source_size_bytes": 0}
    total_amount = sum(float(event.get("amount") or 0) for event in events)
    high_alerts = sum(1 for alert in alerts if alert["risk_level"] == "HIGH")
    avg_risk = round(sum(amount_risk_score(event) for event in events) / max(len(events), 1), 2)

    metrics = [
        {"metric_name": "transaction_count_demo", "value": len(events), "count": len(events)},
        {"metric_name": "risk_alert_count_demo", "value": len(alerts), "count": len(alerts)},
        {"metric_name": "high_risk_alert_count_demo", "value": high_alerts, "count": high_alerts},
    ]

    return {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "demo_mode": True,
        "overview": {
            "event_sample_count": len(events),
            "alert_count": len(alerts),
            "high_alert_count": high_alerts,
            "late_file_count": 0,
            "sample_amount": round(total_amount, 2),
            "avg_risk_score": avg_risk,
            "enterprise_converted_rows": 0,
            "enterprise_source_size_bytes": 0,
            "max_amount": max(float(event.get("amount") or 0) for event in events),
        },
        "time_series": series,
        "risk_levels": [{"name": key, "value": value} for key, value in group_count(alerts, "risk_level").items()],
        "rules": [
            {"name": key, "value": value}
            for key, value in sorted(group_count(alerts, "rule_id").items(), key=lambda item: item[1], reverse=True)
        ],
        "city_amount": top_amount(events, "city"),
        "merchant_amount": top_amount(events, "merchant_id"),
        "channels": [{"name": key, "value": value} for key, value in group_count(events, "channel").items()],
        "scatter": build_scatter(events),
        "heatmap": build_heatmap(events),
        "flow_links": build_flow_links(events),
        "alerts": alerts[-30:][::-1],
        "metrics": metrics,
        "insights": build_insights(alerts, events, metadata, series),
    }


def main() -> None:
    output_dir = ROOT / "dashboard" / "static" / "api"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "dashboard.json"
    output_path.write_text(json.dumps(build_payload(), ensure_ascii=False), encoding="utf-8")
    print(f"Generated {output_path} ({output_path.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
