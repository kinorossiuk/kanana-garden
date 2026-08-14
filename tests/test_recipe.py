import json
import tempfile
import unittest
from pathlib import Path

from kanana_garden.recipe import (
    Recipe,
    RecipeError,
    get_builtin_recipe,
    iter_builtin_recipes,
    validate_mapping,
    validate_unique_slugs,
)


def valid_mapping() -> dict:
    return {
        "schema_version": 1,
        "slug": "test-recipe",
        "title": "테스트",
        "description": "테스트 레시피입니다.",
        "model": "kakaocorp/kanana-2-1.3b-instruct",
        "system_prompt": "정확하게 답하세요.",
        "prompt_template": "요청: {input}",
        "generation": {
            "temperature": 0.2,
            "top_p": 0.9,
            "max_tokens": 100,
        },
        "tags": ["test"],
        "examples": [{"input": "안녕", "expected_contains": "안녕"}],
    }


class RecipeTests(unittest.TestCase):
    def test_builtin_recipes_are_valid_and_unique(self) -> None:
        recipes = list(iter_builtin_recipes())
        self.assertGreaterEqual(len(recipes), 3)
        self.assertEqual(validate_unique_slugs(recipes), [])

    def test_render_preserves_input(self) -> None:
        recipe = Recipe.from_mapping(valid_mapping())
        messages = recipe.render("줄 1\n줄 2")
        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(messages[1]["content"], "요청: 줄 1\n줄 2")

    def test_rejects_unknown_placeholder_and_fields(self) -> None:
        data = valid_mapping()
        data["prompt_template"] = "{input} {name}"
        data["surprise"] = True
        errors = validate_mapping(data)
        self.assertTrue(any("자리표시자" in error for error in errors))
        self.assertTrue(any("알 수 없는 필드" in error for error in errors))

    def test_reports_multiple_generation_errors(self) -> None:
        data = valid_mapping()
        data["generation"] = {
            "temperature": 3,
            "top_p": 0,
            "max_tokens": False,
        }
        errors = validate_mapping(data)
        self.assertEqual(len([error for error in errors if "generation." in error]), 3)

    def test_load_path_gives_json_location(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "broken.json"
            path.write_text('{"slug":', encoding="utf-8")
            with self.assertRaisesRegex(RecipeError, r"line 1, column"):
                Recipe.from_path(path)

    def test_mapping_round_trip(self) -> None:
        recipe = Recipe.from_mapping(valid_mapping())
        encoded = json.dumps(recipe.to_mapping(), ensure_ascii=False)
        restored = Recipe.from_mapping(json.loads(encoded))
        self.assertEqual(recipe, restored)

    def test_get_unknown_recipe_lists_choices(self) -> None:
        with self.assertRaisesRegex(RecipeError, "사용 가능"):
            get_builtin_recipe("does-not-exist")


if __name__ == "__main__":
    unittest.main()

