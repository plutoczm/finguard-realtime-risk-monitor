import argparse
import json
import math
import mimetypes
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = ROOT / "dashboard" / "static"


def read_json_lines(paths: list[Path], limit: int = 8000) -> list[dict]:
    records: list[dict] = []
    for path in paths:
        if not path.exists() or path.is_dir():
            continue
        try:
            with path.open("r", encoding="utf-8") as file:
                for line in file:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
                    if len(records) >= limit:
                        return records
        except OSError:
            continue
    return records


def files_under(directory: Path) -> list[Path]:
    if not directory.exists():
        return []
    return [
        path for path in directory.rglob("*")
        if path.is_file() and path.suffix.lower() not in {".md", ".crc", ".inprogress"}
    ]


def load_metadata() -> dict:
    metadata_path = ROOT / "enterprise_data" / "processed" / "finguard_enterprise_transactions.jsonl.metadata.json"
    raw_path = ROOT / "enterprise_data" / "raw" / "amlworld_transactions_prepared.csv"
    if metadata_path.exists():
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            if raw_path.exists() and not metadata.get("source_size_bytes"):
                metadata["source_size_bytes"] = raw_path.stat().st_size
            return metadata
        except json.JSONDecodeError:
            pass
    if raw_path.exists():
        return {
            "source": str(raw_path),
            "source_size_bytes": raw_path.stat().st_size,
            "converted_rows": 0,
            "laundering_rows": 0,
            "total_amount": 0,
            "max_amount": 0,
        }
    return {}


def load_alerts() -> list[dict]:
    alerts = read_json_lines(files_under(ROOT / "data" / "alerts" / "risk_alerts"), limit=3000)
    if alerts:
        return alerts

    sample_path = ROOT / "reports" / "risk_alert_sample.md"
    sample_alerts = []
    if sample_path.exists():
        for line in sample_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("{") and line.endswith("}"):
                try:
                    sample_alerts.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return sample_alerts


def load_metrics() -> list[dict]:
    metrics = read_json_lines(files_under(ROOT / "data" / "output" / "realtime_metrics"), limit=3000)
    if metrics:
        return metrics
    return [
        {"metric_name": "transaction_count_1m", "value": 1260, "count": 1260},
        {"metric_name": "transaction_amount_5m", "value": 386520.75, "count": 0},
        {"metric_name": "channel_success_rate_5m", "dimensions": {"channel": "APP"}, "value": 0.938, "count": 520},
        {"metric_name": "risk_alert_count_1m", "value": 18, "count": 18},
        {"metric_name": "high_risk_alert_count_1m", "value": 7, "count": 7},
    ]


def load_enterprise_events(limit: int = 8000) -> list[dict]:
    processed = ROOT / "enterprise_data" / "processed" / "finguard_enterprise_transactions.jsonl"
    sample = ROOT / "data" / "sample_events" / "transactions.json"
    return read_json_lines([processed if processed.exists() else sample], limit=limit)


def numeric(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def parse_time(value: str) -> datetime:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except (TypeError, ValueError):
        return datetime.now(timezone.utc)


def amount_risk_score(event: dict) -> float:
    amount = numeric(event.get("amount"))
    score = min(99.0, 18.0 + math.log10(max(amount, 1.0)) * 10.0)
    label = str(event.get("risk_label") or "NORMAL").upper()
    if event.get("is_black_device"):
        score += 18.0
    if event.get("is_black_card"):
        score += 10.0
    if label != "NORMAL":
        score += 12.0
    if str(event.get("transaction_status", "")).upper() == "FAILED":
        score += 7.0
    return round(min(score, 100.0), 2)


def group_count(records: list[dict], key: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for record in records:
        value = str(record.get(key) or "UNKNOWN")
        result[value] = result.get(value, 0) + 1
    return result


def top_amount(records: list[dict], key: str, limit: int = 10) -> list[dict]:
    result: dict[str, float] = {}
    for record in records:
        value = str(record.get(key) or "UNKNOWN")
        result[value] = result.get(value, 0.0) + numeric(record.get("amount"))
    return [
        {"name": name, "value": round(value, 2)}
        for name, value in sorted(result.items(), key=lambda item: item[1], reverse=True)[:limit]
    ]


def build_time_series(events: list[dict], buckets: int = 36) -> list[dict]:
    if not events:
        return []
    sorted_events = sorted(events, key=lambda event: parse_time(event.get("event_time")).timestamp())
    chunk = max(1, math.ceil(len(sorted_events) / buckets))
    rows = []
    for index in range(0, len(sorted_events), chunk):
        part = sorted_events[index:index + chunk]
        if not part:
            continue
        ts = parse_time(part[-1].get("event_time")).strftime("%H:%M")
        amount = sum(numeric(event.get("amount")) for event in part)
        failed = sum(1 for event in part if str(event.get("transaction_status", "")).upper() == "FAILED")
        risk = sum(amount_risk_score(event) for event in part) / len(part)
        rows.append({
            "time": ts,
            "count": len(part),
            "amount": round(amount, 2),
            "failed": failed,
            "risk": round(risk, 2),
        })
    return rows[:buckets]


def build_scatter(events: list[dict], limit: int = 800) -> list[list[float | str]]:
    points = []
    step = max(1, len(events) // limit)
    for index, event in enumerate(events[::step][:limit]):
        amount = numeric(event.get("amount"))
        risk = amount_risk_score(event)
        hour = parse_time(event.get("event_time")).hour
        points.append([
            hour,
            round(math.log10(max(amount, 1.0)), 4),
            risk,
            event.get("channel") or "UNKNOWN",
            event.get("risk_label") or "NORMAL",
            event.get("transaction_id") or event.get("event_id") or f"event-{index}",
        ])
    return points


def build_heatmap(events: list[dict]) -> dict:
    channels = sorted(group_count(events, "channel").keys())
    labels = sorted(group_count(events, "risk_label").keys())
    if not channels:
        channels = ["APP", "H5", "API"]
    if not labels:
        labels = ["NORMAL"]
    channel_index = {value: idx for idx, value in enumerate(channels)}
    label_index = {value: idx for idx, value in enumerate(labels)}
    matrix: dict[tuple[int, int], int] = {}
    for event in events:
        x = channel_index.get(str(event.get("channel") or "UNKNOWN"), 0)
        y = label_index.get(str(event.get("risk_label") or "NORMAL"), 0)
        matrix[(x, y)] = matrix.get((x, y), 0) + 1
    data = [[x, y, value] for (x, y), value in matrix.items()]
    return {"channels": channels, "labels": labels, "data": data}


def build_flow_links(events: list[dict], limit: int = 12) -> list[dict]:
    merchants = top_amount(events, "merchant_id", limit=limit)
    cities = top_amount(events, "city", limit=limit)
    city_names = [item["name"] for item in cities] or ["Global"]
    links = []
    for index, merchant in enumerate(merchants):
        links.append({
            "source": city_names[index % len(city_names)],
            "target": merchant["name"],
            "value": merchant["value"],
        })
    return links


def build_insights(alerts: list[dict], events: list[dict], metadata: dict, series: list[dict]) -> list[str]:
    high_count = sum(1 for alert in alerts if str(alert.get("risk_level", "")).upper() == "HIGH")
    converted = int(metadata.get("converted_rows") or 0)
    laundering = int(metadata.get("laundering_rows") or 0)
    avg_risk = round(sum(amount_risk_score(event) for event in events) / max(len(events), 1), 2)
    max_bucket = max(series, key=lambda row: row["amount"], default={"time": "--:--", "amount": 0})
    top_channel = max(group_count(events, "channel").items(), key=lambda item: item[1], default=("UNKNOWN", 0))

    insights = [
        f"当前样本综合风险脉冲为 {avg_risk}/100，建议优先核查三维星图中高金额、高风险聚集区。",
        f"交易金额峰值出现在 {max_bucket['time']} 附近，窗口金额约 {max_bucket['amount']:.2f}，可联动商户收款突增规则复核。",
        f"当前主通道为 {top_channel[0]}，样本量 {top_channel[1]} 笔，建议同步观察渠道成功率、Kafka lag 与 Flink 反压。",
    ]
    if high_count:
        insights.insert(0, f"当前存在 {high_count} 条高风险告警，应优先处理黑名单设备、多账户关联和银行卡共用风险。")
    if converted and laundering:
        insights.append(f"企业级样本 AML 标签密度约 {laundering / converted * 100:.4f}%，属于低频高危模式，适合做规则召回率压测。")
    insights.append("若压测时出现消息积压，建议同时提升 Kafka 分区数、Flink 并行度和文件 Sink 滚动粒度。")
    return insights[:5]


def build_dashboard_payload() -> dict:
    alerts = load_alerts()
    metrics = load_metrics()
    events = load_enterprise_events()
    metadata = load_metadata()
    series = build_time_series(events)
    late_count = len(files_under(ROOT / "data" / "late_events"))
    total_amount = sum(numeric(event.get("amount")) for event in events)
    high_alerts = sum(1 for alert in alerts if str(alert.get("risk_level", "")).upper() == "HIGH")
    avg_risk = round(sum(amount_risk_score(event) for event in events) / max(len(events), 1), 2)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "overview": {
            "event_sample_count": len(events),
            "alert_count": len(alerts),
            "high_alert_count": high_alerts,
            "late_file_count": late_count,
            "sample_amount": round(total_amount, 2),
            "avg_risk_score": avg_risk,
            "enterprise_converted_rows": metadata.get("converted_rows", 0),
            "enterprise_source_size_bytes": metadata.get("source_size_bytes", metadata.get("source_size", 0)),
            "max_amount": metadata.get("max_amount", 0),
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
        "metrics": metrics[-30:][::-1],
        "insights": build_insights(alerts, events, metadata, series),
    }


class DashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/dashboard":
            self.send_json(build_dashboard_payload())
            return
        if parsed.path == "/":
            self.serve_file(STATIC_DIR / "index.html")
            return
        static_path = (STATIC_DIR / parsed.path.lstrip("/")).resolve()
        if STATIC_DIR in static_path.parents and static_path.exists():
            self.serve_file(static_path)
            return
        self.send_error(404, "Not found")

    def log_message(self, format: str, *args) -> None:
        return

    def send_json(self, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def serve_file(self, path: Path) -> None:
        content = path.read_bytes()
        content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run FinGuard immersive 3D risk dashboard.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8090)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    server = ThreadingHTTPServer((args.host, args.port), DashboardHandler)
    print(f"FinGuard immersive dashboard: http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
