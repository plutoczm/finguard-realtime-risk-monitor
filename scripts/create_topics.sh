#!/usr/bin/env bash
set -euo pipefail

BOOTSTRAP_SERVER="${BOOTSTRAP_SERVER:-localhost:9092}"
TRANSACTION_TOPIC="${TRANSACTION_TOPIC:-payment_transaction_events}"
PARTITIONS="${PARTITIONS:-6}"

kafka-topics \
  --bootstrap-server "${BOOTSTRAP_SERVER}" \
  --create \
  --if-not-exists \
  --topic "${TRANSACTION_TOPIC}" \
  --partitions "${PARTITIONS}" \
  --replication-factor 1

kafka-topics --bootstrap-server "${BOOTSTRAP_SERVER}" --describe --topic "${TRANSACTION_TOPIC}"
