# AI Risk Copilot

## Why this AI layer exists

The Flink job remains the deterministic, low-latency control plane. The LLM is deliberately placed after rule detection, where it can add value without becoming a single point of failure for payment authorization.

The copilot converts a structured `RiskAlert` plus a minimized transaction context into:

- a concise analyst summary;
- a recommended next action;
- cited evidence from the supplied context;
- an investigation checklist;
- explicit limitations.

## Reliability and safety boundaries

1. **No autonomous authorization**: the model cannot approve or reject a payment.
2. **PII minimization**: user/device/merchant identifiers are hashed before model calls; raw IP is excluded.
3. **Grounding contract**: the prompt forbids facts outside the supplied alert context.
4. **Structured Outputs**: the provider response is constrained to a JSON schema.
5. **Deterministic fallback**: missing credentials, timeout, provider error, parse error, or schema failure returns a rule-based explanation.
6. **Operational telemetry**: `/metrics` exposes request count, fallback count, and average latency.
7. **Prompt versioning**: every response carries `prompt_version` for auditability.
8. **Golden-set evaluation**: `python -m ai_service.eval` validates expected actions and evidence coverage without requiring an API key.

## API

```bash
uvicorn ai_service.app:app --host 0.0.0.0 --port 8091
```

Without `OPENAI_API_KEY`, the endpoint still works using deterministic fallback mode.

## Evaluation strategy

The current golden set is intentionally small and deterministic. A production-grade next step is to add analyst-labeled cases and track: schema-valid rate, grounded-evidence rate, action agreement, fallback rate, p95 latency, cost per explanation, and analyst acceptance rate.
