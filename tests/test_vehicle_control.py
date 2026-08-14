import unittest

from kanana_garden.recipe import RecipeError
from kanana_garden.vehicle_control import parse_vehicle_action


class VehicleControlTests(unittest.TestCase):
    def test_accepts_bounded_volume_action(self) -> None:
        action = parse_vehicle_action(
            '{"action":"volume_set","slots":{"level_percent":30},'
            '"confidence":"high","requires_confirmation":false}'
        )
        self.assertEqual(action["slots"]["level_percent"], 30)

    def test_accepts_navigation_destination_as_data(self) -> None:
        action = parse_vehicle_action(
            '{"action":"navigation_start","slots":{"destination":"강남역"},'
            '"confidence":"high","requires_confirmation":true}'
        )
        self.assertEqual(action["slots"]["destination"], "강남역")

    def test_rejects_shell_touch_and_package_fields(self) -> None:
        for content in (
            '{"action":"volume_up","slots":{},"confidence":"high",'
            '"requires_confirmation":false,"shell":"input keyevent 24"}',
            '{"action":"app_open","slots":{"package":"com.anything"},'
            '"confidence":"high","requires_confirmation":false}',
        ):
            with self.subTest(content=content):
                with self.assertRaises(RecipeError):
                    parse_vehicle_action(content)

    def test_rejects_markdown_wrapped_json(self) -> None:
        with self.assertRaisesRegex(RecipeError, "JSON 객체"):
            parse_vehicle_action(
                '```json\n{"action":"volume_up","slots":{},'
                '"confidence":"high","requires_confirmation":false}\n```'
            )


if __name__ == "__main__":
    unittest.main()
