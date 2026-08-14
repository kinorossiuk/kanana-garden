"""Recompute stored evidence against the current recipes and eval suites."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit

from .baseline import (
    MAX_REPETITIONS,
    MAX_TEMPERATURE_C,
    MIN_REPETITIONS,
    SAFE_THROTTLED,
    build_pi5_baseline_report,
)
from .eval_suite import EvalSuite, evaluate_assertions, iter_builtin_suites
from .parity import build_parity_report
from .recipe import Recipe, RecipeError, iter_builtin_recipes
from .verification import recipe_digest, sanitized_endpoint


DEVICE_CHECK_NAMES = {
    "raspberry_pi_5",
    "arm64",
    "memory_8gb_profile",
    "free_disk",
    "python",
    "boot_id",
    "device_id",
    "native_bf16",
    "temperature",
    "throttling",
}
DEVICE_REQUIRED_NAMES = {
    "raspberry_pi_5",
    "arm64",
    "memory_8gb_profile",
    "free_disk",
    "python",
    "boot_id",
    "device_id",
}
SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise RecipeError(f"{path} 파일을 읽을 수 없습니다: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RecipeError(
            f"{path} JSON 문법 오류: {exc.msg} "
            f"(line {exc.lineno}, column {exc.colno})"
        ) from exc
    if not isinstance(value, dict):
        raise RecipeError(f"{path} 최상위 값은 JSON 객체여야 합니다.")
    return value


def load_report(path: Path) -> dict[str, Any]:
    return _load_json_object(path)


def load_assets(
    paths: Iterable[Path] = (),
) -> tuple[dict[str, Recipe], dict[str, EvalSuite]]:
    recipes = {recipe.slug: recipe for recipe in iter_builtin_recipes()}
    suites = {suite.slug: suite for suite in iter_builtin_suites()}
    for path in paths:
        data = _load_json_object(path)
        if "prompt_template" in data:
            recipe = Recipe.from_mapping(data, str(path))
            if recipe.slug in recipes:
                raise RecipeError(f"중복 recipe asset slug: {recipe.slug}")
            recipes[recipe.slug] = recipe
        elif "thresholds" in data and "cases" in data:
            suite = EvalSuite.from_mapping(data, str(path))
            if suite.slug in suites:
                raise RecipeError(f"중복 suite asset slug: {suite.slug}")
            suites[suite.slug] = suite
        else:
            raise RecipeError(f"{path} 파일은 recipe 또는 eval suite가 아닙니다.")
    return recipes, suites


def _checked_at(value: Any, errors: list[str]) -> datetime | None:
    if not isinstance(value, str):
        errors.append("checked_at은 ISO-8601 문자열이어야 합니다.")
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        errors.append("checked_at이 올바른 ISO-8601 시간이 아닙니다.")
        return None
    if parsed.tzinfo is None:
        errors.append("checked_at에는 시간대가 있어야 합니다.")
        return None
    return parsed


def _close(left: Any, right: float) -> bool:
    return (
        isinstance(left, (int, float))
        and not isinstance(left, bool)
        and abs(float(left) - right) <= 1e-9
    )


def _endpoint_is_sanitized(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        parts = urlsplit(value)
        parts.port
        return (
            parts.scheme in {"http", "https"}
            and parts.hostname is not None
            and parts.username is None
            and parts.password is None
            and not parts.query
            and not parts.fragment
            and sanitized_endpoint(value) == value
        )
    except ValueError:
        return False


def _base_checks(
    report: dict[str, Any],
    *,
    require_endpoint: bool = False,
) -> list[str]:
    errors: list[str] = []
    if report.get("schema_version") != 1:
        errors.append("schema_version은 1이어야 합니다.")
    if report.get("powered_by") != "Kanana":
        errors.append("powered_by는 Kanana여야 합니다.")
    _checked_at(report.get("checked_at"), errors)
    endpoint = report.get("endpoint")
    if (require_endpoint or endpoint is not None) and not _endpoint_is_sanitized(
        endpoint
    ):
        errors.append("endpoint가 없거나 인증정보 없이 안전하게 정규화되지 않았습니다.")
    return errors


def validate_model_check(
    report: dict[str, Any],
    recipes: dict[str, Recipe],
) -> list[str]:
    errors = _base_checks(report, require_endpoint=True)
    if report.get("kind") != "kanana-garden-model-check":
        errors.append("kind가 kanana-garden-model-check가 아닙니다.")
        return errors
    recipe_meta = report.get("recipe")
    if not isinstance(recipe_meta, dict) or not isinstance(
        recipe_meta.get("slug"), str
    ):
        errors.append("recipe.slug가 없습니다.")
        return errors
    slug = recipe_meta["slug"]
    recipe = recipes.get(slug)
    if recipe is None:
        errors.append(f"현재 asset에서 recipe를 찾을 수 없습니다: {slug}")
        return errors
    if recipe_meta.get("sha256") != recipe_digest(recipe):
        errors.append("recipe SHA-256이 현재 recipe와 일치하지 않습니다.")

    model = report.get("requested_model")
    exposed = report.get("exposed_models")
    if not isinstance(model, str):
        errors.append("requested_model이 문자열이 아닙니다.")
    if not isinstance(exposed, list) or not all(
        isinstance(item, str) for item in exposed
    ):
        errors.append("exposed_models가 문자열 배열이 아닙니다.")
        exposed = []
    if isinstance(model, str) and model not in exposed:
        errors.append("requested_model이 exposed_models에 없습니다.")

    cases = report.get("cases")
    if not isinstance(cases, list):
        errors.append("cases가 배열이 아닙니다.")
        return errors
    if len(cases) != len(recipe.examples):
        errors.append(
            f"case 수가 recipe examples와 다릅니다: "
            f"{len(cases)} != {len(recipe.examples)}"
        )
    recomputed_passes: list[bool] = []
    for offset, example in enumerate(recipe.examples):
        if offset >= len(cases):
            break
        case = cases[offset]
        prefix = f"cases[{offset}]"
        if not isinstance(case, dict):
            errors.append(f"{prefix}가 객체가 아닙니다.")
            recomputed_passes.append(False)
            continue
        if case.get("index") != offset + 1:
            errors.append(f"{prefix}.index가 {offset + 1}이 아닙니다.")
        expected = example.get("expected_contains")
        if case.get("expected_contains") != expected:
            errors.append(f"{prefix}.expected_contains가 recipe와 다릅니다.")
        content = case.get("content")
        content_passed = isinstance(content, str) and (
            expected is None or expected in content
        )
        model_matched = (
            isinstance(model, str) and case.get("response_model") == model
        )
        passed = content_passed and model_matched
        recomputed_passes.append(passed)
        if case.get("model_matched") is not model_matched:
            errors.append(f"{prefix}.model_matched가 재계산 결과와 다릅니다.")
        if case.get("passed") is not passed:
            errors.append(f"{prefix}.passed가 재계산 결과와 다릅니다.")
    overall = bool(recomputed_passes) and all(recomputed_passes)
    if report.get("passed") is not overall:
        errors.append("passed가 case 재계산 결과와 다릅니다.")
    return errors


def validate_device_check(report: dict[str, Any]) -> list[str]:
    errors = _base_checks(report)
    if report.get("kind") != "kanana-garden-device-check":
        errors.append("kind가 kanana-garden-device-check가 아닙니다.")
        return errors
    if report.get("profile") != "raspberry-pi-5-8gb":
        errors.append("profile은 raspberry-pi-5-8gb여야 합니다.")
    checks = report.get("checks")
    if not isinstance(checks, list):
        errors.append("checks가 배열이 아닙니다.")
        return errors

    by_name: dict[str, dict[str, Any]] = {}
    for index, check in enumerate(checks):
        prefix = f"checks[{index}]"
        if not isinstance(check, dict):
            errors.append(f"{prefix}가 객체가 아닙니다.")
            continue
        name = check.get("name")
        if not isinstance(name, str) or name not in DEVICE_CHECK_NAMES:
            errors.append(f"{prefix}.name이 지원하는 장비 점검 이름이 아닙니다.")
            continue
        if name in by_name:
            errors.append(f"중복 장비 점검 이름: {name}")
            continue
        by_name[name] = check
        if not isinstance(check.get("passed"), bool):
            errors.append(f"{prefix}.passed가 bool이 아닙니다.")
        if not isinstance(check.get("required"), bool):
            errors.append(f"{prefix}.required가 bool이 아닙니다.")
        if not isinstance(check.get("detail"), str):
            errors.append(f"{prefix}.detail이 문자열이 아닙니다.")

    missing = sorted(DEVICE_REQUIRED_NAMES - by_name.keys())
    if missing:
        errors.append(f"필수 장비 점검이 없습니다: {', '.join(missing)}")
    for name in DEVICE_REQUIRED_NAMES:
        check = by_name.get(name)
        if check is not None and check.get("required") is not True:
            errors.append(f"{name} 점검은 required=true여야 합니다.")
    native_bf16 = by_name.get("native_bf16")
    if native_bf16 is None:
        errors.append("native_bf16 점검이 없습니다.")
    elif native_bf16.get("required") is not False:
        errors.append("native_bf16 점검은 required=false여야 합니다.")
    boot_id = report.get("boot_id_sha256")
    boot_id_valid = (
        isinstance(boot_id, str) and SHA256_PATTERN.fullmatch(boot_id) is not None
    )
    if not boot_id_valid:
        errors.append("boot_id_sha256이 올바른 SHA-256이 아닙니다.")
    boot_check = by_name.get("boot_id")
    if boot_check is not None:
        if boot_check.get("passed") is not boot_id_valid:
            errors.append("boot_id.passed가 boot_id_sha256과 다릅니다.")
        expected_detail = boot_id if boot_id_valid else "unavailable"
        if boot_check.get("detail") != expected_detail:
            errors.append("boot_id.detail이 boot_id_sha256과 다릅니다.")
    device_id = report.get("device_id_sha256")
    device_id_valid = (
        isinstance(device_id, str)
        and SHA256_PATTERN.fullmatch(device_id) is not None
    )
    if not device_id_valid:
        errors.append("device_id_sha256이 올바른 SHA-256이 아닙니다.")
    device_check = by_name.get("device_id")
    if device_check is not None:
        if device_check.get("passed") is not device_id_valid:
            errors.append("device_id.passed가 device_id_sha256과 다릅니다.")
        expected_detail = device_id if device_id_valid else "unavailable"
        if device_check.get("detail") != expected_detail:
            errors.append("device_id.detail이 device_id_sha256과 다릅니다.")

    valid_checks = [
        check
        for check in by_name.values()
        if isinstance(check.get("passed"), bool)
        and isinstance(check.get("required"), bool)
    ]
    ready = all(check["passed"] for check in valid_checks if check["required"])
    if report.get("ready") is not ready:
        errors.append("ready가 필수 장비 점검 재계산 결과와 다릅니다.")

    temperature = report.get("temperature_c")
    temperature_check = by_name.get("temperature")
    if temperature is None:
        if temperature_check is not None:
            errors.append("temperature_c가 없는데 temperature 점검이 있습니다.")
    elif not isinstance(temperature, (int, float)) or isinstance(temperature, bool):
        errors.append("temperature_c는 숫자 또는 null이어야 합니다.")
    elif temperature_check is None:
        errors.append("temperature_c가 있는데 temperature 점검이 없습니다.")
    elif temperature_check.get("passed") is not (float(temperature) < 80):
        errors.append("temperature.passed가 80°C 기준 재계산 결과와 다릅니다.")

    throttled = report.get("throttled")
    throttling_check = by_name.get("throttling")
    if throttled is None:
        if throttling_check is not None:
            errors.append("throttled가 없는데 throttling 점검이 있습니다.")
    elif not isinstance(throttled, str):
        errors.append("throttled는 문자열 또는 null이어야 합니다.")
    elif throttling_check is None:
        errors.append("throttled가 있는데 throttling 점검이 없습니다.")
    elif throttling_check.get("passed") is not (throttled == "throttled=0x0"):
        errors.append("throttling.passed가 재계산 결과와 다릅니다.")

    recommendations = report.get("recommendations")
    if not isinstance(recommendations, list) or not all(
        isinstance(item, str) for item in recommendations
    ):
        errors.append("recommendations가 문자열 배열이 아닙니다.")
    return errors


def _validate_nested_device(
    value: Any,
    label: str,
    errors: list[str],
) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        errors.append(f"{label}가 객체가 아닙니다.")
        return None
    for error in validate_device_check(value):
        errors.append(f"{label}.{error}")
    return value


def _summary_value_matches(stored: Any, expected: Any) -> bool:
    if expected is None or isinstance(expected, (bool, str)):
        return stored is expected if isinstance(expected, bool) else stored == expected
    if isinstance(expected, int):
        return (
            isinstance(stored, int)
            and not isinstance(stored, bool)
            and stored == expected
        )
    if isinstance(expected, float):
        return _close(stored, float(expected))
    return stored == expected


def validate_pi5_baseline(
    report: dict[str, Any],
    recipes: dict[str, Recipe],
) -> list[str]:
    errors = _base_checks(report, require_endpoint=True)
    if report.get("kind") != "kanana-garden-pi5-baseline":
        errors.append("kind가 kanana-garden-pi5-baseline이 아닙니다.")
        return errors
    if report.get("profile") != "raspberry-pi-5-8gb":
        errors.append("profile은 raspberry-pi-5-8gb여야 합니다.")

    model = report.get("requested_model")
    exposed = report.get("exposed_models")
    if not isinstance(model, str):
        errors.append("requested_model이 문자열이 아닙니다.")
        model = ""
    if not isinstance(exposed, list) or not all(
        isinstance(item, str) for item in exposed
    ):
        errors.append("exposed_models가 문자열 배열이 아닙니다.")
        exposed = []
    if model and model not in exposed:
        errors.append("requested_model이 exposed_models에 없습니다.")

    repetitions = report.get("repetitions")
    if (
        not isinstance(repetitions, int)
        or isinstance(repetitions, bool)
        or not MIN_REPETITIONS <= repetitions <= MAX_REPETITIONS
    ):
        errors.append(
            f"repetitions는 {MIN_REPETITIONS} 이상 "
            f"{MAX_REPETITIONS} 이하의 정수여야 합니다."
        )
        return errors

    before = _validate_nested_device(
        report.get("device_before"), "device_before", errors
    )
    after = _validate_nested_device(
        report.get("device_after"), "device_after", errors
    )
    recipe_values = report.get("recipes")
    if not isinstance(recipe_values, list):
        errors.append("recipes가 배열이 아닙니다.")
        return errors

    required_recipes = tuple(iter_builtin_recipes())
    if model and any(recipe.model != model for recipe in required_recipes):
        errors.append("requested_model이 현재 내장 recipe 모델과 다릅니다.")
    required_slugs = [recipe.slug for recipe in required_recipes]
    stored_slugs = [
        item.get("slug") for item in recipe_values if isinstance(item, dict)
    ]
    if stored_slugs != required_slugs or len(stored_slugs) != len(recipe_values):
        errors.append("recipes가 현재 내장 recipe 전체와 같은 순서가 아닙니다.")
    raw_by_slug = {
        value.get("slug"): value
        for value in recipe_values
        if isinstance(value, dict) and isinstance(value.get("slug"), str)
    }
    if len(raw_by_slug) != len(stored_slugs):
        errors.append("recipes에 중복 slug가 있습니다.")

    rebuilt_runs: list[dict[str, Any]] = []
    shortened = False
    all_rebuilt_samples: list[dict[str, Any]] = []
    for recipe in required_recipes:
        raw = raw_by_slug.get(recipe.slug)
        if not isinstance(raw, dict):
            errors.append(f"recipes에 {recipe.slug}가 없습니다.")
            rebuilt_runs.append(
                {
                    "slug": recipe.slug,
                    "sha256": recipe_digest(recipe),
                    "example_count": len(recipe.examples),
                    "samples": [],
                }
            )
            shortened = True
            continue
        prefix = f"recipes[{recipe.slug}]"
        if raw.get("sha256") != recipe_digest(recipe):
            errors.append(f"{prefix}.sha256이 현재 recipe와 다릅니다.")
        if raw.get("example_count") != len(recipe.examples):
            errors.append(f"{prefix}.example_count가 현재 recipe와 다릅니다.")
        stored_samples = raw.get("samples")
        if not isinstance(stored_samples, list):
            errors.append(f"{prefix}.samples가 배열이 아닙니다.")
            stored_samples = []
        expected_positions = [
            (repetition, example_index, example)
            for repetition in range(1, repetitions + 1)
            for example_index, example in enumerate(recipe.examples, start=1)
        ]
        if len(stored_samples) > len(expected_positions):
            errors.append(f"{prefix}.samples가 예상 개수보다 많습니다.")
        if shortened and stored_samples:
            errors.append("안전 중단 뒤에 추가 sample이 기록되어 있습니다.")
        rebuilt_samples: list[dict[str, Any]] = []
        for offset, (repetition, example_index, example) in enumerate(
            expected_positions
        ):
            if offset >= len(stored_samples):
                break
            stored = stored_samples[offset]
            sample_prefix = f"{prefix}.samples[{offset}]"
            if not isinstance(stored, dict):
                errors.append(f"{sample_prefix}가 객체가 아닙니다.")
                continue
            if stored.get("repetition") != repetition:
                errors.append(
                    f"{sample_prefix}.repetition이 {repetition}이 아닙니다."
                )
            if stored.get("example_index") != example_index:
                errors.append(
                    f"{sample_prefix}.example_index가 {example_index}이 아닙니다."
                )
            expected_contains = example.get("expected_contains")
            if stored.get("expected_contains") != expected_contains:
                errors.append(
                    f"{sample_prefix}.expected_contains가 recipe와 다릅니다."
                )
            content = stored.get("content")
            if not isinstance(content, str):
                errors.append(f"{sample_prefix}.content가 문자열이 아닙니다.")
                content = ""
            model_matched = stored.get("response_model") == model and bool(model)
            passed = (
                (expected_contains is None or expected_contains in content)
                and model_matched
            )
            if stored.get("model_matched") is not model_matched:
                errors.append(
                    f"{sample_prefix}.model_matched가 재계산 결과와 다릅니다."
                )
            if stored.get("passed") is not passed:
                errors.append(
                    f"{sample_prefix}.passed가 재계산 결과와 다릅니다."
                )

            usage = stored.get("usage")
            if not isinstance(usage, dict):
                errors.append(f"{sample_prefix}.usage가 객체가 아닙니다.")
                usage = {}
            completion_tokens = usage.get("completion_tokens")
            if completion_tokens is not None and (
                not isinstance(completion_tokens, int)
                or isinstance(completion_tokens, bool)
                or completion_tokens < 0
            ):
                errors.append(
                    f"{sample_prefix}.usage.completion_tokens가 유효하지 않습니다."
                )
                completion_tokens = None
            latency = stored.get("latency_seconds")
            if (
                not isinstance(latency, (int, float))
                or isinstance(latency, bool)
                or latency <= 0
            ):
                errors.append(
                    f"{sample_prefix}.latency_seconds가 양수가 아닙니다."
                )
                latency = 0.000001
            expected_rate = (
                round(completion_tokens / float(latency), 3)
                if completion_tokens is not None
                else None
            )
            if expected_rate is None:
                if stored.get("tokens_per_second") is not None:
                    errors.append(
                        f"{sample_prefix}.tokens_per_second가 "
                        "usage 재계산 결과와 다릅니다."
                    )
            elif not _close(stored.get("tokens_per_second"), expected_rate):
                errors.append(
                    f"{sample_prefix}.tokens_per_second가 "
                    "usage 재계산 결과와 다릅니다."
                )

            temperature = stored.get("temperature_c")
            if temperature is not None and (
                not isinstance(temperature, (int, float))
                or isinstance(temperature, bool)
            ):
                errors.append(
                    f"{sample_prefix}.temperature_c가 숫자 또는 null이 아닙니다."
                )
                temperature = None
            throttled = stored.get("throttled")
            if throttled is not None and not isinstance(throttled, str):
                errors.append(
                    f"{sample_prefix}.throttled가 문자열 또는 null이 아닙니다."
                )
                throttled = None

            rebuilt = dict(stored)
            rebuilt.update(
                {
                    "repetition": repetition,
                    "example_index": example_index,
                    "expected_contains": expected_contains,
                    "model_matched": model_matched,
                    "passed": passed,
                    "usage": usage,
                    "latency_seconds": latency,
                    "tokens_per_second": expected_rate,
                    "temperature_c": temperature,
                    "throttled": throttled,
                }
            )
            rebuilt_samples.append(rebuilt)
            all_rebuilt_samples.append(rebuilt)
        if len(stored_samples) < len(expected_positions):
            shortened = True
        rebuilt_runs.append(
            {
                **raw,
                "slug": recipe.slug,
                "sha256": recipe_digest(recipe),
                "example_count": len(recipe.examples),
                "samples": rebuilt_samples,
            }
        )

    recomputed_stop: str | None = None
    stop_offset: int | None = None
    for offset, sample in enumerate(all_rebuilt_samples):
        temperature = sample.get("temperature_c")
        throttled = sample.get("throttled")
        if (
            isinstance(temperature, (int, float))
            and not isinstance(temperature, bool)
            and temperature >= MAX_TEMPERATURE_C
        ):
            recomputed_stop = "temperature_limit"
            stop_offset = offset
            break
        if isinstance(throttled, str) and throttled != SAFE_THROTTLED:
            recomputed_stop = "throttling_detected"
            stop_offset = offset
            break
    if stop_offset is not None and stop_offset != len(all_rebuilt_samples) - 1:
        errors.append("안전 한계 감지 뒤에 추가 sample이 기록되어 있습니다.")
    if shortened and recomputed_stop is None:
        errors.append("불완전한 baseline에 안전 중단 근거가 없습니다.")
    if report.get("stop_reason") != recomputed_stop:
        errors.append("stop_reason이 sample 재계산 결과와 다릅니다.")

    checked_at = _checked_at(report.get("checked_at"), [])
    if before is None or after is None or checked_at is None:
        return errors
    if before.get("boot_id_sha256") != after.get("boot_id_sha256"):
        errors.append("baseline 실행 중 boot ID가 달라졌습니다.")
    if before.get("device_id_sha256") != after.get("device_id_sha256"):
        errors.append("baseline 실행 중 device ID가 달라졌습니다.")
    expected_report = build_pi5_baseline_report(
        endpoint=(
            report["endpoint"]
            if _endpoint_is_sanitized(report.get("endpoint"))
            else "http://invalid"
        ),
        requested_model=model,
        exposed_models=exposed,
        repetitions=repetitions,
        recipe_runs=rebuilt_runs,
        device_before=before,
        device_after=after,
        stop_reason=recomputed_stop,
        checked_at=checked_at,
    )
    if report.get("complete") is not expected_report["complete"]:
        errors.append("complete가 sample 재계산 결과와 다릅니다.")
    if report.get("passed") is not expected_report["passed"]:
        errors.append("passed가 기준선 재계산 결과와 다릅니다.")
    summary = report.get("summary")
    if not isinstance(summary, dict):
        errors.append("summary가 객체가 아닙니다.")
    else:
        for name, expected_value in expected_report["summary"].items():
            if not _summary_value_matches(summary.get(name), expected_value):
                errors.append(f"summary.{name}이 재계산 결과와 다릅니다.")
    return errors


def _validate_endpoint_run(
    run: Any,
    suite: EvalSuite,
    selected_ids: list[str],
    label: str,
    errors: list[str],
) -> dict[str, Any] | None:
    if not isinstance(run, dict):
        errors.append(f"{label}가 객체가 아닙니다.")
        return None
    endpoint = run.get("endpoint")
    if not _endpoint_is_sanitized(endpoint):
        errors.append(f"{label}.endpoint가 없거나 안전하게 정규화되지 않았습니다.")
    model = run.get("requested_model")
    exposed = run.get("exposed_models")
    if not isinstance(model, str):
        errors.append(f"{label}.requested_model이 문자열이 아닙니다.")
    if not isinstance(exposed, list) or not all(
        isinstance(item, str) for item in exposed
    ):
        errors.append(f"{label}.exposed_models가 문자열 배열이 아닙니다.")
        exposed = []
    if isinstance(model, str) and model not in exposed:
        errors.append(f"{label}.requested_model이 exposed_models에 없습니다.")
    cases = run.get("cases")
    if not isinstance(cases, list):
        errors.append(f"{label}.cases가 배열이 아닙니다.")
        return None
    ids = [case.get("id") for case in cases if isinstance(case, dict)]
    if ids != selected_ids:
        errors.append(f"{label}.cases ID 또는 순서가 selected cases와 다릅니다.")
    suite_by_id = {case.id: case for case in suite.cases}
    rebuilt_cases: list[dict[str, Any]] = []
    for index, stored in enumerate(cases):
        prefix = f"{label}.cases[{index}]"
        if not isinstance(stored, dict):
            errors.append(f"{prefix}가 객체가 아닙니다.")
            continue
        case_id = stored.get("id")
        if not isinstance(case_id, str):
            errors.append(f"{prefix}.id가 문자열이 아닙니다.")
            continue
        case = suite_by_id.get(case_id)
        if case is None:
            errors.append(f"{prefix}.id가 suite에 없습니다: {case_id}")
            continue
        if stored.get("category") != case.category:
            errors.append(f"{prefix}.category가 suite와 다릅니다.")
        content = stored.get("content")
        if not isinstance(content, str):
            errors.append(f"{prefix}.content가 문자열이 아닙니다.")
            content = ""
        assertion_result = evaluate_assertions(case, content)
        model_matched = isinstance(model, str) and stored.get("response_model") == model
        passed = assertion_result["passed"] and model_matched
        if stored.get("assertions_passed") is not assertion_result["passed"]:
            errors.append(f"{prefix}.assertions_passed가 재계산 결과와 다릅니다.")
        if stored.get("assertions") != assertion_result["assertions"]:
            errors.append(f"{prefix}.assertions가 재계산 결과와 다릅니다.")
        if stored.get("model_matched") is not model_matched:
            errors.append(f"{prefix}.model_matched가 재계산 결과와 다릅니다.")
        if stored.get("passed") is not passed:
            errors.append(f"{prefix}.passed가 재계산 결과와 다릅니다.")
        rebuilt = dict(stored)
        rebuilt.update(
            {
                "assertions_passed": assertion_result["passed"],
                "assertions": assertion_result["assertions"],
                "model_matched": model_matched,
                "passed": passed,
            }
        )
        rebuilt_cases.append(rebuilt)
    pass_count = sum(case["passed"] for case in rebuilt_cases)
    pass_rate = pass_count / len(rebuilt_cases) if rebuilt_cases else 0
    if run.get("pass_count") != pass_count:
        errors.append(f"{label}.pass_count가 재계산 결과와 다릅니다.")
    if run.get("case_count") != len(rebuilt_cases):
        errors.append(f"{label}.case_count가 재계산 결과와 다릅니다.")
    if not _close(run.get("pass_rate"), pass_rate):
        errors.append(f"{label}.pass_rate가 재계산 결과와 다릅니다.")
    rebuilt_run = dict(run)
    rebuilt_run.update(
        {
            "pass_count": pass_count,
            "case_count": len(rebuilt_cases),
            "pass_rate": pass_rate,
            "cases": rebuilt_cases,
        }
    )
    return rebuilt_run


def validate_parity(
    report: dict[str, Any],
    suites: dict[str, EvalSuite],
) -> list[str]:
    errors = _base_checks(report)
    if report.get("kind") != "kanana-garden-runtime-parity":
        errors.append("kind가 kanana-garden-runtime-parity가 아닙니다.")
        return errors
    suite_meta = report.get("suite")
    if not isinstance(suite_meta, dict) or not isinstance(suite_meta.get("slug"), str):
        errors.append("suite.slug가 없습니다.")
        return errors
    suite = suites.get(suite_meta["slug"])
    if suite is None:
        errors.append(f"현재 asset에서 suite를 찾을 수 없습니다: {suite_meta['slug']}")
        return errors
    if suite_meta.get("sha256") != suite.digest():
        errors.append("suite SHA-256이 현재 suite와 일치하지 않습니다.")
    if report.get("thresholds") != suite.thresholds:
        errors.append("thresholds가 현재 suite와 일치하지 않습니다.")

    reference_raw = report.get("reference")
    candidate_raw = report.get("candidate")
    if not isinstance(reference_raw, dict) or not isinstance(
        reference_raw.get("cases"), list
    ):
        errors.append("reference.cases가 없습니다.")
        return errors
    selected_ids = [
        case.get("id") for case in reference_raw["cases"] if isinstance(case, dict)
    ]
    if len(selected_ids) != len(reference_raw["cases"]):
        errors.append("reference.cases에 객체가 아닌 항목이 있습니다.")
    if not all(isinstance(case_id, str) for case_id in selected_ids):
        errors.append("selected case ID는 문자열이어야 합니다.")
        return errors
    if not selected_ids:
        errors.append("선택된 case가 하나 이상이어야 합니다.")
        return errors
    selected_count = suite_meta.get("selected_case_count")
    if selected_count != len(selected_ids):
        errors.append("suite.selected_case_count가 실제 case 수와 다릅니다.")
    if suite_meta.get("total_case_count") != len(suite.cases):
        errors.append("suite.total_case_count가 현재 suite와 다릅니다.")
    suite_by_id = {case.id: case for case in suite.cases}
    if len(set(selected_ids)) != len(selected_ids):
        errors.append("selected case ID가 중복됩니다.")
    if any(case_id not in suite_by_id for case_id in selected_ids):
        errors.append("selected case ID 중 현재 suite에 없는 값이 있습니다.")
        return errors
    selected_cases = tuple(suite_by_id[case_id] for case_id in selected_ids)

    reference = _validate_endpoint_run(
        reference_raw, suite, selected_ids, "reference", errors
    )
    candidate = _validate_endpoint_run(
        candidate_raw, suite, selected_ids, "candidate", errors
    )
    checked_at = _checked_at(report.get("checked_at"), [])
    if reference is None or candidate is None or checked_at is None:
        return errors
    reference_ids = [case.get("id") for case in reference["cases"]]
    candidate_ids = [case.get("id") for case in candidate["cases"]]
    if reference_ids != selected_ids or candidate_ids != selected_ids:
        return errors
    if reference.get("endpoint") == candidate.get("endpoint"):
        errors.append("reference와 candidate endpoint는 서로 달라야 합니다.")
    expected = build_parity_report(
        suite=suite,
        selected_cases=selected_cases,
        reference=reference,
        candidate=candidate,
        checked_at=checked_at,
    )
    if report.get("complete") is not expected["complete"]:
        errors.append("complete가 선택된 case 수와 일치하지 않습니다.")
    if report.get("passed") is not expected["passed"]:
        errors.append("passed가 임계값 재계산 결과와 다릅니다.")
    summary = report.get("summary")
    if not isinstance(summary, dict):
        errors.append("summary가 객체가 아닙니다.")
    else:
        for name, expected_value in expected["summary"].items():
            if not _close(summary.get(name), expected_value):
                errors.append(f"summary.{name}이 재계산 결과와 다릅니다.")
    return errors


def validate_report(
    report: dict[str, Any],
    recipes: dict[str, Recipe],
    suites: dict[str, EvalSuite],
) -> list[str]:
    kind = report.get("kind")
    if kind == "kanana-garden-model-check":
        return validate_model_check(report, recipes)
    if kind == "kanana-garden-runtime-parity":
        return validate_parity(report, suites)
    if kind == "kanana-garden-device-check":
        return validate_device_check(report)
    if kind == "kanana-garden-pi5-baseline":
        return validate_pi5_baseline(report, recipes)
    return [f"지원하지 않는 report kind: {kind}"]


def validate_report_path(
    path: Path,
    recipes: dict[str, Recipe],
    suites: dict[str, EvalSuite],
) -> list[str]:
    return validate_report(load_report(path), recipes, suites)
