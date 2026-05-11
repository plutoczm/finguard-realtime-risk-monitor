#!/usr/bin/env bash
set -euo pipefail

BOOTSTRAP_SERVER="${BOOTSTRAP_SERVER:-localhost:9092}"

topics=(
  "payment_transaction_events:6"
  "payment_user_events:3"
  "payment_risk_alerts:3"
  "payment_realtime_metrics:3"
  "payment_late_events:3"
  "payment_dead_letter_events:3"
)

for topic_spec in "${topics[@]}"; do
  topic="${topic_spec%%:*}"
  partitions="${topic_spec##*:}"
  kafka-topics \
    --bootstrap-server "${BOOTSTRAP_SERVER}" \
    --create \
    --if-not-exists \
    --topic "${topic}" \
    --partitions "${partitions}" \
    --replication-factor 1
done

kafka-topics --bootstrap-server "${BOOTSTRAP_SERVER}" --list
