from __future__ import annotations

import argparse
import json
from pathlib import Path

from ai_service.models import ExplainRequest
from ai_service.service import RiskExplainer


def evaluate(dataset: Path, live_llm: bool = False) -> dict:
    explainer = RiskExplainer(api_key=None if live_llm else "")
    total = 0
    passed = 0
    failures: list[dict] = []

    for line_number, line in enumerate(dataset.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        case = json.loads(line)
        request = ExplainRequest.model_validate(case["input"])
        result = explainer.explain(request)

        checks = [
            result.recommended_action == case["expected_action"],
            any(token.lower() in result.summary.lower() or any(token.lower() in item.lower() for item in result.key_evidence)
                for token in case["must_mention_any"]),
            len(result.key_evidence) > 0,
            len(result.investigation_steps) > 0,
        ]
        total += 1
        if all(checks):
            passed += 1
        else:
            failures.append(
                {
                    "line": line_number,
                    "expected_action": case["expected_action"],
                    "actual_action": result.recommended_action,
                    "summary": result.summary,
                }
            )

    return {
        "total": total,
        "passed": passed,
        "pass_rate": passed / total if total else 0.0,
        "failures": failures,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run FinGuard risk-copilot golden-set evaluation.")
    parser.add_argument("--dataset", default="evals/golden_risk_cases.jsonl")
    parser.add_argument("--min-pass-rate", type=float, default=1.0)
    parser.add_argument("--live-llm", action="store_true")
    args = parser.parse_args()

    report = evaluate(Path(args.dataset), live_llm=args.live_llm)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["pass_rate"] < args.min_pass_rate:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
