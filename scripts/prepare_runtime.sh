#!/usr/bin/env bash
set -euo pipefail

runtime_dirs=(
  data/checkpoints
  data/output/realtime_metrics
  data/output/dead_letter
  data/alerts/risk_alerts
  data/late_events
)

mkdir -p "${runtime_dirs[@]}"
chmod 0777 "${runtime_dirs[@]}"

printf "Prepared writable local Flink runtime directories.\n"
