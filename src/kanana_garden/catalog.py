"""Build a deterministic recipe catalog from current validated evidence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from .eval_suite import EvalSuite
from .recipe import Recipe, RecipeError
from .report_validation import load_report, validate_report


TRUST_LABELS = {
    "schema-only": "스키마만 검증",
    "model-smoke-passed": "실모델 스모크 통과",
    "pi5-baseline-passed": "Pi 5 기준선 통과",
    "pi5-reboot-reproduced": "Pi 5 재부팅 재현",
}


def load_validated_evidence(
    reports_dir: Path,
    recipes: dict[str, Recipe],
    suites: dict[str, EvalSuite],
) -> list[tuple[Path, dict[str, Any]]]:
    if not reports_dir.exists():
        return []
    if not reports_dir.is_dir():
        raise RecipeError(f"{reports_dir}가 디렉터리가 아닙니다.")
    evidence: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(reports_dir.glob("*.json")):
        report = load_report(path)
        errors = validate_report(report, recipes, suites)
        if errors:
            detail = "\n".join(f"- {error}" for error in errors)
            raise RecipeError(f"{path} 리포트가 유효하지 않습니다:\n{detail}")
        evidence.append((path, report))
    return evidence


def _report_names(
    items: Iterable[tuple[Path, dict[str, Any]]],
) -> list[str]:
    return sorted(path.name for path, _ in items)


def _reboot_reproduced(
    baseline_items: Iterable[tuple[Path, dict[str, Any]]],
) -> bool:
    boots_by_device: dict[str, set[str]] = {}
    for _, report in baseline_items:
        device = report["device_before"]
        boots_by_device.setdefault(device["device_id_sha256"], set()).add(
            device["boot_id_sha256"]
        )
    return any(len(boot_ids) >= 2 for boot_ids in boots_by_device.values())


def build_catalog(
    recipes: Iterable[Recipe],
    evidence: list[tuple[Path, dict[str, Any]]],
) -> dict[str, Any]:
    recipe_list = sorted(recipes, key=lambda recipe: recipe.slug)
    passed_model_checks = [
        item
        for item in evidence
        if item[1].get("kind") == "kanana-garden-model-check"
        and item[1].get("passed") is True
    ]
    passed_baselines = [
        item
        for item in evidence
        if item[1].get("kind") == "kanana-garden-pi5-baseline"
        and item[1].get("passed") is True
    ]
    passed_parity = [
        item
        for item in evidence
        if item[1].get("kind") == "kanana-garden-runtime-parity"
        and item[1].get("passed") is True
    ]
    ready_devices = [
        item
        for item in evidence
        if item[1].get("kind") == "kanana-garden-device-check"
        and item[1].get("ready") is True
    ]

    catalog_recipes: list[dict[str, Any]] = []
    for recipe in recipe_list:
        recipe_model_checks = [
            item
            for item in passed_model_checks
            if item[1]["recipe"]["slug"] == recipe.slug
        ]
        recipe_baselines = [
            item
            for item in passed_baselines
            if any(
                stored_recipe.get("slug") == recipe.slug
                for stored_recipe in item[1]["recipes"]
            )
        ]
        reboot_reproduced = _reboot_reproduced(recipe_baselines)
        if reboot_reproduced:
            trust_level = "pi5-reboot-reproduced"
        elif recipe_baselines:
            trust_level = "pi5-baseline-passed"
        elif recipe_model_checks:
            trust_level = "model-smoke-passed"
        else:
            trust_level = "schema-only"
        catalog_recipes.append(
            {
                "slug": recipe.slug,
                "title": recipe.title,
                "description": recipe.description,
                "model": recipe.model,
                "tags": list(recipe.tags),
                "trust_level": trust_level,
                "trust_label": TRUST_LABELS[trust_level],
                "evidence": {
                    "model_checks": _report_names(recipe_model_checks),
                    "pi5_baselines": _report_names(recipe_baselines),
                    "reboot_reproduced": reboot_reproduced,
                },
            }
        )

    baseline_devices: dict[str, set[str]] = {}
    for _, report in passed_baselines:
        device = report["device_before"]
        baseline_devices.setdefault(device["device_id_sha256"], set()).add(
            device["boot_id_sha256"]
        )
    return {
        "schema_version": 1,
        "powered_by": "Kanana",
        "recipe_count": len(catalog_recipes),
        "recipes": catalog_recipes,
        "evidence_summary": {
            "valid_report_count": len(evidence),
            "ready_device_report_count": len(ready_devices),
            "passed_model_check_count": len(passed_model_checks),
            "passed_pi5_baseline_count": len(passed_baselines),
            "reboot_reproduced_device_count": sum(
                len(boot_ids) >= 2
                for boot_ids in baseline_devices.values()
            ),
            "passed_parity_report_count": len(passed_parity),
        },
    }


def render_catalog_json(catalog: dict[str, Any]) -> str:
    return json.dumps(catalog, ensure_ascii=False, indent=2) + "\n"


def _markdown_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def render_catalog_markdown(catalog: dict[str, Any]) -> str:
    summary = catalog["evidence_summary"]
    lines = [
        "# Kanana Garden 레시피 카탈로그",
        "",
        "**Powered by Kanana**",
        "",
        "이 문서는 현재 recipe와 `reports/*.json`을 재검산해 자동 생성합니다.",
        "증빙이 없는 recipe는 품질이나 Raspberry Pi 동작이 확인된 것으로",
        "간주하지 않습니다.",
        "",
        "## 현재 증빙",
        "",
        f"- 레시피: {catalog['recipe_count']}개",
        f"- 유효한 실행 리포트: {summary['valid_report_count']}개",
        f"- 실모델 스모크 통과: {summary['passed_model_check_count']}건",
        f"- Pi 5 기준선 통과: {summary['passed_pi5_baseline_count']}건",
        (
            "- Pi 5 재부팅 재현 장치: "
            f"{summary['reboot_reproduced_device_count']}대"
        ),
        f"- 런타임 패리티 통과: {summary['passed_parity_report_count']}건",
        "",
        "## 레시피",
        "",
        "| 레시피 | 해결하는 문제 | 태그 | 검증 수준 |",
        "|---|---|---|---|",
    ]
    for recipe in catalog["recipes"]:
        lines.append(
            "| "
            f"`{_markdown_cell(recipe['slug'])}` | "
            f"{_markdown_cell(recipe['description'])} | "
            f"{_markdown_cell(', '.join(recipe['tags']))} | "
            f"{_markdown_cell(recipe['trust_label'])} |"
        )
    lines.extend(
        [
            "",
            "## 검증 수준",
            "",
            "- **스키마만 검증**: JSON 계약만 통과했으며 실모델 결과는 없습니다.",
            "- **실모델 스모크 통과**: 현재 recipe의 대표 기대 문자열을 통과했습니다.",
            "- **Pi 5 기준선 통과**: 한 boot에서 반복 품질·성능·열 기준선을 통과했습니다.",
            "- **Pi 5 재부팅 재현**: 같은 장치의 서로 다른 두 boot 기준선이 통과했습니다.",
            "",
            "문자열 기반 스모크와 내부 정합성 검사는 의미 품질이나 실행 출처를",
            "암호학적으로 보증하지 않습니다.",
            "",
        ]
    )
    return "\n".join(lines)
