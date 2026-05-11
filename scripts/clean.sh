#!/usr/bin/env bash
set -euo pipefail

docker compose down -v --remove-orphans

rm -rf data/output/realtime_metrics
rm -rf data/output/dead_letter
rm -rf data/alerts/risk_alerts
rm -rf data/late_events/*
mkdir -p data/output/realtime_metrics data/output/dead_letter data/alerts/risk_alerts data/late_events data/sample_events

printf "# Runtime Realtime Metrics\n\nFlink writes metric part files here when using the default local file sink.\n" > data/output/realtime_metrics/README.md
printf "# Runtime Dead Letter Events\n\nInvalid or unparsable transaction events are written here by the Flink job.\n" > data/output/dead_letter/README.md
printf "# Runtime Risk Alerts\n\nMatched risk alerts are written here by the Flink job.\n" > data/alerts/risk_alerts/README.md
printf "# Late Events Output\n\nEvents older than the current Flink watermark are routed here for audit and replay analysis.\n" > data/late_events/README.md

printf "FinGuard local runtime data cleaned.\n"
