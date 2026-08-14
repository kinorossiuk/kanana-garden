"""Recipe loading, validation, discovery, and rendering."""

from __future__ import annotations

import json
import re
import string
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any, Iterable


SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MODEL_PATTERN = re.compile(r"^kakaocorp/[Kk]anana-[A-Za-z0-9._-]+$")
ALLOWED_GENERATION_KEYS = {"temperature", "top_p", "max_tokens"}
REQUIRED_FIELDS = {
    "schema_version",
    "slug",
    "title",
    "description",
    "model",
    "system_prompt",
    "prompt_template",
    "generation",
    "tags",
    "examples",
}


class RecipeError(ValueError):
    """Raised when a recipe does not match the public recipe contract."""


@dataclass(frozen=True)
class Recipe:
    schema_version: int
    slug: str
    title: str
    description: str
    model: str
    system_prompt: str
    prompt_template: str
    generation: dict[str, int | float]
    tags: tuple[str, ...]
    examples: tuple[dict[str, str], ...]

    @classmethod
    def from_mapping(cls, data: dict[str, Any], source: str = "<memory>") -> "Recipe":
        errors = validate_mapping(data)
        if errors:
            detail = "\n".join(f"- {item}" for item in errors)
            raise RecipeError(f"{source} 레시피가 유효하지 않습니다:\n{detail}")

        return cls(
            schema_version=data["schema_version"],
            slug=data["slug"],
            title=data["title"],
            description=data["description"],
            model=data["model"],
            system_prompt=data["system_prompt"],
            prompt_template=data["prompt_template"],
            generation=dict(data["generation"]),
            tags=tuple(data["tags"]),
            examples=tuple(dict(example) for example in data["examples"]),
        )

    @classmethod
    def from_path(cls, path: str | Path) -> "Recipe":
        recipe_path = Path(path)
        try:
            data = json.loads(recipe_path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise RecipeError(f"{recipe_path} 파일을 읽을 수 없습니다: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise RecipeError(
                f"{recipe_path} JSON 문법 오류: {exc.msg} "
                f"(line {exc.lineno}, column {exc.colno})"
            ) from exc
        if not isinstance(data, dict):
            raise RecipeError(f"{recipe_path} 최상위 값은 JSON 객체여야 합니다.")
        return cls.from_mapping(data, str(recipe_path))

    def render(self, user_input: str) -> list[dict[str, str]]:
        if not user_input.strip():
            raise RecipeError("입력은 비어 있을 수 없습니다.")
        return [
            {"role": "system", "content": self.system_prompt},
            {
                "role": "user",
                "content": self.prompt_template.format(input=user_input),
            },
        ]

    def to_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "slug": self.slug,
            "title": self.title,
            "description": self.description,
            "model": self.model,
            "system_prompt": self.system_prompt,
            "prompt_template": self.prompt_template,
            "generation": dict(self.generation),
            "tags": list(self.tags),
            "examples": [dict(example) for example in self.examples],
        }


def _is_nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_mapping(data: dict[str, Any]) -> list[str]:
    """Return every validation error so contributors can fix a recipe once."""
    errors: list[str] = []
    missing = REQUIRED_FIELDS - data.keys()
    extra = data.keys() - REQUIRED_FIELDS
    if missing:
        errors.append(f"필수 필드 누락: {', '.join(sorted(missing))}")
    if extra:
        errors.append(f"알 수 없는 필드: {', '.join(sorted(extra))}")

    if data.get("schema_version") != 1:
        errors.append("schema_version은 1이어야 합니다.")

    slug = data.get("slug")
    if not isinstance(slug, str) or not SLUG_PATTERN.fullmatch(slug):
        errors.append("slug는 소문자·숫자·하이픈으로 작성해야 합니다.")

    for field in ("title", "description", "system_prompt", "prompt_template"):
        if not _is_nonempty_string(data.get(field)):
            errors.append(f"{field}은 비어 있지 않은 문자열이어야 합니다.")

    model = data.get("model")
    if not isinstance(model, str) or not MODEL_PATTERN.fullmatch(model):
        errors.append("model은 kakaocorp/kanana-* 형식의 모델 ID여야 합니다.")

    template = data.get("prompt_template")
    if isinstance(template, str):
        try:
            placeholders = {
                field_name
                for _, field_name, _, _ in string.Formatter().parse(template)
                if field_name is not None
            }
        except ValueError as exc:
            errors.append(f"prompt_template 포맷 문법 오류: {exc}")
        else:
            if placeholders != {"input"}:
                errors.append("prompt_template에는 {input} 자리표시자 하나만 사용해야 합니다.")

    generation = data.get("generation")
    if not isinstance(generation, dict):
        errors.append("generation은 JSON 객체여야 합니다.")
    else:
        unknown = generation.keys() - ALLOWED_GENERATION_KEYS
        if unknown:
            errors.append(f"generation의 알 수 없는 필드: {', '.join(sorted(unknown))}")
        temperature = generation.get("temperature")
        if not isinstance(temperature, (int, float)) or isinstance(temperature, bool):
            errors.append("generation.temperature는 숫자여야 합니다.")
        elif not 0 <= temperature <= 2:
            errors.append("generation.temperature는 0 이상 2 이하여야 합니다.")
        top_p = generation.get("top_p", 1.0)
        if not isinstance(top_p, (int, float)) or isinstance(top_p, bool):
            errors.append("generation.top_p는 숫자여야 합니다.")
        elif not 0 < top_p <= 1:
            errors.append("generation.top_p는 0 초과 1 이하여야 합니다.")
        max_tokens = generation.get("max_tokens")
        if not isinstance(max_tokens, int) or isinstance(max_tokens, bool):
            errors.append("generation.max_tokens는 정수여야 합니다.")
        elif not 1 <= max_tokens <= 32768:
            errors.append("generation.max_tokens는 1 이상 32768 이하여야 합니다.")

    tags = data.get("tags")
    if (
        not isinstance(tags, list)
        or not tags
        or any(not _is_nonempty_string(tag) for tag in tags)
    ):
        errors.append("tags는 비어 있지 않은 문자열 배열이어야 합니다.")
    elif len(set(tags)) != len(tags):
        errors.append("tags에 중복 값이 있습니다.")

    examples = data.get("examples")
    if not isinstance(examples, list) or not examples:
        errors.append("examples는 하나 이상의 예제를 포함해야 합니다.")
    else:
        for index, example in enumerate(examples):
            if not isinstance(example, dict):
                errors.append(f"examples[{index}]는 JSON 객체여야 합니다.")
                continue
            allowed = {"input", "expected_contains"}
            unknown = example.keys() - allowed
            if unknown:
                errors.append(
                    f"examples[{index}]의 알 수 없는 필드: {', '.join(sorted(unknown))}"
                )
            if not _is_nonempty_string(example.get("input")):
                errors.append(f"examples[{index}].input은 비어 있을 수 없습니다.")
            if "expected_contains" in example and not _is_nonempty_string(
                example["expected_contains"]
            ):
                errors.append(
                    f"examples[{index}].expected_contains는 비어 있을 수 없습니다."
                )

    return errors


def iter_builtin_recipes() -> Iterable[Recipe]:
    recipe_dir = resources.files("kanana_garden.recipes")
    for entry in sorted(recipe_dir.iterdir(), key=lambda item: item.name):
        if entry.name.endswith(".json"):
            with entry.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            yield Recipe.from_mapping(data, f"builtin:{entry.name}")


def get_builtin_recipe(slug: str) -> Recipe:
    for recipe in iter_builtin_recipes():
        if recipe.slug == slug:
            return recipe
    available = ", ".join(recipe.slug for recipe in iter_builtin_recipes())
    raise RecipeError(f"'{slug}' 레시피가 없습니다. 사용 가능: {available}")


def validate_unique_slugs(recipes: Iterable[Recipe]) -> list[str]:
    seen: set[str] = set()
    duplicates: list[str] = []
    for recipe in recipes:
        if recipe.slug in seen:
            duplicates.append(recipe.slug)
        seen.add(recipe.slug)
    return duplicates

