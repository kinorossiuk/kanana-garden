"""Compare a reference Kanana runtime with an edge runtime candidate."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .client import KananaClient
from .eval_suite import EvalCase, EvalSuite, evaluate_assertions
from .recipe import RecipeError
from .verification import sanitized_endpoint


def run_endpoint(
    *,
    client: KananaClient,
    endpoint: str,
    model: str,
    cases: tuple[EvalCase, ...],
    generation: dict[str, int | float],
) -> dict[str, Any]:
    exposed_models = client.list_models()
    if model not in exposed_models:
        raise RecipeError(
            f"{sanitized_endpoint(endpoint)}에 모델 '{model}'이 없습니다: "
            f"{', '.join(exposed_models)}"
        )
    results: list[dict[str, Any]] = []
    for case in cases:
        started = time.monotonic()
        response = client.chat(
            model=model,
            messages=[dict(message) for message in case.messages],
            generation=generation,
        )
        latency = time.monotonic() - started
        assertion_result = evaluate_assertions(case, response.content)
        model_matched = response.model == model
        completion_tokens = response.usage.get("completion_tokens")
        tokens_per_second = (
            completion_tokens / latency
            if completion_tokens is not None and latency > 0
            else None
        )
        results.append(
            {
                "id": case.id,
                "category": case.category,
                "passed": assertion_result["passed"] and model_matched,
                "assertions_passed": assertion_result["passed"],
                "assertions": assertion_result["assertions"],
                "response_model": response.model,
                "model_matched": model_matched,
                "content": response.content,
                "usage": response.usage,
                "latency_seconds": round(latency, 3),
                "tokens_per_second": (
                    round(tokens_per_second, 3)
                    if tokens_per_second is not None
                    else None
                ),
            }
        )
    passed_count = sum(result["passed"] for result in results)
    return {
        "endpoint": sanitized_endpoint(endpoint),
        "requested_model": model,
        "exposed_models": exposed_models,
        "pass_count": passed_count,
        "case_count": len(results),
        "pass_rate": passed_count / len(results) if results else 0,
        "cases": results,
    }


def build_parity_report(
    *,
    suite: EvalSuite,
    selected_cases: tuple[EvalCase, ...],
    reference: dict[str, Any],
    candidate: dict[str, Any],
    checked_at: datetime | None = None,
) -> dict[str, Any]:
    reference_by_id = {case["id"]: case for case in reference["cases"]}
    candidate_by_id = {case["id"]: case for case in candidate["cases"]}
    reference_passed_ids = {
        case_id for case_id, case in reference_by_id.items() if case["passed"]
    }
    candidate_on_reference = sum(
        candidate_by_id[case_id]["passed"] for case_id in reference_passed_ids
    )
    relative_rate = (
        candidate_on_reference / len(reference_passed_ids)
        if reference_passed_ids
        else 0
    )
    agreement_count = sum(
        reference_by_id[case.id]["passed"] == candidate_by_id[case.id]["passed"]
        for case in selected_cases
    )
    timestamp = checked_at or datetime.now(timezone.utc)
    reference_threshold = suite.thresholds["reference_pass_rate"]
    candidate_threshold = suite.thresholds["candidate_relative_pass_rate"]
    complete = len(selected_cases) == len(suite.cases)
    threshold_passed = (
        reference["pass_rate"] >= reference_threshold
        and relative_rate >= candidate_threshold
    )
    return {
        "schema_version": 1,
        "kind": "kanana-garden-runtime-parity",
        "powered_by": "Kanana",
        "checked_at": timestamp.astimezone(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        "suite": {
            "slug": suite.slug,
            "sha256": suite.digest(),
            "selected_case_count": len(selected_cases),
            "total_case_count": len(suite.cases),
        },
        "thresholds": dict(suite.thresholds),
        "complete": complete,
        "passed": threshold_passed if complete else None,
        "summary": {
            "reference_pass_rate": reference["pass_rate"],
            "candidate_pass_rate": candidate["pass_rate"],
            "candidate_relative_pass_rate": relative_rate,
            "agreement_rate": (
                agreement_count / len(selected_cases) if selected_cases else 0
            ),
        },
        "reference": reference,
        "candidate": candidate,
    }


def write_report(report: dict[str, Any], path: Path) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        raise RecipeError(f"{path} 리포트를 쓸 수 없습니다: {exc}") from exc
