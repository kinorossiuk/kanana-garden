"""Strict vehicle-control action contract for model output."""

from __future__ import annotations

import json
from typing import Any

from .recipe import RecipeError


ACTIONS = {
    "volume_up",
    "volume_down",
    "volume_set",
    "volume_mute",
    "volume_unmute",
    "navigation_start",
    "navigation_stop",
    "media_play",
    "media_pause",
    "media_next",
    "media_previous",
    "app_open",
    "unsupported",
}
CONFIDENCE_LEVELS = {"high", "medium", "low"}
APP_ALIASES = {"navigation", "music", "settings"}
NO_SLOT_ACTIONS = {
    "volume_up",
    "volume_down",
    "volume_mute",
    "volume_unmute",
    "navigation_stop",
    "media_pause",
    "media_next",
    "media_previous",
}
TOP_LEVEL_FIELDS = {
    "action",
    "slots",
    "confidence",
    "requires_confirmation",
}


def _short_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RecipeError(f"{name}은 비어 있지 않은 문자열이어야 합니다.")
    cleaned = value.strip()
    if len(cleaned) > 200:
        raise RecipeError(f"{name}은 200자 이하여야 합니다.")
    return cleaned


def parse_vehicle_action(content: str) -> dict[str, Any]:
    """Parse a model response without allowing executable free-form fields."""

    if not isinstance(content, str) or not content.strip():
        raise RecipeError("차량 제어 응답이 비어 있습니다.")
    try:
        value = json.loads(content)
    except json.JSONDecodeError as exc:
        raise RecipeError(
            "차량 제어 응답은 설명이나 코드 펜스가 없는 JSON 객체여야 합니다."
        ) from exc
    if not isinstance(value, dict):
        raise RecipeError("차량 제어 응답의 최상위 값은 JSON 객체여야 합니다.")
    unknown = value.keys() - TOP_LEVEL_FIELDS
    missing = TOP_LEVEL_FIELDS - value.keys()
    if unknown:
        raise RecipeError(f"허용하지 않는 차량 제어 필드: {', '.join(sorted(unknown))}")
    if missing:
        raise RecipeError(f"차량 제어 필드 누락: {', '.join(sorted(missing))}")

    action = value.get("action")
    if action not in ACTIONS:
        raise RecipeError(f"허용하지 않는 차량 제어 action: {action}")
    confidence = value.get("confidence")
    if confidence not in CONFIDENCE_LEVELS:
        raise RecipeError("confidence는 high, medium, low 중 하나여야 합니다.")
    if not isinstance(value.get("requires_confirmation"), bool):
        raise RecipeError("requires_confirmation은 bool이어야 합니다.")
    slots = value.get("slots")
    if not isinstance(slots, dict):
        raise RecipeError("slots는 JSON 객체여야 합니다.")

    cleaned_slots: dict[str, Any]
    if action in NO_SLOT_ACTIONS:
        if slots:
            raise RecipeError(f"{action} action에는 slots를 사용할 수 없습니다.")
        cleaned_slots = {}
    elif action == "volume_set":
        if set(slots) != {"level_percent"}:
            raise RecipeError("volume_set slots에는 level_percent만 필요합니다.")
        level = slots["level_percent"]
        if not isinstance(level, int) or isinstance(level, bool) or not 0 <= level <= 100:
            raise RecipeError("level_percent는 0 이상 100 이하 정수여야 합니다.")
        cleaned_slots = {"level_percent": level}
    elif action == "navigation_start":
        if set(slots) != {"destination"}:
            raise RecipeError("navigation_start slots에는 destination만 필요합니다.")
        cleaned_slots = {"destination": _short_text(slots["destination"], "destination")}
    elif action == "media_play":
        if set(slots) not in (set(), {"query"}):
            raise RecipeError("media_play slots에는 선택적으로 query만 사용할 수 있습니다.")
        cleaned_slots = (
            {"query": _short_text(slots["query"], "query")} if slots else {}
        )
    elif action == "app_open":
        if set(slots) != {"app"} or slots.get("app") not in APP_ALIASES:
            raise RecipeError(
                "app_open slots.app은 navigation, music, settings 중 하나여야 합니다."
            )
        cleaned_slots = {"app": slots["app"]}
    else:
        if set(slots) != {"reason"}:
            raise RecipeError("unsupported slots에는 reason만 필요합니다.")
        cleaned_slots = {"reason": _short_text(slots["reason"], "reason")}

    return {
        "action": action,
        "slots": cleaned_slots,
        "confidence": confidence,
        "requires_confirmation": value["requires_confirmation"],
    }
