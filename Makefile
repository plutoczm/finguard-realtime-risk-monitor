PYTHON=python
PIP=pip
COMPOSE=docker compose
BOOTSTRAP=localhost:9092
INTERNAL_BOOTSTRAP=kafka:29092
TRANSACTION_TOPIC=payment_transaction_events
JAR=flink-job/target/finguard-risk-monitor-1.0.0.jar

.PHONY: up down create-topics generate produce submit-job logs clean test package ps
.PHONY: download-enterprise convert-enterprise produce-enterprise dashboard ai ai-eval ai-docker ai-benchmark

up:
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

ps:
	$(COMPOSE) ps

create-topics:
	$(COMPOSE) exec kafka bash /scripts/create_topics.sh

generate:
	$(PYTHON) producer/generate_transactions.py --count 1000 --output data/sample_events/transactions.json --mode mixed --abnormal-rate 0.20

produce:
	$(PYTHON) producer/kafka_producer.py --bootstrap-server $(BOOTSTRAP) --topic $(TRANSACTION_TOPIC) --mode mixed --abnormal-rate 0.15 --qps 50 --duration 300

download-enterprise:
	$(PYTHON) scripts/download_enterprise_dataset.py

convert-enterprise:
	$(PYTHON) producer/enterprise_dataset.py --limit 200000

produce-enterprise:
	$(PYTHON) producer/enterprise_kafka_producer.py --bootstrap-server $(BOOTSTRAP) --topic $(TRANSACTION_TOPIC) --qps 500 --limit 100000

dashboard:
	$(PYTHON) dashboard/server.py --port 8090

ai:
	uvicorn ai_service.app:app --host 127.0.0.1 --port 8091

ai-eval:
	$(PYTHON) -m ai_service.eval --min-pass-rate 1.0

ai-benchmark:
	$(PYTHON) scripts/benchmark_ai.py --requests 100 --concurrency 8 --warmup 5 --output reports/benchmarks/ai-latest.json

ai-docker:
	$(COMPOSE) --profile ai up -d ai-copilot

package:
	cd flink-job && mvn -q -DskipTests package

submit-job: package
	$(COMPOSE) exec flink-jobmanager flink run -d -c com.finguard.RiskMonitorJob /opt/flink/usrlib/finguard-risk-monitor-1.0.0.jar --bootstrap-servers $(INTERNAL_BOOTSTRAP) --transaction-topic $(TRANSACTION_TOPIC) --metric-output file:///opt/finguard/data/output/realtime_metrics --alert-output file:///opt/finguard/data/alerts/risk_alerts --late-output file:///opt/finguard/data/late_events --dead-letter-output file:///opt/finguard/data/output/dead_letter

logs:
	$(COMPOSE) logs -f --tail=200

clean:
	bash scripts/clean.sh

test:
	$(PYTHON) -m pytest -q
	$(PYTHON) -m ai_service.eval --min-pass-rate 1.0
	cd flink-job && mvn -q test
