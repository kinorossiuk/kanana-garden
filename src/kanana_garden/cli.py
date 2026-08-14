"""Command-line interface for discovering and running Kanana recipes."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Sequence

from . import __version__
from .client import KananaAPIError, KananaClient
from .recipe import (
    Recipe,
    RecipeError,
    get_builtin_recipe,
    iter_builtin_recipes,
    validate_unique_slugs,
)
from .verification import build_report


DEFAULT_MODEL = "kakaocorp/kanana-2-1.3b-instruct"
DEFAULT_BASE_URL = "http://localhost:8000/v1"


def _add_connection_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--base-url",
        default=os.getenv("KANANA_BASE_URL", DEFAULT_BASE_URL),
        help="OpenAI 호환 API의 /v1 주소 (기본값: %(default)s)",
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("KANANA_API_KEY"),
        help="API 토큰 (기본값: KANANA_API_KEY 환경 변수)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help="HTTP 제한 시간(초) (기본값: %(default)s)",
    )


def _add_input_options(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--input", help="레시피에 전달할 텍스트")
    group.add_argument(
        "--input-file",
        type=Path,
        help="입력 파일 경로. 표준 입력은 '-'",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kanana-garden",
        description="Powered by Kanana — 카나나 활용 레시피를 검증하고 실행합니다.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="내장 레시피 목록")
    list_parser.add_argument("--json", action="store_true", help="JSON으로 출력")

    show_parser = subparsers.add_parser("show", help="레시피 상세 보기")
    show_parser.add_argument("recipe", help="내장 slug 또는 JSON 파일")
    show_parser.add_argument("--json", action="store_true", help="JSON으로 출력")

    catalog_parser = subparsers.add_parser(
        "catalog",
        help="recipe와 실행 증빙으로 신뢰 수준 카탈로그 생성",
    )
    catalog_parser.add_argument(
        "--reports-dir",
        type=Path,
        default=Path("reports"),
        help="검증 리포트 디렉터리 (기본값: %(default)s)",
    )
    catalog_parser.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="출력 형식 (기본값: %(default)s)",
    )
    catalog_output = catalog_parser.add_mutually_exclusive_group()
    catalog_output.add_argument("--output", type=Path, help="결과 저장 경로")
    catalog_output.add_argument(
        "--check",
        type=Path,
        help="생성 결과와 기존 파일이 같은지 검사",
    )

    validate_parser = subparsers.add_parser("validate", help="레시피 유효성 검사")
    validate_parser.add_argument("paths", type=Path, nargs="*")

    suite_validate_parser = subparsers.add_parser(
        "suite-validate",
        help="패리티 평가 스위트 유효성 검사",
    )
    suite_validate_parser.add_argument("suites", nargs="+", help="내장 slug 또는 JSON 파일")

    report_validate_parser = subparsers.add_parser(
        "report-validate",
        help="저장된 실행 증빙을 현재 asset으로 재검산",
    )
    report_validate_parser.add_argument(
        "reports",
        type=Path,
        nargs="*",
        help="생략하면 reports/*.json을 검사",
    )
    report_validate_parser.add_argument(
        "--asset",
        type=Path,
        action="append",
        default=[],
        help="외부 recipe 또는 eval suite JSON",
    )

    render_parser = subparsers.add_parser("render", help="최종 메시지 미리 보기")
    render_parser.add_argument("recipe", help="내장 slug 또는 JSON 파일")
    _add_input_options(render_parser)

    run_parser = subparsers.add_parser("run", help="카나나 서버에서 레시피 실행")
    run_parser.add_argument("recipe", help="내장 slug 또는 JSON 파일")
    _add_input_options(run_parser)
    _add_connection_options(run_parser)
    run_parser.add_argument("--model", help="레시피의 모델 ID 덮어쓰기")
    run_parser.add_argument("--temperature", type=float, help="temperature 덮어쓰기")
    run_parser.add_argument("--max-tokens", type=int, help="max_tokens 덮어쓰기")
    run_parser.add_argument("--json", action="store_true", help="응답 메타데이터 포함")

    vehicle_parser = subparsers.add_parser(
        "vehicle-command",
        help="한국어 차량 명령을 실행하지 않고 안전한 action JSON으로 해석",
    )
    _add_input_options(vehicle_parser)
    _add_connection_options(vehicle_parser)
    vehicle_parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help="명령 해석 모델 ID (기본값: %(default)s)",
    )

    check_parser = subparsers.add_parser("check", help="대표 예제를 실제 모델로 검사")
    check_parser.add_argument("recipe", help="내장 slug 또는 JSON 파일")
    _add_connection_options(check_parser)
    check_parser.add_argument("--model", help="레시피의 모델 ID 덮어쓰기")
    check_parser.add_argument("--json", action="store_true", help="검증 리포트를 JSON으로 출력")
    check_parser.add_argument("--output", type=Path, help="검증 리포트를 저장할 JSON 파일")

    parity_parser = subparsers.add_parser(
        "parity",
        help="공식·온디바이스 런타임의 한국어 출력 정합성 비교",
    )
    parity_parser.add_argument("suite", help="내장 slug 또는 평가 스위트 JSON")
    parity_parser.add_argument("--reference-url", required=True)
    parity_parser.add_argument("--candidate-url", required=True)
    parity_parser.add_argument(
        "--reference-api-key",
        default=os.getenv("KANANA_REFERENCE_API_KEY"),
    )
    parity_parser.add_argument(
        "--candidate-api-key",
        default=os.getenv("KANANA_CANDIDATE_API_KEY"),
    )
    parity_parser.add_argument("--reference-model")
    parity_parser.add_argument("--candidate-model")
    parity_parser.add_argument("--case-id", action="append", dest="case_ids")
    parity_parser.add_argument("--limit", type=int)
    parity_parser.add_argument("--timeout", type=float, default=300.0)
    parity_parser.add_argument("--output", type=Path)
    parity_parser.add_argument("--json", action="store_true")

    doctor_parser = subparsers.add_parser("doctor", help="서버와 모델 연결 확인")
    _add_connection_options(doctor_parser)
    doctor_parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help="확인할 모델 ID (기본값: %(default)s)",
    )

    baseline_parser = subparsers.add_parser(
        "server-baseline",
        help="5600G 서버의 반복 품질·성능 기준선 수집",
    )
    _add_connection_options(baseline_parser)
    baseline_parser.set_defaults(timeout=600.0)
    baseline_parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help="측정할 모델 ID (기본값: %(default)s)",
    )
    baseline_parser.add_argument(
        "--repetitions",
        type=int,
        default=3,
        help="각 예제 반복 횟수, 3~20 (기본값: %(default)s)",
    )
    baseline_parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="기준선 JSON 저장 경로",
    )
    baseline_parser.add_argument("--json", action="store_true", help="JSON으로 출력")

    compare_parser = subparsers.add_parser(
        "server-compare",
        help="서로 다른 5600G 서버 세션의 안정성 비교",
    )
    compare_parser.add_argument("first", type=Path, help="첫 baseline JSON")
    compare_parser.add_argument("second", type=Path, help="서버 재시작 후 baseline JSON")
    compare_parser.add_argument("--json", action="store_true", help="JSON으로 출력")

    uis_doctor_parser = subparsers.add_parser(
        "uis7862s-doctor",
        help="ADB로 UIS7862S 테스트 장비 준비 상태 확인",
    )
    uis_doctor_parser.add_argument(
        "--serial",
        default=os.getenv("ANDROID_SERIAL"),
        help="ADB serial (기본값: ANDROID_SERIAL 또는 연결된 단일 장치)",
    )
    uis_doctor_parser.add_argument("--adb-path", help="adb 실행 파일 경로")
    uis_doctor_parser.add_argument(
        "--timeout", type=float, default=30.0, help="ADB 명령 제한 시간(초)"
    )
    uis_doctor_parser.add_argument("--json", action="store_true", help="JSON으로 출력")

    uis_capture_parser = subparsers.add_parser(
        "uis7862s-capture",
        help="UIS7862S 재현 로그와 시스템 상태를 분석 번들로 수집",
    )
    uis_capture_parser.add_argument(
        "--serial",
        default=os.getenv("ANDROID_SERIAL"),
        help="ADB serial (기본값: ANDROID_SERIAL 또는 연결된 단일 장치)",
    )
    uis_capture_parser.add_argument("--adb-path", help="adb 실행 파일 경로")
    uis_capture_parser.add_argument(
        "--timeout", type=float, default=30.0, help="ADB 명령 제한 시간(초)"
    )
    uis_capture_parser.add_argument(
        "--output",
        type=Path,
        help="새 캡처 디렉터리 (기본값: reports/uis7862s/<UTC 시각>-<label>)",
    )
    uis_capture_parser.add_argument("--label", help="재현 ID 또는 짧은 설명")
    uis_capture_parser.add_argument("--package", help="집중 분석할 Android package")
    uis_capture_parser.add_argument(
        "--ota-version", help="테스트 중인 OTA 버전 식별자"
    )
    uis_capture_parser.add_argument(
        "--bugreport",
        action="store_true",
        help="민감 정보가 많은 전체 Android bugreport도 수집",
    )
    uis_capture_parser.add_argument(
        "--no-screenshot", action="store_true", help="화면 캡처 제외"
    )
    uis_capture_parser.add_argument("--json", action="store_true", help="manifest 출력")

    ota_download_parser = subparsers.add_parser(
        "ota-download",
        help="검증 해시가 고정된 UIS7862S OTA를 로컬 보관소에 다운로드",
    )
    ota_download_parser.add_argument("--version", required=True, help="OTA 버전 식별자")
    ota_download_parser.add_argument("--url", required=True, help="OTA 다운로드 URL")
    ota_download_parser.add_argument(
        "--sha256", required=True, help="공급자가 제공하거나 별도 확인한 SHA-256"
    )
    ota_download_parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("var/ota"),
        help="OTA 보관소 (기본값: %(default)s)",
    )
    ota_download_parser.add_argument("--filename", help="저장할 파일명")
    ota_download_parser.add_argument(
        "--allow-http", action="store_true", help="HTTPS가 아닌 HTTP URL 허용"
    )
    ota_download_parser.add_argument(
        "--timeout", type=float, default=120.0, help="네트워크 읽기 제한 시간(초)"
    )
    ota_download_parser.add_argument("--json", action="store_true", help="manifest 출력")

    ota_verify_parser = subparsers.add_parser(
        "ota-verify", help="보관된 OTA 파일 크기와 SHA-256 재검증"
    )
    ota_verify_parser.add_argument(
        "path", type=Path, help="OTA 파일 또는 같은 디렉터리의 manifest.json"
    )
    ota_verify_parser.add_argument("--json", action="store_true", help="JSON으로 출력")

    serve_parser = subparsers.add_parser(
        "serve-local",
        help="공식 Transformers 모델을 로컬 OpenAI 호환 API로 서빙",
    )
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8000)
    serve_parser.add_argument("--model", default=DEFAULT_MODEL)
    serve_parser.add_argument(
        "--revision",
        default="c10f59f16af7e3e3a9b2801f528a98c1e4ff6171",
        help="검토한 Hugging Face 커밋 해시",
    )
    serve_parser.add_argument("--max-input-tokens", type=int, default=2048)
    serve_parser.add_argument("--max-output-tokens", type=int, default=512)
    serve_parser.add_argument("--threads", type=int, default=4)
    serve_parser.add_argument(
        "--dtype",
        choices=("auto", "float32", "bfloat16"),
        default="auto",
        help="모델 연산 dtype; 5600G CPU 기준선은 float32 권장",
    )
    serve_parser.add_argument(
        "--api-key",
        default=os.getenv("KANANA_API_KEY"),
        help="외부 바인딩 시 필수",
    )

    new_parser = subparsers.add_parser("new", help="새 레시피 골격 생성")
    new_parser.add_argument("slug")
    new_parser.add_argument("--output", type=Path, required=True)
    new_parser.add_argument("--force", action="store_true", help="기존 파일 덮어쓰기")

    return parser


def _read_input(args: argparse.Namespace) -> str:
    if args.input is not None:
        value = args.input
    elif str(args.input_file) == "-":
        value = sys.stdin.read()
    else:
        try:
            value = args.input_file.read_text(encoding="utf-8")
        except OSError as exc:
            raise RecipeError(f"{args.input_file} 입력 파일을 읽을 수 없습니다: {exc}") from exc
    if not value.strip():
        raise RecipeError("입력은 비어 있을 수 없습니다.")
    return value


def _resolve_recipe(value: str) -> Recipe:
    path = Path(value)
    if path.is_file():
        return Recipe.from_path(path)
    if path.suffix == ".json" or "/" in value or "\\" in value:
        raise RecipeError(f"{path} 레시피 파일이 없습니다.")
    return get_builtin_recipe(value)


def _resolve_suite(value: str):
    from .eval_suite import EvalSuite, get_builtin_suite

    path = Path(value)
    if path.is_file():
        return EvalSuite.from_path(path)
    if path.suffix == ".json" or "/" in value or "\\" in value:
        raise RecipeError(f"{path} 평가 스위트 파일이 없습니다.")
    return get_builtin_suite(value)


def _cmd_list(args: argparse.Namespace) -> int:
    recipes = list(iter_builtin_recipes())
    if args.json:
        print(
            json.dumps(
                [
                    {
                        "slug": recipe.slug,
                        "title": recipe.title,
                        "description": recipe.description,
                        "tags": list(recipe.tags),
                    }
                    for recipe in recipes
                ],
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    print("Powered by Kanana\n")
    for recipe in recipes:
        print(f"{recipe.slug:26} {recipe.title}")
        print(f"{'':26} {recipe.description}")
    return 0


def _cmd_show(args: argparse.Namespace) -> int:
    recipe = _resolve_recipe(args.recipe)
    if args.json:
        print(json.dumps(recipe.to_mapping(), ensure_ascii=False, indent=2))
    else:
        print(f"{recipe.title} ({recipe.slug})")
        print(f"{recipe.description}\n")
        print(f"모델: {recipe.model}")
        print(f"태그: {', '.join(recipe.tags)}")
        print(f"생성 설정: {json.dumps(recipe.generation, ensure_ascii=False)}")
        print(f"\n시스템 프롬프트:\n{recipe.system_prompt}")
        print(f"\n사용자 프롬프트:\n{recipe.prompt_template}")
    return 0


def _cmd_catalog(args: argparse.Namespace) -> int:
    from .catalog import (
        build_catalog,
        load_validated_evidence,
        render_catalog_json,
        render_catalog_markdown,
    )
    from .report_validation import load_assets

    recipes, suites = load_assets()
    evidence = load_validated_evidence(args.reports_dir, recipes, suites)
    catalog = build_catalog(recipes.values(), evidence)
    rendered = (
        render_catalog_json(catalog)
        if args.format == "json"
        else render_catalog_markdown(catalog)
    )
    if args.check:
        try:
            current = args.check.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"FAIL {args.check}: {exc}", file=sys.stderr)
            return 1
        if current != rendered:
            print(
                f"FAIL {args.check}가 현재 recipe·report와 다릅니다. "
                f"--output {args.check}로 갱신하세요.",
                file=sys.stderr,
            )
            return 1
        print(f"OK  {args.check}")
        return 0
    if args.output:
        try:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8")
        except OSError as exc:
            raise RecipeError(
                f"{args.output} 카탈로그를 쓸 수 없습니다: {exc}"
            ) from exc
        print(f"생성: {args.output}")
        return 0
    print(rendered, end="")
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    if args.paths:
        recipes = [Recipe.from_path(path) for path in args.paths]
    else:
        recipes = list(iter_builtin_recipes())
    duplicates = validate_unique_slugs(recipes)
    if duplicates:
        raise RecipeError(f"중복 slug: {', '.join(sorted(set(duplicates)))}")
    for recipe in recipes:
        print(f"OK  {recipe.slug}")
    print(f"\n{len(recipes)}개 레시피가 유효합니다.")
    return 0


def _cmd_suite_validate(args: argparse.Namespace) -> int:
    for value in args.suites:
        suite = _resolve_suite(value)
        print(f"OK  {suite.slug} ({len(suite.cases)} cases, {suite.digest()})")
    print(f"\n{len(args.suites)}개 평가 스위트가 유효합니다.")
    return 0


def _cmd_report_validate(args: argparse.Namespace) -> int:
    from .report_validation import load_assets, validate_report_path

    recipes, suites = load_assets(args.asset)
    report_paths = args.reports or sorted(Path("reports").glob("*.json"))
    if not report_paths:
        print("검증할 JSON 리포트가 없습니다.")
        return 0
    failures = 0
    for path in report_paths:
        try:
            errors = validate_report_path(path, recipes, suites)
        except RecipeError as exc:
            errors = [str(exc)]
        if errors:
            failures += 1
            print(f"FAIL {path}", file=sys.stderr)
            for error in errors:
                print(f"  - {error}", file=sys.stderr)
        else:
            print(f"OK  {path}")
    if failures:
        print(
            f"\n{len(report_paths)}개 중 {failures}개 리포트가 유효하지 않습니다.",
            file=sys.stderr,
        )
        return 1
    print(f"\n{len(report_paths)}개 리포트가 현재 asset과 일치합니다.")
    return 0


def _cmd_render(args: argparse.Namespace) -> int:
    recipe = _resolve_recipe(args.recipe)
    messages = recipe.render(_read_input(args))
    print(json.dumps(messages, ensure_ascii=False, indent=2))
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    recipe = _resolve_recipe(args.recipe)
    model = args.model or recipe.model
    generation = dict(recipe.generation)
    if args.temperature is not None:
        if not 0 <= args.temperature <= 2:
            raise RecipeError("--temperature는 0 이상 2 이하여야 합니다.")
        generation["temperature"] = args.temperature
    if args.max_tokens is not None:
        if not 1 <= args.max_tokens <= 32768:
            raise RecipeError("--max-tokens는 1 이상 32768 이하여야 합니다.")
        generation["max_tokens"] = args.max_tokens

    client = KananaClient(args.base_url, args.api_key, args.timeout)
    result = client.chat(
        model=model,
        messages=recipe.render(_read_input(args)),
        generation=generation,
    )
    if args.json:
        print(
            json.dumps(
                {
                    "recipe": recipe.slug,
                    "model": result.model,
                    "content": result.content,
                    "usage": result.usage,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(result.content)
    return 0


def _cmd_vehicle_command(args: argparse.Namespace) -> int:
    from .vehicle_control import parse_vehicle_action

    recipe = get_builtin_recipe("vehicle-control-ko")
    client = KananaClient(args.base_url, args.api_key, args.timeout)
    exposed_models = client.list_models()
    if args.model not in exposed_models:
        raise RecipeError(
            f"요청 모델 '{args.model}'이 서버 모델 목록에 없습니다: "
            f"{', '.join(exposed_models)}"
        )
    result = client.chat(
        model=args.model,
        messages=recipe.render(_read_input(args)),
        generation=recipe.generation,
    )
    action = parse_vehicle_action(result.content)
    print(json.dumps(action, ensure_ascii=False, indent=2))
    return 0


def _cmd_check(args: argparse.Namespace) -> int:
    recipe = _resolve_recipe(args.recipe)
    model = args.model or recipe.model
    client = KananaClient(args.base_url, args.api_key, args.timeout)
    exposed_models = client.list_models()
    if model not in exposed_models:
        raise RecipeError(
            f"요청 모델 '{model}'이 서버 모델 목록에 없습니다: "
            f"{', '.join(exposed_models)}"
        )

    cases: list[dict[str, object]] = []
    for index, example in enumerate(recipe.examples, start=1):
        started = time.monotonic()
        result = client.chat(
            model=model,
            messages=recipe.render(example["input"]),
            generation=recipe.generation,
        )
        latency_seconds = time.monotonic() - started
        expected = example.get("expected_contains")
        content_passed = expected is None or expected in result.content
        model_passed = result.model == model
        action_contract_valid: bool | None = None
        parsed_action: dict[str, object] | None = None
        if recipe.slug == "vehicle-control-ko":
            from .vehicle_control import parse_vehicle_action

            try:
                parsed_action = parse_vehicle_action(result.content)
            except RecipeError:
                action_contract_valid = False
            else:
                action_contract_valid = True
        completion_tokens = result.usage.get("completion_tokens")
        tokens_per_second = (
            completion_tokens / latency_seconds
            if completion_tokens is not None and latency_seconds > 0
            else None
        )
        case: dict[str, object] = {
                "index": index,
                "passed": (
                    content_passed
                    and model_passed
                    and action_contract_valid is not False
                ),
                "expected_contains": expected,
                "response_model": result.model,
                "model_matched": model_passed,
                "content": result.content,
                "usage": result.usage,
                "latency_seconds": round(latency_seconds, 3),
                "tokens_per_second": (
                    round(tokens_per_second, 3)
                    if tokens_per_second is not None
                    else None
                ),
        }
        if action_contract_valid is not None:
            case["action_contract_valid"] = action_contract_valid
            case["parsed_action"] = parsed_action
        cases.append(case)

    report = build_report(
        recipe=recipe,
        endpoint=args.base_url,
        requested_model=model,
        exposed_models=exposed_models,
        cases=cases,
    )
    rendered_report = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        try:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered_report, encoding="utf-8")
        except OSError as exc:
            raise RecipeError(f"{args.output} 리포트를 쓸 수 없습니다: {exc}") from exc

    if args.json:
        print(rendered_report, end="")
    else:
        for case in cases:
            status = "PASS" if case["passed"] else "FAIL"
            performance = f"{case['latency_seconds']:.3f}s"
            if case["tokens_per_second"] is not None:
                performance += f", {case['tokens_per_second']:.3f} tok/s"
            print(f"{status} 예제 {case['index']} ({performance})")
            if not case["model_matched"]:
                print(
                    f"     응답 모델 불일치: {case['response_model']}",
                    file=sys.stderr,
                )
            if not case["passed"] and case["expected_contains"] is not None:
                print(
                    f"     기대 문자열: {case['expected_contains']}",
                    file=sys.stderr,
                )
        if args.output:
            print(f"리포트: {args.output}")

    if not report["passed"]:
        if not args.json:
            failures = sum(not case["passed"] for case in cases)
            print(
                f"\n{len(cases)}개 중 {failures}개 예제가 실패했습니다.",
                file=sys.stderr,
            )
        return 1
    if not args.json:
        print(f"\n{len(cases)}개 예제가 통과했습니다. Powered by Kanana")
    return 0


def _cmd_parity(args: argparse.Namespace) -> int:
    from .parity import build_parity_report, run_endpoint, write_report

    if args.reference_url.rstrip("/") == args.candidate_url.rstrip("/"):
        raise RecipeError("reference와 candidate URL은 서로 달라야 합니다.")
    if args.timeout <= 0:
        raise RecipeError("--timeout은 0보다 커야 합니다.")

    suite = _resolve_suite(args.suite)
    selected_cases = suite.select_cases(args.case_ids, args.limit)
    reference_model = args.reference_model or suite.model
    candidate_model = args.candidate_model or suite.model

    reference = run_endpoint(
        client=KananaClient(
            args.reference_url,
            args.reference_api_key,
            args.timeout,
        ),
        endpoint=args.reference_url,
        model=reference_model,
        cases=selected_cases,
        generation=suite.generation,
    )
    candidate = run_endpoint(
        client=KananaClient(
            args.candidate_url,
            args.candidate_api_key,
            args.timeout,
        ),
        endpoint=args.candidate_url,
        model=candidate_model,
        cases=selected_cases,
        generation=suite.generation,
    )
    report = build_parity_report(
        suite=suite,
        selected_cases=selected_cases,
        reference=reference,
        candidate=candidate,
    )
    if args.output:
        write_report(report, args.output)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"스위트: {suite.title} ({len(selected_cases)} cases)")
        print(f"기준 런타임: {reference['pass_rate']:.1%}")
        print(f"후보 런타임: {candidate['pass_rate']:.1%}")
        print(
            "기준 통과 케이스 대비 후보: "
            f"{report['summary']['candidate_relative_pass_rate']:.1%}"
        )
        print(f"통과/실패 일치율: {report['summary']['agreement_rate']:.1%}\n")
        candidate_by_id = {case["id"]: case for case in candidate["cases"]}
        for reference_case in reference["cases"]:
            candidate_case = candidate_by_id[reference_case["id"]]
            reference_status = "PASS" if reference_case["passed"] else "FAIL"
            candidate_status = "PASS" if candidate_case["passed"] else "FAIL"
            print(
                f"{reference_case['id']:28} "
                f"ref={reference_status:4} candidate={candidate_status:4}"
            )
        if args.output:
            print(f"\n리포트: {args.output}")
        if report["passed"] is None:
            print("\nPARTIAL — 전체 스위트 합격 증거로 사용할 수 없습니다.")
        else:
            print("\nPASS" if report["passed"] else "\nFAIL")
    return 0 if report["passed"] is not False else 1


def _cmd_doctor(args: argparse.Namespace) -> int:
    client = KananaClient(args.base_url, args.api_key, args.timeout)
    models = client.list_models()
    print(f"OK  API 연결: {args.base_url}")
    print(f"OK  노출 모델: {', '.join(models)}")
    if args.model not in models:
        print(
            f"FAIL 요청 모델 '{args.model}'이 서버 모델 목록에 없습니다.",
            file=sys.stderr,
        )
        return 1
    print(f"OK  기본 모델: {args.model}")
    print("\nPowered by Kanana")
    return 0


def _cmd_server_baseline(args: argparse.Namespace) -> int:
    from .baseline import run_server_baseline, write_server_baseline_report

    client = KananaClient(args.base_url, args.api_key, args.timeout)
    report = run_server_baseline(
        client=client,
        endpoint=args.base_url,
        model=args.model,
        recipes=iter_builtin_recipes(),
        repetitions=args.repetitions,
    )
    write_server_baseline_report(report, args.output)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        summary = report["summary"]
        status = "PASS" if report["passed"] else "FAIL"
        print(
            f"{status} 5600G 서버 기준선: "
            f"{summary['passed_sample_count']}/{summary['sample_count']} samples"
        )
        print(
            "지연 시간 중앙값/p95: "
            f"{summary['median_latency_seconds']}s / "
            f"{summary['p95_latency_seconds']}s"
        )
        print(
            f"생성 속도 중앙값: {summary['median_tokens_per_second']} tok/s"
        )
        runtime = report["runtime"]
        print(f"서버 세션: {runtime['session_id']}")
        print(f"모델 revision/dtype: {runtime['revision']} / {runtime['dtype']}")
        print(f"리포트: {args.output}")
        print(
            f"재검산: kanana-garden report-validate {args.output}"
        )
    return 0 if report["passed"] else 1


def _cmd_server_compare(args: argparse.Namespace) -> int:
    from .stability import compare_server_baselines
    from .report_validation import load_assets, load_report

    recipes, _ = load_assets()
    comparison = compare_server_baselines(
        load_report(args.first),
        load_report(args.second),
        recipes,
    )
    if args.json:
        print(json.dumps(comparison, ensure_ascii=False, indent=2))
    else:
        status = "PASS" if comparison["passed"] else "FAIL"
        print(f"{status} 5600G 서버 재시작 안정성\n")
        for check in comparison["checks"]:
            check_status = "PASS" if check["passed"] else "FAIL"
            print(f"{check_status:4} {check['name']:26} {check['detail']}")
        delta = comparison["performance_delta"]

        def formatted(value: object, suffix: str) -> str:
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                return "측정 불가"
            return f"{value:+.3f}{suffix}"

        print("\n두 번째 실행의 변화:")
        print(
            "지연 중앙값: "
            f"{formatted(delta['median_latency_percent'], '%')}"
        )
        print(f"지연 p95: {formatted(delta['p95_latency_percent'], '%')}")
        print(
            "생성 속도 중앙값: "
            f"{formatted(delta['median_tokens_per_second_percent'], '%')}"
        )
    return 0 if comparison["passed"] else 1


def _cmd_uis7862s_doctor(args: argparse.Namespace) -> int:
    from .uis7862s import device_report

    report = device_report(
        serial=args.serial,
        adb_path=args.adb_path,
        timeout=args.timeout,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("UIS7862S Android 테스트 장비 사전 점검\n")
        for check in report["checks"]:
            if not check["required"] and not check["passed"]:
                status = "INFO"
            else:
                status = "PASS" if check["passed"] else "FAIL"
            print(f"{status:4} {check['name']:20} {check['detail']}")
        device = report["device"]
        print(
            f"\n장비: {device['manufacturer']} {device['model']} / "
            f"Android {device['android_release']} (SDK {device['sdk']})"
        )
        print(f"빌드: {device['build_fingerprint']}")
        print("\n권장 사항:")
        for recommendation in report["recommendations"]:
            print(f"- {recommendation}")
    return 0 if report["ready"] else 1


def _cmd_uis7862s_capture(args: argparse.Namespace) -> int:
    from .uis7862s import capture_diagnostics

    report = capture_diagnostics(
        output=args.output,
        label=args.label,
        package=args.package,
        ota_version=args.ota_version,
        serial=args.serial,
        adb_path=args.adb_path,
        timeout=args.timeout,
        include_screenshot=not args.no_screenshot,
        include_bugreport=args.bugreport,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        status = "PASS" if report["complete"] else "PARTIAL"
        analysis = report["analysis"]
        print(f"{status} UIS7862S 진단 캡처: {report['capture_dir']}")
        print(
            "후보 이벤트: "
            f"crash={analysis['candidate_counts']['crash']}, "
            f"anr={analysis['candidate_counts']['anr']}, "
            f"memory={analysis['candidate_counts']['memory']}, "
            f"watchdog={analysis['candidate_counts']['watchdog']}, "
            f"thermal={analysis['candidate_counts']['thermal']}"
        )
        if report["critical_failures"]:
            print(
                "필수 수집 실패: " + ", ".join(report["critical_failures"]),
                file=sys.stderr,
            )
        print(f"분석 시작점: {Path(report['capture_dir']) / 'analysis.json'}")
    return 0 if report["complete"] else 1


def _cmd_ota_download(args: argparse.Namespace) -> int:
    from .ota import download_ota

    report = download_ota(
        version=args.version,
        url=args.url,
        sha256=args.sha256,
        output_dir=args.output_dir,
        filename=args.filename,
        allow_http=args.allow_http,
        timeout=args.timeout,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"OK  OTA {report['version']}: {report['path']}")
        print(f"SHA-256: {report['sha256']}")
        print(f"상태: {report['state']} (자동 설치하지 않음)")
        print(f"재검증: kanana-garden ota-verify {report['manifest']}")
    return 0


def _cmd_ota_verify(args: argparse.Namespace) -> int:
    from .ota import verify_ota

    report = verify_ota(args.path)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        status = "PASS" if report["passed"] else "FAIL"
        print(f"{status} OTA {report['version']}: {report['path']}")
        print(f"SHA-256: {report['actual_sha256']}")
        print(f"크기: {report['actual_bytes']} bytes")
    return 0 if report["passed"] else 1


def _cmd_serve_local(args: argparse.Namespace) -> int:
    if not 1 <= args.port <= 65535:
        raise ValueError("--port는 1 이상 65535 이하여야 합니다.")
    if not 128 <= args.max_input_tokens <= 32768:
        raise ValueError("--max-input-tokens는 128 이상 32768 이하여야 합니다.")
    if not 1 <= args.max_output_tokens <= 4096:
        raise ValueError("--max-output-tokens는 1 이상 4096 이하여야 합니다.")
    if not 1 <= args.threads <= 64:
        raise ValueError("--threads는 1 이상 64 이하여야 합니다.")
    from .local_server import serve

    serve(
        host=args.host,
        port=args.port,
        model_id=args.model,
        revision=args.revision,
        max_input_tokens=args.max_input_tokens,
        max_output_tokens=args.max_output_tokens,
        threads=args.threads,
        dtype=args.dtype,
        api_key=args.api_key,
    )
    return 0


def _cmd_new(args: argparse.Namespace) -> int:
    data = {
        "schema_version": 1,
        "slug": args.slug,
        "title": "새 카나나 레시피",
        "description": "이 레시피가 해결하는 문제를 한 문장으로 설명합니다.",
        "model": DEFAULT_MODEL,
        "system_prompt": "당신은 정확하고 유용한 한국어 AI 도우미입니다.",
        "prompt_template": "다음 요청을 처리하세요.\n\n{input}",
        "generation": {
            "temperature": 0.2,
            "top_p": 0.9,
            "max_tokens": 1024,
        },
        "tags": ["korean"],
        "examples": [
            {
                "input": "실제로 실행해 볼 대표 입력을 적습니다.",
                "expected_contains": "응답에 반드시 포함되어야 할 짧은 표현",
            }
        ],
    }
    recipe = Recipe.from_mapping(data, "새 레시피")
    if args.output.exists() and not args.force:
        raise RecipeError(
            f"{args.output} 파일이 이미 있습니다. 덮어쓰려면 --force를 사용하세요."
        )
    try:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(recipe.to_mapping(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        raise RecipeError(f"{args.output} 파일을 쓸 수 없습니다: {exc}") from exc
    print(f"생성: {args.output}")
    print(f"검사: kanana-garden validate {args.output}")
    return 0


COMMANDS = {
    "list": _cmd_list,
    "show": _cmd_show,
    "catalog": _cmd_catalog,
    "validate": _cmd_validate,
    "suite-validate": _cmd_suite_validate,
    "report-validate": _cmd_report_validate,
    "render": _cmd_render,
    "run": _cmd_run,
    "vehicle-command": _cmd_vehicle_command,
    "check": _cmd_check,
    "parity": _cmd_parity,
    "doctor": _cmd_doctor,
    "server-baseline": _cmd_server_baseline,
    "server-compare": _cmd_server_compare,
    "uis7862s-doctor": _cmd_uis7862s_doctor,
    "uis7862s-capture": _cmd_uis7862s_capture,
    "ota-download": _cmd_ota_download,
    "ota-verify": _cmd_ota_verify,
    "serve-local": _cmd_serve_local,
    "new": _cmd_new,
}


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return COMMANDS[args.command](args)
    except (RecipeError, KananaAPIError, RuntimeError, ValueError) as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 2
