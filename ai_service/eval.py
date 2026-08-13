from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Any

from ai_service.models import ExplainRequest
from ai_service.service import PROMPT_VERSION, RiskExplainer, sanitize_context

DIMENSIONS = (
    "action_agreement",
    "evidence_coverage",
    "structural_quality",
    "privacy_safety",
    "degradation_contract",
)


def _contains_any(text: str, tokens: list[str]) -> bool:
    lowered = text.lower()
    return any(str(token).lower() in lowered for token in tokens)


def _contains_none(text: str, tokens: list[str]) -> bool:
    lowered = text.lower()
    return all(str(token).lower() not in lowered for token in tokens)


def _score_case(case: dict[str, Any], request: ExplainRequest, result: Any, live_llm: bool) -> dict[str, bool]:
    expected = case.get("expected", {})
    rendered = json.dumps(result.model_dump(), ensure_ascii=False, sort_keys=True)
    sanitized = json.dumps(sanitize_context(request), ensure_ascii=False, sort_keys=True)
    must_mention_any = [str(item) for item in expected.get("must_mention_any", [])]
    forbidden_output = [str(item) for item in expected.get("forbidden_output_terms", [])]
    forbidden_context = [str(item) for item in expected.get("forbidden_context_terms", [])]
    evidence_coverage = True if not must_mention_any else _contains_any(rendered, must_mention_any)
    privacy_safety = _contains_none(rendered, forbidden_output) and _contains_none(sanitized, forbidden_context)
    degradation_contract = True
    if not live_llm:
        if expected.get("source") is not None:
            degradation_contract = degradation_contract and result.source == expected["source"]
        if expected.get("degradation_reason") is not None:
            degradation_contract = degradation_contract and result.degradation_reason == expected["degradation_reason"]
    return {
        "action_agreement": result.recommended_action == expected.get("action"),
        "evidence_coverage": evidence_coverage,
        "structural_quality": bool(result.summary.strip() and result.key_evidence and result.investigation_steps),
        "privacy_safety": privacy_safety,
        "degradation_contract": degradation_contract,
    }


def evaluate(dataset: Path, live_llm: bool = False) -> dict[str, Any]:
    if live_llm and not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("--live-llm requires OPENAI_API_KEY")
    explainer = RiskExplainer(api_key=None if live_llm else "")
    total = 0
    passed = 0
    failures: list[dict[str, Any]] = []
    dimension_counts: dict[str, dict[str, int]] = {name: {"passed": 0, "total": 0} for name in DIMENSIONS}
    category_counts: dict[str, dict[str, int]] = defaultdict(lambda: {"passed": 0, "total": 0})
    for line_number, line in enumerate(dataset.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        case = json.loads(line)
        request = ExplainRequest.model_validate(case["input"])
        result = explainer.explain(request)
        checks = _score_case(case, request, result, live_llm=live_llm)
        total += 1
        case_passed = all(checks.values())
        passed += int(case_passed)
        category = str(case.get("category") or "uncategorized")
        category_counts[category]["total"] += 1
        category_counts[category]["passed"] += int(case_passed)
        for dimension, ok in checks.items():
            dimension_counts[dimension]["total"] += 1
            dimension_counts[dimension]["passed"] += int(ok)
        if not case_passed:
            failures.append({
                "line": line_number,
                "id": case.get("id", f"line-{line_number}"),
                "category": category,
                "failed_checks": [name for name, ok in checks.items() if not ok],
                "expected_action": case.get("expected", {}).get("action"),
                "actual_action": result.recommended_action,
                "source": result.source,
                "degradation_reason": result.degradation_reason,
                "summary": result.summary,
            })
    dimensions = {name: {**counts, "pass_rate": counts["passed"] / counts["total"] if counts["total"] else 0.0} for name, counts in dimension_counts.items()}
    categories = {name: {**counts, "pass_rate": counts["passed"] / counts["total"] if counts["total"] else 0.0} for name, counts in sorted(category_counts.items())}
    return {
        "dataset": str(dataset),
        "mode": "live_llm" if live_llm else "deterministic_fallback",
        "prompt_version": PROMPT_VERSION,
        "total": total,
        "passed": passed,
        "pass_rate": passed / total if total else 0.0,
        "dimensions": dimensions,
        "categories": categories,
        "failures": failures,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run FinGuard risk-copilot multidimensional regression evaluation.")
    parser.add_argument("--dataset", default="evals/golden_risk_cases.jsonl")
    parser.add_argument("--min-pass-rate", type=float, default=1.0)
    parser.add_argument("--min-dimension-pass-rate", type=float, default=1.0)
    parser.add_argument("--live-llm", action="store_true")
    parser.add_argument("--report", default=None)
    args = parser.parse_args()
    report = evaluate(Path(args.dataset), live_llm=args.live_llm)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.report:
        output = Path(args.report)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")
    failed_dimensions = [name for name, metric in report["dimensions"].items() if metric["pass_rate"] < args.min_dimension_pass_rate]
    if report["pass_rate"] < args.min_pass_rate or failed_dimensions:
        raise SystemExit("evaluation gate failed")


if __name__ == "__main__":
    main()
