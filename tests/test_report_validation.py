import copy
import json
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from kanana_garden.eval_suite import evaluate_assertions, get_builtin_suite
from kanana_garden.parity import build_parity_report
from kanana_garden.recipe import get_builtin_recipe
from kanana_garden.report_validation import (
    load_assets,
    validate_model_check,
    validate_parity,
    validate_report_path,
)
from kanana_garden.verification import build_report


MODEL = "kakaocorp/kanana-2-1.3b-instruct"
CHECKED_AT = datetime(2026, 7, 31, 1, 2, 3, tzinfo=timezone.utc)


def model_check_report() -> dict:
    recipe = get_builtin_recipe("meeting-action-items-ko")
    expected = recipe.examples[0]["expected_contains"]
    return build_report(
        recipe=recipe,
        endpoint="http://pi.local:8000/v1",
        requested_model=MODEL,
        exposed_models=[MODEL],
        cases=[
            {
                "index": 1,
                "passed": True,
                "expected_contains": expected,
                "response_model": MODEL,
                "model_matched": True,
                "content": f"{expected} 표입니다.",
                "usage": {"completion_tokens": 4},
                "latency_seconds": 2.0,
                "tokens_per_second": 2.0,
            }
        ],
        checked_at=CHECKED_AT,
    )


def parity_report() -> tuple[dict, object]:
    base_suite = get_builtin_suite("runtime-stability-ko-v1")
    case = next(case for case in base_suite.cases if case.id == "extract-contact")
    suite = replace(base_suite, cases=(case,))
    content = "02-1234-5678"
    assertions = evaluate_assertions(case, content)
    stored_case = {
        "id": case.id,
        "category": case.category,
        "passed": True,
        "assertions_passed": True,
        "assertions": assertions["assertions"],
        "response_model": MODEL,
        "model_matched": True,
        "content": content,
        "usage": {"completion_tokens": 1},
        "latency_seconds": 1.0,
        "tokens_per_second": 1.0,
    }
    endpoint = {
        "endpoint": "http://host.local:8000/v1",
        "requested_model": MODEL,
        "exposed_models": [MODEL],
        "pass_count": 1,
        "case_count": 1,
        "pass_rate": 1.0,
        "cases": [stored_case],
    }
    report = build_parity_report(
        suite=suite,
        selected_cases=suite.cases,
        reference=copy.deepcopy(endpoint),
        candidate={
            **copy.deepcopy(endpoint),
            "endpoint": "http://pi.local:8080/v1",
        },
        checked_at=CHECKED_AT,
    )
    return report, suite


class ReportValidationTests(unittest.TestCase):
    def test_valid_model_check_is_recomputed(self) -> None:
        recipes, _ = load_assets()
        self.assertEqual(validate_model_check(model_check_report(), recipes), [])

    def test_tampered_model_content_and_digest_are_rejected(self) -> None:
        recipes, _ = load_assets()
        report = model_check_report()
        report["recipe"]["sha256"] = "sha256:tampered"
        report["cases"][0]["content"] = "관련 없는 응답"
        errors = validate_model_check(report, recipes)
        self.assertTrue(any("SHA-256" in error for error in errors))
        self.assertTrue(any("cases[0].passed" in error for error in errors))
        self.assertTrue(any(error.startswith("passed") for error in errors))

    def test_model_check_requires_safe_endpoint(self) -> None:
        recipes, _ = load_assets()
        report = model_check_report()
        report["endpoint"] = "https://user:secret@host.example/v1"
        errors = validate_model_check(report, recipes)
        self.assertTrue(any("endpoint" in error for error in errors))

    def test_valid_parity_report_is_recomputed(self) -> None:
        report, suite = parity_report()
        self.assertEqual(validate_parity(report, {suite.slug: suite}), [])

    def test_tampered_parity_summary_and_output_are_rejected(self) -> None:
        report, suite = parity_report()
        report["candidate"]["cases"][0]["content"] = "잘못된 번호"
        report["summary"]["candidate_pass_rate"] = 1
        errors = validate_parity(report, {suite.slug: suite})
        self.assertTrue(any("candidate.cases[0].passed" in error for error in errors))
        self.assertTrue(any("summary.candidate_pass_rate" in error for error in errors))
        self.assertTrue(any(error.startswith("passed") for error in errors))

    def test_malformed_parity_case_list_is_rejected_without_crashing(self) -> None:
        report, suite = parity_report()
        report["candidate"]["cases"] = []
        errors = validate_parity(report, {suite.slug: suite})
        self.assertTrue(any("candidate.cases ID" in error for error in errors))

    def test_parity_requires_distinct_safe_endpoints_and_current_category(self) -> None:
        report, suite = parity_report()
        report["reference"]["endpoint"] = "http://[invalid"
        report["candidate"]["endpoint"] = "http://[invalid"
        report["candidate"]["cases"][0]["category"] = "tampered"
        errors = validate_parity(report, {suite.slug: suite})
        self.assertTrue(any("reference.endpoint" in error for error in errors))
        self.assertTrue(any("candidate.endpoint" in error for error in errors))
        self.assertTrue(any("category" in error for error in errors))
        self.assertTrue(any("서로 달라야" in error for error in errors))

    def test_report_path_dispatches_by_kind(self) -> None:
        recipes, suites = load_assets()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            path.write_text(
                json.dumps(model_check_report(), ensure_ascii=False),
                encoding="utf-8",
            )
            self.assertEqual(
                validate_report_path(path, recipes, suites),
                [],
            )


if __name__ == "__main__":
    unittest.main()
