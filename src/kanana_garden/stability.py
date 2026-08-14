"""Compare validated 5600G baselines from distinct server sessions."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .recipe import Recipe, RecipeError


def _percent_change(first: Any, second: Any) -> float | None:
    if (
        not isinstance(first, (int, float))
        or isinstance(first, bool)
        or not isinstance(second, (int, float))
        or isinstance(second, bool)
        or first == 0
    ):
        return None
    return round((float(second) - float(first)) / float(first) * 100, 3)


def compare_server_baselines(
    first: dict[str, Any],
    second: dict[str, Any],
    recipes: dict[str, Recipe],
    *,
    compared_at: datetime | None = None,
) -> dict[str, Any]:
    from .report_validation import validate_server_baseline

    validation_errors: list[str] = []
    for label, baseline in (("first", first), ("second", second)):
        validation_errors.extend(
            f"{label}.{error}"
            for error in validate_server_baseline(baseline, recipes)
        )
    if validation_errors:
        detail = "\n".join(f"- {error}" for error in validation_errors)
        raise RecipeError(f"비교할 baseline이 유효하지 않습니다:\n{detail}")

    first_runtime = first["runtime"]
    second_runtime = second["runtime"]
    first_recipes = [
        (recipe["slug"], recipe["sha256"]) for recipe in first["recipes"]
    ]
    second_recipes = [
        (recipe["slug"], recipe["sha256"]) for recipe in second["recipes"]
    ]
    checks = [
        {
            "name": "first_baseline_passed",
            "passed": first["passed"] is True,
            "detail": first["checked_at"],
        },
        {
            "name": "second_baseline_passed",
            "passed": second["passed"] is True,
            "detail": second["checked_at"],
        },
        {
            "name": "distinct_server_sessions",
            "passed": first_runtime["session_id"] != second_runtime["session_id"],
            "detail": (
                "different server session IDs"
                if first_runtime["session_id"] != second_runtime["session_id"]
                else "same server session ID"
            ),
        },
        {
            "name": "same_model",
            "passed": first["requested_model"] == second["requested_model"],
            "detail": first["requested_model"],
        },
        {
            "name": "same_revision",
            "passed": first_runtime["revision"] == second_runtime["revision"],
            "detail": first_runtime["revision"],
        },
        {
            "name": "same_dtype",
            "passed": first_runtime["dtype"] == second_runtime["dtype"],
            "detail": first_runtime["dtype"],
        },
        {
            "name": "same_recipe_revision",
            "passed": first_recipes == second_recipes,
            "detail": f"{len(first_recipes)} recipes",
        },
    ]
    first_summary = first["summary"]
    second_summary = second["summary"]
    timestamp = compared_at or datetime.now(timezone.utc)
    return {
        "schema_version": 1,
        "comparison": "kanana-garden-server-stability",
        "powered_by": "Kanana",
        "compared_at": timestamp.astimezone(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        "passed": all(check["passed"] for check in checks),
        "checks": checks,
        "first": {
            "checked_at": first["checked_at"],
            "session_id": first_runtime["session_id"],
            "endpoint": first["endpoint"],
        },
        "second": {
            "checked_at": second["checked_at"],
            "session_id": second_runtime["session_id"],
            "endpoint": second["endpoint"],
        },
        "performance_delta": {
            "median_latency_percent": _percent_change(
                first_summary["median_latency_seconds"],
                second_summary["median_latency_seconds"],
            ),
            "p95_latency_percent": _percent_change(
                first_summary["p95_latency_seconds"],
                second_summary["p95_latency_seconds"],
            ),
            "median_tokens_per_second_percent": _percent_change(
                first_summary["median_tokens_per_second"],
                second_summary["median_tokens_per_second"],
            ),
        },
    }
