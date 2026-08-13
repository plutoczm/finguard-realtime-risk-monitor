# AI Evaluation Strategy

FinGuard separates deterministic regression gates from optional live-model evaluation so ordinary CI remains reproducible while prompt/model changes can still be compared on the same cases.

## Dataset

`evals/golden_risk_cases.jsonl` contains analyst-style cases grouped into four categories:

- `policy`: expected recommendation for known risk rules;
- `boundary`: unknown rules, critical/medium fallback policy and missing evidence;
- `privacy`: raw identifiers and explicit sensitive fields must not cross the model/audit boundary;
- `adversarial`: untrusted instruction-like text must not change deterministic risk policy.

Each case declares an expected action plus optional evidence tokens, forbidden context/output terms and expected fallback degradation metadata.

## Dimensions

`python -m ai_service.eval` reports five dimensions independently:

1. `action_agreement` — recommendation matches the expected policy/label;
2. `evidence_coverage` — output contains at least one required case signal;
3. `structural_quality` — summary, evidence and investigation steps are non-empty;
4. `privacy_safety` — configured raw sensitive values are absent from sanitized context and output;
5. `degradation_contract` — offline fallback source/reason matches the expected reliability contract.

A case passes only when every applicable dimension passes. CI gates both the case-level pass rate and every dimension-level pass rate.

## Deterministic CI mode

```bash
python -m ai_service.eval \
  --min-pass-rate 1.0 \
  --min-dimension-pass-rate 1.0 \
  --report reports/evals/golden.json
```

No model credential is required. This mode tests policy, privacy and fallback invariants without provider variability. GitHub Actions retains the JSON report as an artifact so regressions are inspectable rather than represented only by a red check.

## Optional live-model mode

```bash
OPENAI_API_KEY=... python -m ai_service.eval --live-llm --report reports/evals/live.json
```

Live mode uses the same dataset but does not require fallback source/degradation metadata. It is intended for prompt/model comparison, not for every commit.

A serious model comparison should run the same commit/dataset multiple times and report at least action agreement, privacy failures, schema/provider failures, latency and cost. Do not interpret model-reported `confidence` as calibrated probability without a separate calibration study.

## Growth policy

Cases should be added from real failure modes and analyst disagreements, not only hand-authored happy paths. The next useful dataset expansion is 50–100 reviewed cases covering contradictory evidence, ambiguous actions, malformed fields, multilingual inputs, provider failures and more adversarial strings.
