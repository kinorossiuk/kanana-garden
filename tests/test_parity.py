import unittest
from dataclasses import replace
from datetime import datetime, timezone
from kanana_garden.client import ChatResult
from kanana_garden.eval_suite import get_builtin_suite
from kanana_garden.parity import build_parity_report, run_endpoint


MODEL = "kakaocorp/kanana-2-1.3b-instruct"


class FakeClient:
    def __init__(self, contents: list[str]) -> None:
        self.contents = iter(contents)

    def list_models(self) -> list[str]:
        return [MODEL]

    def chat(self, **_: object) -> ChatResult:
        return ChatResult(
            content=next(self.contents),
            model=MODEL,
            usage={"completion_tokens": 10},
        )


class ParityTests(unittest.TestCase):
    def test_run_endpoint_applies_assertions(self) -> None:
        suite = get_builtin_suite("pi5-parity-ko-v1")
        cases = suite.select_cases(["extract-contact", "extract-location"])
        run = run_endpoint(
            client=FakeClient(
                [
                    "02-1234-5678",
                    "시민센터 3층 배움실",
                ]
            ),
            endpoint="http://reference.local/v1?secret=value",
            model=MODEL,
            cases=cases,
            generation=suite.generation,
        )
        self.assertEqual(run["pass_count"], 2)
        self.assertEqual(run["pass_rate"], 1)
        self.assertEqual(run["endpoint"], "http://reference.local/v1")
        self.assertIsNotNone(run["cases"][0]["tokens_per_second"])

    def test_relative_rate_only_counts_reference_passes(self) -> None:
        suite = get_builtin_suite("pi5-parity-ko-v1")
        cases = suite.cases[:3]
        reference = {
            "pass_rate": 2 / 3,
            "cases": [
                {"id": cases[0].id, "passed": True},
                {"id": cases[1].id, "passed": True},
                {"id": cases[2].id, "passed": False},
            ],
        }
        candidate = {
            "pass_rate": 2 / 3,
            "cases": [
                {"id": cases[0].id, "passed": True},
                {"id": cases[1].id, "passed": False},
                {"id": cases[2].id, "passed": True},
            ],
        }
        report = build_parity_report(
            suite=replace(suite, cases=cases),
            selected_cases=cases,
            reference=reference,
            candidate=candidate,
            checked_at=datetime(2026, 7, 31, tzinfo=timezone.utc),
        )
        self.assertEqual(report["summary"]["candidate_relative_pass_rate"], 0.5)
        self.assertFalse(report["passed"])
        self.assertTrue(report["complete"])
        self.assertEqual(report["checked_at"], "2026-07-31T00:00:00Z")

    def test_partial_run_cannot_claim_full_pass(self) -> None:
        suite = get_builtin_suite("pi5-parity-ko-v1")
        cases = suite.cases[:1]
        endpoint = {
            "pass_rate": 1,
            "cases": [{"id": cases[0].id, "passed": True}],
        }
        report = build_parity_report(
            suite=suite,
            selected_cases=cases,
            reference=endpoint,
            candidate=endpoint,
        )
        self.assertFalse(report["complete"])
        self.assertIsNone(report["passed"])


if __name__ == "__main__":
    unittest.main()
