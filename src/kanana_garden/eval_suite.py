"""Deterministic, grounded evaluation suites for runtime parity checks."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any, Iterable

from .recipe import MODEL_PATTERN, RecipeError


SUITE_FIELDS = {
    "schema_version",
    "slug",
    "title",
    "description",
    "model",
    "generation",
    "thresholds",
    "cases",
}
CASE_FIELDS = {"id", "category", "messages", "assertions"}
ASSERTION_FIELDS = {"contains", "not_contains", "regex"}


@dataclass(frozen=True)
class EvalCase:
    id: str
    category: str
    messages: tuple[dict[str, str], ...]
    assertions: dict[str, tuple[str, ...]]

    def to_mapping(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "category": self.category,
            "messages": [dict(message) for message in self.messages],
            "assertions": {
                name: list(values) for name, values in self.assertions.items()
            },
        }


@dataclass(frozen=True)
class EvalSuite:
    schema_version: int
    slug: str
    title: str
    description: str
    model: str
    generation: dict[str, int | float]
    thresholds: dict[str, float]
    cases: tuple[EvalCase, ...]

    @classmethod
    def from_mapping(cls, data: dict[str, Any], source: str = "<memory>") -> "EvalSuite":
        errors = validate_suite_mapping(data)
        if errors:
            detail = "\n".join(f"- {error}" for error in errors)
            raise RecipeError(f"{source} 평가 스위트가 유효하지 않습니다:\n{detail}")
        return cls(
            schema_version=data["schema_version"],
            slug=data["slug"],
            title=data["title"],
            description=data["description"],
            model=data["model"],
            generation=dict(data["generation"]),
            thresholds=dict(data["thresholds"]),
            cases=tuple(
                EvalCase(
                    id=case["id"],
                    category=case["category"],
                    messages=tuple(dict(message) for message in case["messages"]),
                    assertions={
                        name: tuple(values)
                        for name, values in case["assertions"].items()
                    },
                )
                for case in data["cases"]
            ),
        )

    @classmethod
    def from_path(cls, path: str | Path) -> "EvalSuite":
        suite_path = Path(path)
        try:
            data = json.loads(suite_path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise RecipeError(f"{suite_path} 파일을 읽을 수 없습니다: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise RecipeError(
                f"{suite_path} JSON 문법 오류: {exc.msg} "
                f"(line {exc.lineno}, column {exc.colno})"
            ) from exc
        if not isinstance(data, dict):
            raise RecipeError(f"{suite_path} 최상위 값은 JSON 객체여야 합니다.")
        return cls.from_mapping(data, str(suite_path))

    def to_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "slug": self.slug,
            "title": self.title,
            "description": self.description,
            "model": self.model,
            "generation": dict(self.generation),
            "thresholds": dict(self.thresholds),
            "cases": [case.to_mapping() for case in self.cases],
        }

    def digest(self) -> str:
        canonical = json.dumps(
            self.to_mapping(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return f"sha256:{hashlib.sha256(canonical).hexdigest()}"

    def select_cases(
        self, case_ids: Iterable[str] | None = None, limit: int | None = None
    ) -> tuple[EvalCase, ...]:
        selected = self.cases
        if case_ids:
            requested = list(case_ids)
            known = {case.id for case in self.cases}
            unknown = set(requested) - known
            if unknown:
                raise RecipeError(f"알 수 없는 case ID: {', '.join(sorted(unknown))}")
            wanted = set(requested)
            selected = tuple(case for case in self.cases if case.id in wanted)
        if limit is not None:
            if limit < 1:
                raise RecipeError("--limit은 1 이상이어야 합니다.")
            selected = selected[:limit]
        return selected


def _string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _string_list(value: Any) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(_string(item) for item in value)
    )


def validate_suite_mapping(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    missing = SUITE_FIELDS - data.keys()
    extra = data.keys() - SUITE_FIELDS
    if missing:
        errors.append(f"필수 필드 누락: {', '.join(sorted(missing))}")
    if extra:
        errors.append(f"알 수 없는 필드: {', '.join(sorted(extra))}")
    if data.get("schema_version") != 1:
        errors.append("schema_version은 1이어야 합니다.")
    for field in ("slug", "title", "description"):
        if not _string(data.get(field)):
            errors.append(f"{field}은 비어 있지 않은 문자열이어야 합니다.")
    model = data.get("model")
    if not isinstance(model, str) or not MODEL_PATTERN.fullmatch(model):
        errors.append("model은 kakaocorp/kanana-* 형식이어야 합니다.")

    generation = data.get("generation")
    if not isinstance(generation, dict):
        errors.append("generation은 JSON 객체여야 합니다.")
    else:
        if generation.keys() != {"temperature", "top_p", "max_tokens"}:
            errors.append(
                "generation에는 temperature, top_p, max_tokens만 있어야 합니다."
            )
        if generation.get("temperature") != 0:
            errors.append("패리티 스위트의 temperature는 0이어야 합니다.")
        top_p = generation.get("top_p")
        if not isinstance(top_p, (int, float)) or isinstance(top_p, bool):
            errors.append("generation.top_p는 숫자여야 합니다.")
        elif not 0 < top_p <= 1:
            errors.append("generation.top_p는 0 초과 1 이하여야 합니다.")
        max_tokens = generation.get("max_tokens")
        if not isinstance(max_tokens, int) or isinstance(max_tokens, bool):
            errors.append("generation.max_tokens는 정수여야 합니다.")
        elif not 1 <= max_tokens <= 2048:
            errors.append("generation.max_tokens는 1 이상 2048 이하여야 합니다.")

    thresholds = data.get("thresholds")
    threshold_fields = {"reference_pass_rate", "candidate_relative_pass_rate"}
    if not isinstance(thresholds, dict) or thresholds.keys() != threshold_fields:
        errors.append(
            "thresholds에는 reference_pass_rate와 "
            "candidate_relative_pass_rate가 있어야 합니다."
        )
    else:
        for name, value in thresholds.items():
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not 0 <= value <= 1
            ):
                errors.append(f"thresholds.{name}은 0 이상 1 이하 숫자여야 합니다.")

    cases = data.get("cases")
    if not isinstance(cases, list) or not cases:
        errors.append("cases는 하나 이상의 케이스를 포함해야 합니다.")
        return errors
    ids: list[str] = []
    for index, case in enumerate(cases):
        prefix = f"cases[{index}]"
        if not isinstance(case, dict):
            errors.append(f"{prefix}는 JSON 객체여야 합니다.")
            continue
        missing_case = CASE_FIELDS - case.keys()
        extra_case = case.keys() - CASE_FIELDS
        if missing_case:
            errors.append(f"{prefix} 필수 필드 누락: {', '.join(sorted(missing_case))}")
        if extra_case:
            errors.append(f"{prefix} 알 수 없는 필드: {', '.join(sorted(extra_case))}")
        case_id = case.get("id")
        if not _string(case_id) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", case_id):
            errors.append(f"{prefix}.id는 소문자·숫자·하이픈 형식이어야 합니다.")
        else:
            ids.append(case_id)
        if not _string(case.get("category")):
            errors.append(f"{prefix}.category는 비어 있을 수 없습니다.")

        messages = case.get("messages")
        if not isinstance(messages, list) or not messages:
            errors.append(f"{prefix}.messages는 비어 있지 않은 배열이어야 합니다.")
        else:
            for message_index, message in enumerate(messages):
                message_prefix = f"{prefix}.messages[{message_index}]"
                if not isinstance(message, dict) or message.keys() != {"role", "content"}:
                    errors.append(
                        f"{message_prefix}에는 role과 content만 있어야 합니다."
                    )
                    continue
                if message.get("role") not in {"system", "user", "assistant"}:
                    errors.append(f"{message_prefix}.role이 올바르지 않습니다.")
                if not _string(message.get("content")):
                    errors.append(f"{message_prefix}.content가 비어 있습니다.")

        assertions = case.get("assertions")
        if not isinstance(assertions, dict) or not assertions:
            errors.append(f"{prefix}.assertions는 비어 있지 않은 객체여야 합니다.")
        else:
            unknown_assertions = assertions.keys() - ASSERTION_FIELDS
            if unknown_assertions:
                errors.append(
                    f"{prefix}.assertions 알 수 없는 필드: "
                    f"{', '.join(sorted(unknown_assertions))}"
                )
            for name, values in assertions.items():
                if name in ASSERTION_FIELDS and not _string_list(values):
                    errors.append(f"{prefix}.assertions.{name}은 문자열 배열이어야 합니다.")
                if name == "regex" and isinstance(values, list):
                    for pattern in values:
                        if not isinstance(pattern, str):
                            continue
                        try:
                            re.compile(pattern)
                        except re.error as exc:
                            errors.append(
                                f"{prefix}.assertions.regex 문법 오류: {exc}"
                            )
    duplicates = {case_id for case_id in ids if ids.count(case_id) > 1}
    if duplicates:
        errors.append(f"중복 case ID: {', '.join(sorted(duplicates))}")
    return errors


def evaluate_assertions(case: EvalCase, content: str) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for value in case.assertions.get("contains", ()):
        results.append(
            {"type": "contains", "value": value, "passed": value in content}
        )
    for value in case.assertions.get("not_contains", ()):
        results.append(
            {"type": "not_contains", "value": value, "passed": value not in content}
        )
    for value in case.assertions.get("regex", ()):
        results.append(
            {
                "type": "regex",
                "value": value,
                "passed": re.search(value, content) is not None,
            }
        )
    return {
        "passed": bool(results) and all(result["passed"] for result in results),
        "assertions": results,
    }


def iter_builtin_suites() -> Iterable[EvalSuite]:
    suite_dir = resources.files("kanana_garden.evals")
    for entry in sorted(suite_dir.iterdir(), key=lambda item: item.name):
        if entry.name.endswith(".json"):
            with entry.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            yield EvalSuite.from_mapping(data, f"builtin:{entry.name}")


def get_builtin_suite(slug: str) -> EvalSuite:
    suites = list(iter_builtin_suites())
    for suite in suites:
        if suite.slug == slug:
            return suite
    available = ", ".join(suite.slug for suite in suites)
    raise RecipeError(f"'{slug}' 평가 스위트가 없습니다. 사용 가능: {available}")
