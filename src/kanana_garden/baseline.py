"""Collect a repeatable quality and performance baseline from the 5600G server."""

from __future__ import annotations

import json
import math
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from .client import KananaClient
from .recipe import Recipe, RecipeError
from .verification import recipe_digest, sanitized_endpoint


MIN_REPETITIONS = 3
MAX_REPETITIONS = 20
SERVER_PROFILE = "ryzen-5-5600g"


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _rounded_median(values: list[float]) -> float | None:
    return round(statistics.median(values), 6) if values else None


def _rounded_p95(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(0.95 * len(ordered)) - 1)
    return round(ordered[index], 6)


def build_server_baseline_report(
    *,
    endpoint: str,
    requested_model: str,
    exposed_models: list[str],
    repetitions: int,
    recipe_runs: list[dict[str, Any]],
    runtime: dict[str, Any],
    checked_at: datetime | None = None,
) -> dict[str, Any]:
    samples = [
        sample
        for recipe_run in recipe_runs
        for sample in recipe_run.get("samples", [])
        if isinstance(sample, dict)
    ]
    expected_sample_count = sum(
        recipe_run.get("example_count", 0) * repetitions
        for recipe_run in recipe_runs
        if isinstance(recipe_run.get("example_count"), int)
        and not isinstance(recipe_run.get("example_count"), bool)
    )
    passed_count = sum(sample.get("passed") is True for sample in samples)
    latencies = [
        float(sample["latency_seconds"])
        for sample in samples
        if _is_number(sample.get("latency_seconds"))
    ]
    token_rates = [
        float(sample["tokens_per_second"])
        for sample in samples
        if _is_number(sample.get("tokens_per_second"))
    ]
    complete = (
        repetitions >= MIN_REPETITIONS
        and expected_sample_count > 0
        and len(samples) == expected_sample_count
    )
    performance_complete = len(token_rates) == len(samples)
    runtime_complete = all(
        isinstance(runtime.get(name), str) and bool(runtime[name])
        for name in ("session_id", "revision", "dtype")
    )
    passed = (
        complete
        and passed_count == len(samples)
        and performance_complete
        and runtime_complete
    )
    timestamp = checked_at or datetime.now(timezone.utc)
    return {
        "schema_version": 1,
        "kind": "kanana-garden-server-baseline",
        "powered_by": "Kanana",
        "checked_at": timestamp.astimezone(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        "profile": SERVER_PROFILE,
        "endpoint": sanitized_endpoint(endpoint),
        "requested_model": requested_model,
        "exposed_models": list(exposed_models),
        "runtime": dict(runtime),
        "repetitions": repetitions,
        "complete": complete,
        "passed": passed,
        "recipes": recipe_runs,
        "summary": {
            "recipe_count": len(recipe_runs),
            "expected_sample_count": expected_sample_count,
            "sample_count": len(samples),
            "passed_sample_count": passed_count,
            "pass_rate": passed_count / len(samples) if samples else 0,
            "median_latency_seconds": _rounded_median(latencies),
            "p95_latency_seconds": _rounded_p95(latencies),
            "median_tokens_per_second": _rounded_median(token_rates),
            "performance_complete": performance_complete,
            "runtime_metadata_complete": runtime_complete,
        },
    }


def run_server_baseline(
    *,
    client: KananaClient,
    endpoint: str,
    model: str,
    recipes: Iterable[Recipe],
    repetitions: int = MIN_REPETITIONS,
    clock: Callable[[], float] | None = None,
    checked_at: datetime | None = None,
) -> dict[str, Any]:
    if not MIN_REPETITIONS <= repetitions <= MAX_REPETITIONS:
        raise RecipeError(
            f"repetitions는 {MIN_REPETITIONS} 이상 "
            f"{MAX_REPETITIONS} 이하여야 합니다."
        )
    selected_recipes = tuple(recipes)
    if not selected_recipes:
        raise RecipeError("기준선에 사용할 레시피가 없습니다.")
    mismatched_recipes = [
        recipe.slug for recipe in selected_recipes if recipe.model != model
    ]
    if mismatched_recipes:
        raise RecipeError(
            f"요청 모델 '{model}'이 recipe 모델과 다릅니다: "
            f"{', '.join(mismatched_recipes)}"
        )

    runtime_info = client.runtime_info(model)
    exposed_models = runtime_info["exposed_models"]
    runtime = runtime_info["runtime"]
    if model not in exposed_models:
        raise RecipeError(
            f"요청 모델 '{model}'이 서버 모델 목록에 없습니다: "
            f"{', '.join(exposed_models)}"
        )
    monotonic = clock or time.monotonic
    recipe_runs: list[dict[str, Any]] = [
        {
            "slug": recipe.slug,
            "sha256": recipe_digest(recipe),
            "example_count": len(recipe.examples),
            "samples": [],
        }
        for recipe in selected_recipes
    ]
    for recipe, recipe_run in zip(selected_recipes, recipe_runs):
        for repetition in range(1, repetitions + 1):
            for example_index, example in enumerate(recipe.examples, start=1):
                started = monotonic()
                response = client.chat(
                    model=model,
                    messages=recipe.render(example["input"]),
                    generation=recipe.generation,
                )
                elapsed = max(round(monotonic() - started, 6), 0.000001)
                completion_tokens = response.usage.get("completion_tokens")
                tokens_per_second = (
                    round(completion_tokens / elapsed, 3)
                    if isinstance(completion_tokens, int)
                    and not isinstance(completion_tokens, bool)
                    and completion_tokens >= 0
                    else None
                )
                expected = example.get("expected_contains")
                content_passed = expected is None or expected in response.content
                model_matched = response.model == model
                sample: dict[str, Any] = {
                        "repetition": repetition,
                        "example_index": example_index,
                        "expected_contains": expected,
                        "response_model": response.model,
                        "model_matched": model_matched,
                        "content": response.content,
                        "usage": response.usage,
                        "latency_seconds": elapsed,
                        "tokens_per_second": tokens_per_second,
                        "passed": content_passed and model_matched,
                }
                if recipe.slug == "vehicle-control-ko":
                    from .vehicle_control import parse_vehicle_action

                    try:
                        parsed_action = parse_vehicle_action(response.content)
                    except RecipeError:
                        parsed_action = None
                    sample["action_contract_valid"] = parsed_action is not None
                    sample["parsed_action"] = parsed_action
                    sample["passed"] = sample["passed"] and parsed_action is not None
                recipe_run["samples"].append(sample)

    return build_server_baseline_report(
        endpoint=endpoint,
        requested_model=model,
        exposed_models=exposed_models,
        repetitions=repetitions,
        recipe_runs=recipe_runs,
        runtime=runtime,
        checked_at=checked_at,
    )


def write_server_baseline_report(report: dict[str, Any], path: Path) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        raise RecipeError(f"{path} 리포트를 쓸 수 없습니다: {exc}") from exc
