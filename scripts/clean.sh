#!/usr/bin/env bash
set -euo pipefail

docker compose down -v --remove-orphans

rm -rf data/output data/alerts data/late_events data/checkpoints data/ai_copilot
mkdir -p data/sample_events
bash scripts/prepare_runtime.sh

printf "FinGuard local runtime and AI audit data cleaned.\n"
