import copy
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from kanana_garden.baseline import (
    SAFE_THROTTLED,
    run_pi5_baseline,
    write_pi5_baseline_report,
)
from kanana_garden.client import ChatResult
from kanana_garden.recipe import RecipeError, iter_builtin_recipes
from kanana_garden.report_validation import (
    load_assets,
    validate_pi5_baseline,
    validate_report_path,
)
from kanana_garden.reboot import compare_pi5_baselines


MODEL = "kakaocorp/kanana-2-1.3b-instruct"
CHECKED_AT = datetime(2026, 7, 31, 1, 2, 3, tzinfo=timezone.utc)
BOOT_ID = f"sha256:{'a' * 64}"
DEVICE_ID = f"sha256:{'d' * 64}"


def ready_device(
    temperature: float = 52.0,
    boot_id_sha256: str = BOOT_ID,
    device_id_sha256: str = DEVICE_ID,
) -> dict:
    checks = [
        ("raspberry_pi_5", True, True, "Raspberry Pi 5 Model B Rev 1.0"),
        ("arm64", True, True, "aarch64"),
        ("memory_8gb_profile", True, True, "8.0 GiB"),
        ("free_disk", True, True, "100.0 GiB free"),
        ("python", True, True, "3.12.0"),
        ("boot_id", True, True, boot_id_sha256),
        ("device_id", True, True, device_id_sha256),
        ("native_bf16", False, False, "not advertised by CPU"),
        ("temperature", temperature < 80, True, f"{temperature:.1f} °C"),
        ("throttling", True, True, SAFE_THROTTLED),
    ]
    return {
        "schema_version": 1,
        "kind": "kanana-garden-device-check",
        "powered_by": "Kanana",
        "checked_at": "2026-07-31T01:02:03Z",
        "profile": "raspberry-pi-5-8gb",
        "boot_id_sha256": boot_id_sha256,
        "device_id_sha256": device_id_sha256,
        "ready": temperature < 80,
        "checks": [
            {
                "name": name,
                "passed": passed,
                "required": required,
                "detail": detail,
            }
            for name, passed, required, detail in checks
        ],
        "temperature_c": temperature,
        "throttled": SAFE_THROTTLED,
        "recommendations": [],
    }


class FakeClient:
    def __init__(self) -> None:
        self.chat_count = 0

    def list_models(self) -> list[str]:
        return [MODEL]

    def chat(self, **kwargs: object) -> ChatResult:
        self.chat_count += 1
        messages = kwargs["messages"]
        assert isinstance(messages, list)
        prompt = messages[-1]["content"]
        if "액션 아이템 표" in prompt:
            content = "액션 아이템"
        elif "## 쉬운 문장" in prompt:
            content = "14일"
        else:
            content = "7일 MVP"
        return ChatResult(
            content=content,
            model=MODEL,
            usage={"completion_tokens": 10},
        )


class HalfSecondClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        self.value += 0.5
        return self.value


class BaselineTests(unittest.TestCase):
    def run_baseline(self, telemetry_temperature: float = 55.0) -> tuple[dict, FakeClient]:
        client = FakeClient()
        report = run_pi5_baseline(
            client=client,
            endpoint="http://pi.local:8000/v1",
            model=MODEL,
            recipes=iter_builtin_recipes(),
            repetitions=3,
            device_probe=lambda _path: copy.deepcopy(ready_device()),
            telemetry_probe=lambda: {
                "temperature_c": telemetry_temperature,
                "throttled": SAFE_THROTTLED,
            },
            clock=HalfSecondClock(),
            checked_at=CHECKED_AT,
        )
        return report, client

    def test_three_repetitions_build_a_complete_valid_baseline(self) -> None:
        report, client = self.run_baseline()
        self.assertTrue(report["complete"])
        self.assertTrue(report["passed"])
        self.assertEqual(client.chat_count, 9)
        self.assertEqual(report["summary"]["sample_count"], 9)
        self.assertEqual(report["summary"]["median_latency_seconds"], 0.5)
        self.assertEqual(report["summary"]["median_tokens_per_second"], 20.0)
        recipes, _ = load_assets()
        self.assertEqual(validate_pi5_baseline(report, recipes), [])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "baseline.json"
            write_pi5_baseline_report(report, path)
            _, suites = load_assets()
            self.assertEqual(validate_report_path(path, recipes, suites), [])
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), report)

    def test_temperature_limit_stops_more_generation_and_validates(self) -> None:
        report, client = self.run_baseline(telemetry_temperature=81.0)
        self.assertFalse(report["complete"])
        self.assertFalse(report["passed"])
        self.assertEqual(report["stop_reason"], "temperature_limit")
        self.assertEqual(client.chat_count, 1)
        recipes, _ = load_assets()
        self.assertEqual(validate_pi5_baseline(report, recipes), [])

    def test_tampered_content_summary_and_rate_are_rejected(self) -> None:
        report, _ = self.run_baseline()
        first = report["recipes"][0]["samples"][0]
        first["content"] = "관련 없는 응답"
        first["tokens_per_second"] = 999
        report["summary"]["pass_rate"] = 1
        recipes, _ = load_assets()
        errors = validate_pi5_baseline(report, recipes)
        self.assertTrue(any(".passed" in error for error in errors))
        self.assertTrue(any("tokens_per_second" in error for error in errors))
        self.assertTrue(any("summary.pass_rate" in error for error in errors))
        self.assertTrue(any(error.startswith("passed") for error in errors))

    def test_unready_device_fails_before_model_request(self) -> None:
        client = FakeClient()
        device = ready_device(temperature=81.0)
        with self.assertRaisesRegex(RecipeError, "device-doctor"):
            run_pi5_baseline(
                client=client,
                endpoint="http://pi.local:8000/v1",
                model=MODEL,
                recipes=iter_builtin_recipes(),
                device_probe=lambda _path: device,
            )
        self.assertEqual(client.chat_count, 0)

    def test_distinct_boot_baselines_prove_reboot_reproducibility(self) -> None:
        first, _ = self.run_baseline()
        second = copy.deepcopy(first)
        second_boot = f"sha256:{'b' * 64}"
        for device_key in ("device_before", "device_after"):
            device = second[device_key]
            device["boot_id_sha256"] = second_boot
            boot_check = next(
                check for check in device["checks"] if check["name"] == "boot_id"
            )
            boot_check["detail"] = second_boot
        recipes, _ = load_assets()
        comparison = compare_pi5_baselines(
            first,
            second,
            recipes,
            compared_at=CHECKED_AT,
        )
        self.assertTrue(comparison["passed"])
        self.assertEqual(
            comparison["performance_delta"]["median_latency_percent"],
            0.0,
        )
        self.assertEqual(comparison["compared_at"], "2026-07-31T01:02:03Z")

    def test_same_boot_does_not_prove_reboot_reproducibility(self) -> None:
        first, _ = self.run_baseline()
        recipes, _ = load_assets()
        comparison = compare_pi5_baselines(
            first,
            copy.deepcopy(first),
            recipes,
            compared_at=CHECKED_AT,
        )
        self.assertFalse(comparison["passed"])
        distinct_check = next(
            check
            for check in comparison["checks"]
            if check["name"] == "distinct_boot_sessions"
        )
        self.assertFalse(distinct_check["passed"])

    def test_different_device_does_not_prove_reboot_reproducibility(self) -> None:
        first, _ = self.run_baseline()
        second = copy.deepcopy(first)
        second_device_id = f"sha256:{'e' * 64}"
        for device_key in ("device_before", "device_after"):
            device = second[device_key]
            device["device_id_sha256"] = second_device_id
            device_check = next(
                check
                for check in device["checks"]
                if check["name"] == "device_id"
            )
            device_check["detail"] = second_device_id
        second_boot = f"sha256:{'b' * 64}"
        for device_key in ("device_before", "device_after"):
            device = second[device_key]
            device["boot_id_sha256"] = second_boot
            boot_check = next(
                check for check in device["checks"] if check["name"] == "boot_id"
            )
            boot_check["detail"] = second_boot
        recipes, _ = load_assets()
        comparison = compare_pi5_baselines(
            first,
            second,
            recipes,
            compared_at=CHECKED_AT,
        )
        self.assertFalse(comparison["passed"])
        same_device = next(
            check
            for check in comparison["checks"]
            if check["name"] == "same_device"
        )
        self.assertFalse(same_device["passed"])

    def test_compare_rejects_tampered_baseline(self) -> None:
        first, _ = self.run_baseline()
        second = copy.deepcopy(first)
        second["summary"]["sample_count"] = 999
        recipes, _ = load_assets()
        with self.assertRaisesRegex(RecipeError, "유효하지 않습니다"):
            compare_pi5_baselines(first, second, recipes)


if __name__ == "__main__":
    unittest.main()
