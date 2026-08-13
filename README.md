# FinGuard — Realtime Risk Engine + AI Investigation Copilot

FinGuard 是一个面向支付风控场景的工程化作品：**Kafka + Flink 负责实时、确定性的风险检测，AI Risk Copilot 负责告警解释与人工调查辅助**。项目刻意把 LLM 放在硬实时决策链路之外，使模型失败、超时或不可用时不会阻塞支付风控主链路。

> Portfolio focus: streaming systems, AI application engineering, structured outputs, graceful degradation, PII minimization, evaluation and CI.

## Architecture

```mermaid
flowchart LR
    P[Transaction Producer] --> K[Kafka]
    K --> F[Flink Risk Engine]
    F --> M[Realtime Metrics]
    F --> A[Risk Alerts]
    M --> D[Dashboard]
    A --> D
    A --> C[AI Risk Copilot]
    C --> H[Human Risk Analyst]
    C -. provider unavailable .-> G[Deterministic Fallback]
```

### Why hybrid instead of “LLM does fraud detection”

- **Flink rules** own deterministic, low-latency detection, event-time windows, state, deduplication and late-data handling.
- **LLM copilot** turns structured alert evidence into analyst-facing summaries, recommended next actions and investigation steps.
- The model **cannot authorize or reject payments**.
- Raw user/device/merchant IDs are pseudonymized before model calls; raw IP is excluded.
- LLM responses use a strict JSON schema and fall back to deterministic explanations on missing key, timeout, provider error or parse/schema failure.

## Main capabilities

| Layer | Capability |
|---|---|
| Ingestion | Python producer, synthetic/enterprise AML datasets, Kafka topics |
| Streaming | Flink DataStream, Watermark, windows, keyed state, TTL, deduplication |
| Detection | frequency, amount spike, multi-user device/card, consecutive failure, blacklist rules |
| Reliability | checkpoint boundary, dead-letter output, late-event side output, idempotent alert IDs |
| AI application | FastAPI copilot, OpenAI Responses API, Structured Outputs, prompt versioning |
| AI safety | PII minimization, grounded-context contract, human-in-the-loop, deterministic fallback |
| Evaluation | golden-set action/evidence checks runnable without an API key |
| Observability | AI request/fallback/latency metrics plus Flink/Kafka operational signals |
| Delivery | Docker Compose, Vercel dashboard, GitHub Actions Python + Java CI |

## Quick start

```bash
pip install -r requirements.txt
make test
```

Start Kafka/Flink:

```bash
make up
make create-topics
make generate
make submit-job
make produce
```

Start dashboard:

```bash
make dashboard
# http://127.0.0.1:8090
```

Start AI copilot:

```bash
# Optional: export OPENAI_API_KEY=...
make ai
# http://127.0.0.1:8091/docs
```

Without `OPENAI_API_KEY`, the AI API remains available in deterministic fallback mode.

Docker profile:

```bash
docker compose --profile ai up -d ai-copilot
```

## AI API example

`POST /v1/explanations`

```json
{
  "alert": {
    "rule_id": "R006",
    "risk_level": "HIGH",
    "reason": "当前交易设备命中黑名单设备",
    "evidence": {"is_black_device": true}
  },
  "transaction": {
    "amount": 899,
    "currency": "CNY",
    "channel": "APP",
    "user_id": "user-demo",
    "device_id": "device-black-001"
  }
}
```

Response contains `summary`, `recommended_action`, `confidence`, `key_evidence`, `investigation_steps`, `limitations`, `source`, `prompt_version` and `model`.

## Evaluation

```bash
make ai-eval
```

The golden set verifies deterministic expectations such as recommended action, evidence coverage and response completeness. A production extension should track schema-valid rate, grounded-evidence rate, action agreement, fallback rate, p95 latency, model cost and analyst acceptance rate.

## Risk rules

| Rule | Description | Level |
|---|---|---|
| R001 | user transaction count > 10 / 1 min | MEDIUM |
| R002 | user amount > CNY 20,000 / 5 min | HIGH |
| R003 | device linked to > 5 users / 10 min | HIGH |
| R004 | card linked to > 3 users / 10 min | HIGH |
| R005 | consecutive failures > 5 | MEDIUM |
| R006 | blacklisted device | HIGH |
| R007 | amount > 5x user historical average | MEDIUM |
| R008 | merchant 5-min amount > 3x historical baseline | HIGH |

## Repository map

```text
ai_service/     FastAPI + LLM/fallback investigation copilot
evals/          golden-set AI evaluation cases
producer/       event generation and Kafka producers
flink-job/      Java Flink real-time risk job
dashboard/      risk monitoring UI/API
tests/          Python tests
docs/           architecture, reliability, AI and interview notes
scripts/        local operations and data tooling
```

## Public dashboard

The visualization-only static demo is deployed at:

`https://finguard-realtime-risk-monitor.vercel.app`

Kafka/Flink and the AI copilot are infrastructure services; Vercel hosts the static cockpit/demo data only.

## Engineering docs

- `docs/AI_COPILOT.md`
- `docs/ARCHITECTURE.md`
- `docs/KAFKA_DESIGN.md`
- `docs/FLINK_DESIGN.md`
- `docs/WATERMARK_AND_LATE_DATA.md`
- `docs/STATE_AND_RELIABILITY.md`
- `docs/RISK_RULES.md`
- `docs/INTERVIEW_QA.md`
