import unittest
from datetime import datetime, timezone

from kanana_garden.recipe import Recipe
from kanana_garden.verification import (
    build_report,
    recipe_digest,
    sanitized_endpoint,
)


def recipe() -> Recipe:
    return Recipe.from_mapping(
        {
            "schema_version": 1,
            "slug": "proof-recipe",
            "title": "증빙",
            "description": "검증 리포트를 테스트합니다.",
            "model": "kakaocorp/kanana-2-1.3b-instruct",
            "system_prompt": "정확히 답하세요.",
            "prompt_template": "{input}",
            "generation": {
                "temperature": 0,
                "top_p": 1,
                "max_tokens": 10,
            },
            "tags": ["test"],
            "examples": [{"input": "입력"}],
        }
    )


class VerificationTests(unittest.TestCase):
    def test_digest_is_stable_and_sensitive_to_recipe(self) -> None:
        first = recipe()
        self.assertEqual(recipe_digest(first), recipe_digest(first))
        changed = first.to_mapping()
        changed["title"] = "변경"
        self.assertNotEqual(recipe_digest(first), recipe_digest(Recipe.from_mapping(changed)))

    def test_endpoint_drops_credentials_query_and_fragment(self) -> None:
        self.assertEqual(
            sanitized_endpoint(
                "https://user:password@[2001:db8::1]:8443/v1/"
                "?token=secret#fragment"
            ),
            "https://[2001:db8::1]:8443/v1",
        )

    def test_report_requires_every_case_to_pass(self) -> None:
        report = build_report(
            recipe=recipe(),
            endpoint="https://host.example/v1",
            requested_model="kakaocorp/kanana-2-1.3b-instruct",
            exposed_models=["kakaocorp/kanana-2-1.3b-instruct"],
            cases=[
                {"index": 1, "passed": True},
                {"index": 2, "passed": False},
            ],
            checked_at=datetime(2026, 7, 31, 1, 2, 3, tzinfo=timezone.utc),
        )
        self.assertFalse(report["passed"])
        self.assertEqual(report["checked_at"], "2026-07-31T01:02:03Z")
        self.assertEqual(report["powered_by"], "Kanana")


if __name__ == "__main__":
    unittest.main()
