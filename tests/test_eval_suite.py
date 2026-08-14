import copy
import unittest
from kanana_garden.eval_suite import (
    EvalSuite,
    evaluate_assertions,
    get_builtin_suite,
    iter_builtin_suites,
    validate_suite_mapping,
)
from kanana_garden.recipe import RecipeError


class EvalSuiteTests(unittest.TestCase):
    def test_builtin_pi_suite_is_valid_and_has_grounded_cases(self) -> None:
        suite = get_builtin_suite("pi5-parity-ko-v1")
        self.assertGreaterEqual(len(suite.cases), 30)
        self.assertEqual(len(list(iter_builtin_suites())), 1)
        self.assertEqual(len({case.id for case in suite.cases}), len(suite.cases))
        self.assertEqual(suite.generation["temperature"], 0)
        self.assertTrue(suite.digest().startswith("sha256:"))

    def test_assertions_cover_contains_not_contains_and_regex(self) -> None:
        suite = get_builtin_suite("pi5-parity-ko-v1")
        case = next(case for case in suite.cases if case.id == "format-json")
        result = evaluate_assertions(
            case,
            '{"담당자": "민지", "상태": "완료"}',
        )
        self.assertTrue(result["passed"])
        failed = evaluate_assertions(case, "```json\n{}\n```")
        self.assertFalse(failed["passed"])

    def test_select_cases_preserves_suite_order(self) -> None:
        suite = get_builtin_suite("pi5-parity-ko-v1")
        selected = suite.select_cases(["extract-amount", "extract-deadline"])
        self.assertEqual(
            [case.id for case in selected],
            ["extract-deadline", "extract-amount"],
        )

    def test_unknown_case_is_rejected(self) -> None:
        suite = get_builtin_suite("pi5-parity-ko-v1")
        with self.assertRaisesRegex(RecipeError, "알 수 없는 case ID"):
            suite.select_cases(["missing-case"])

    def test_duplicate_case_and_sampling_are_rejected(self) -> None:
        suite = get_builtin_suite("pi5-parity-ko-v1")
        mapping = suite.to_mapping()
        mapping["generation"]["temperature"] = 0.2
        mapping["cases"].append(copy.deepcopy(mapping["cases"][0]))
        errors = validate_suite_mapping(mapping)
        self.assertTrue(any("temperature" in error for error in errors))
        self.assertTrue(any("중복 case ID" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
