import tempfile
import unittest
from pathlib import Path

from kanana_garden.catalog import (
    build_catalog,
    load_validated_evidence,
    render_catalog_markdown,
)
from kanana_garden.recipe import RecipeError, iter_builtin_recipes
from kanana_garden.report_validation import load_assets


class CatalogTests(unittest.TestCase):
    def test_no_evidence_is_explicitly_schema_only(self) -> None:
        catalog = build_catalog(iter_builtin_recipes(), [])
        self.assertEqual(catalog["recipe_count"], 3)
        self.assertTrue(
            all(
                recipe["trust_level"] == "schema-only"
                for recipe in catalog["recipes"]
            )
        )
        self.assertEqual(catalog["evidence_summary"]["valid_report_count"], 0)
        rendered = render_catalog_markdown(catalog)
        self.assertIn("스키마만 검증", rendered)
        self.assertIn("실모델 결과는 없습니다", rendered)

    def test_evidence_promotes_only_the_matching_recipe(self) -> None:
        recipes = list(iter_builtin_recipes())
        target = recipes[0]
        evidence = [
            (
                Path("model.json"),
                {
                    "kind": "kanana-garden-model-check",
                    "passed": True,
                    "recipe": {"slug": target.slug},
                },
            )
        ]
        catalog = build_catalog(recipes, evidence)
        by_slug = {recipe["slug"]: recipe for recipe in catalog["recipes"]}
        self.assertEqual(
            by_slug[target.slug]["trust_level"],
            "model-smoke-passed",
        )
        self.assertTrue(
            all(
                recipe["trust_level"] == "schema-only"
                for slug, recipe in by_slug.items()
                if slug != target.slug
            )
        )

    def test_two_boots_on_same_device_promote_reboot_level(self) -> None:
        recipes = list(iter_builtin_recipes())
        target = recipes[0]

        def baseline(name: str, boot: str) -> tuple[Path, dict]:
            return (
                Path(name),
                {
                    "kind": "kanana-garden-pi5-baseline",
                    "passed": True,
                    "device_before": {
                        "device_id_sha256": f"sha256:{'d' * 64}",
                        "boot_id_sha256": f"sha256:{boot * 64}",
                    },
                    "recipes": [{"slug": target.slug}],
                },
            )

        catalog = build_catalog(
            recipes,
            [baseline("boot-1.json", "a"), baseline("boot-2.json", "b")],
        )
        by_slug = {recipe["slug"]: recipe for recipe in catalog["recipes"]}
        self.assertEqual(
            by_slug[target.slug]["trust_level"],
            "pi5-reboot-reproduced",
        )
        self.assertEqual(
            catalog["evidence_summary"]["reboot_reproduced_device_count"],
            1,
        )

    def test_invalid_report_stops_catalog_generation(self) -> None:
        recipes, suites = load_assets()
        with tempfile.TemporaryDirectory() as directory:
            reports_dir = Path(directory)
            (reports_dir / "invalid.json").write_text(
                '{"kind": "unknown"}',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(RecipeError, "유효하지 않습니다"):
                load_validated_evidence(reports_dir, recipes, suites)


if __name__ == "__main__":
    unittest.main()
