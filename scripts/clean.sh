#!/usr/bin/env bash
set -euo pipefail

docker compose down -v --remove-orphans

rm -rf data/output data/alerts data/late_events data/checkpoints
mkdir -p data/output/realtime_metrics data/output/dead_letter data/alerts/risk_alerts data/late_events data/checkpoints data/sample_events

printf "FinGuard local runtime data cleaned.\n"
