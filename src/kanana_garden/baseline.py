"""Collect a repeatable Raspberry Pi 5 quality and performance baseline."""

from __future__ import annotations

import json
import math
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from .client import KananaClient
from .device import device_report, runtime_telemetry
from .recipe import Recipe, RecipeError
from .verification import recipe_digest, sanitized_endpoint


MIN_REPETITIONS = 3
MAX_REPETITIONS = 20
MAX_TEMPERATURE_C = 80.0
SAFE_THROTTLED = "throttled=0x0"


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


def _telemetry_values(
    device_before: dict[str, Any],
    recipe_runs: list[dict[str, Any]],
    device_after: dict[str, Any],
) -> tuple[list[float], list[str], int]:
    samples = [
        sample
        for recipe_run in recipe_runs
        for sample in recipe_run.get("samples", [])
        if isinstance(sample, dict)
    ]
    readings: list[dict[str, Any]] = [
        device_before,
        *samples,
        device_after,
    ]
    temperatures = [
        float(reading["temperature_c"])
        for reading in readings
        if _is_number(reading.get("temperature_c"))
    ]
    throttled = [
        reading["throttled"]
        for reading in readings
        if isinstance(reading.get("throttled"), str)
    ]
    return temperatures, throttled, len(readings)


def build_pi5_baseline_report(
    *,
    endpoint: str,
    requested_model: str,
    exposed_models: list[str],
    repetitions: int,
    recipe_runs: list[dict[str, Any]],
    device_before: dict[str, Any],
    device_after: dict[str, Any],
    stop_reason: str | None = None,
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
    temperatures, throttled_values, telemetry_reading_count = _telemetry_values(
        device_before,
        recipe_runs,
        device_after,
    )
    telemetry_complete = (
        len(temperatures) == telemetry_reading_count
        and len(throttled_values) == telemetry_reading_count
    )
    performance_complete = len(token_rates) == len(samples)
    throttling_observed = any(
        value != SAFE_THROTTLED for value in throttled_values
    )
    max_temperature = max(temperatures) if temperatures else None
    complete = (
        repetitions >= MIN_REPETITIONS
        and expected_sample_count > 0
        and len(samples) == expected_sample_count
        and stop_reason is None
    )
    passed = (
        complete
        and device_before.get("ready") is True
        and device_after.get("ready") is True
        and passed_count == len(samples)
        and telemetry_complete
        and performance_complete
        and max_temperature is not None
        and max_temperature < MAX_TEMPERATURE_C
        and not throttling_observed
    )
    timestamp = checked_at or datetime.now(timezone.utc)
    return {
        "schema_version": 1,
        "kind": "kanana-garden-pi5-baseline",
        "powered_by": "Kanana",
        "checked_at": timestamp.astimezone(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        "profile": "raspberry-pi-5-8gb",
        "endpoint": sanitized_endpoint(endpoint),
        "requested_model": requested_model,
        "exposed_models": list(exposed_models),
        "repetitions": repetitions,
        "complete": complete,
        "passed": passed,
        "stop_reason": stop_reason,
        "device_before": device_before,
        "device_after": device_after,
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
            "max_temperature_c": (
                round(max_temperature, 3)
                if max_temperature is not None
                else None
            ),
            "telemetry_complete": telemetry_complete,
            "performance_complete": performance_complete,
            "throttling_observed": throttling_observed,
        },
    }


def run_pi5_baseline(
    *,
    client: KananaClient,
    endpoint: str,
    model: str,
    recipes: Iterable[Recipe],
    repetitions: int = MIN_REPETITIONS,
    model_dir: Path | None = None,
    device_probe: Callable[[Path | None], dict[str, Any]] | None = None,
    telemetry_probe: Callable[[], dict[str, Any]] | None = None,
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

    probe_device = device_probe or device_report
    probe_telemetry = telemetry_probe or runtime_telemetry
    monotonic = clock or time.monotonic
    before = probe_device(model_dir)
    if before.get("ready") is not True:
        raise RecipeError(
            "Raspberry Pi 5 사전 점검이 통과하지 않았습니다. "
            "먼저 device-doctor를 실행하세요."
        )

    exposed_models = client.list_models()
    if model not in exposed_models:
        raise RecipeError(
            f"요청 모델 '{model}'이 서버 모델 목록에 없습니다: "
            f"{', '.join(exposed_models)}"
        )

    recipe_runs: list[dict[str, Any]] = [
        {
            "slug": recipe.slug,
            "sha256": recipe_digest(recipe),
            "example_count": len(recipe.examples),
            "samples": [],
        }
        for recipe in selected_recipes
    ]
    stop_reason: str | None = None
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
                telemetry = probe_telemetry()
                temperature = telemetry.get("temperature_c")
                throttled = telemetry.get("throttled")
                expected = example.get("expected_contains")
                content_passed = (
                    expected is None or expected in response.content
                )
                model_matched = response.model == model
                recipe_run["samples"].append(
                    {
                        "repetition": repetition,
                        "example_index": example_index,
                        "expected_contains": expected,
                        "response_model": response.model,
                        "model_matched": model_matched,
                        "content": response.content,
                        "usage": response.usage,
                        "latency_seconds": elapsed,
                        "tokens_per_second": tokens_per_second,
                        "temperature_c": temperature,
                        "throttled": throttled,
                        "passed": content_passed and model_matched,
                    }
                )
                if _is_number(temperature) and temperature >= MAX_TEMPERATURE_C:
                    stop_reason = "temperature_limit"
                    break
                if isinstance(throttled, str) and throttled != SAFE_THROTTLED:
                    stop_reason = "throttling_detected"
                    break
            if stop_reason is not None:
                break
        if stop_reason is not None:
            break

    after = probe_device(model_dir)
    return build_pi5_baseline_report(
        endpoint=endpoint,
        requested_model=model,
        exposed_models=exposed_models,
        repetitions=repetitions,
        recipe_runs=recipe_runs,
        device_before=before,
        device_after=after,
        stop_reason=stop_reason,
        checked_at=checked_at,
    )


def write_pi5_baseline_report(report: dict[str, Any], path: Path) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        raise RecipeError(f"{path} 리포트를 쓸 수 없습니다: {exc}") from exc
