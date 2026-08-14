import os
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest import mock

from kanana_garden.device import GIB, _device_id_sha256, device_report


class DeviceReportTests(unittest.TestCase):
    def test_custom_device_id_is_domain_hashed_without_exposing_source(self) -> None:
        with mock.patch.dict(
            os.environ,
            {"KANANA_DEVICE_ID": "private-random-device-label"},
        ):
            digest = _device_id_sha256()
        self.assertIsNotNone(digest)
        self.assertRegex(digest or "", r"^sha256:[0-9a-f]{64}$")
        self.assertNotIn("private-random-device-label", digest or "")

    @mock.patch(
        "kanana_garden.device._device_id_sha256",
        return_value=f"sha256:{'d' * 64}",
    )
    @mock.patch(
        "kanana_garden.device._boot_id_sha256",
        return_value=f"sha256:{'a' * 64}",
    )
    @mock.patch("kanana_garden.device._throttled", return_value="throttled=0x0")
    @mock.patch("kanana_garden.device._temperature_c", return_value=54.25)
    @mock.patch(
        "kanana_garden.device._device_model",
        return_value="Raspberry Pi 5 Model B Rev 1.0",
    )
    @mock.patch("kanana_garden.device.shutil.disk_usage")
    @mock.patch("kanana_garden.device._mem_total", return_value=8 * GIB)
    @mock.patch("kanana_garden.device.platform.machine", return_value="aarch64")
    def test_pi5_profile_is_ready(
        self,
        _machine: mock.Mock,
        _memory: mock.Mock,
        disk_usage: mock.Mock,
        _device_model: mock.Mock,
        _temperature: mock.Mock,
        _throttled: mock.Mock,
        _boot_id: mock.Mock,
        _device_id: mock.Mock,
    ) -> None:
        disk_usage.return_value = SimpleNamespace(
            total=128 * GIB,
            used=20 * GIB,
            free=108 * GIB,
        )
        report = device_report("/tmp")
        self.assertTrue(report["ready"])
        self.assertEqual(report["kind"], "kanana-garden-device-check")
        self.assertEqual(report["powered_by"], "Kanana")
        self.assertEqual(report["boot_id_sha256"], f"sha256:{'a' * 64}")
        self.assertEqual(report["device_id_sha256"], f"sha256:{'d' * 64}")
        self.assertEqual(report["profile"], "raspberry-pi-5-8gb")
        self.assertEqual(report["temperature_c"], 54.25)
        self.assertEqual(report["throttled"], "throttled=0x0")

    @mock.patch(
        "kanana_garden.device._device_id_sha256",
        return_value=f"sha256:{'d' * 64}",
    )
    @mock.patch(
        "kanana_garden.device._boot_id_sha256",
        return_value=f"sha256:{'a' * 64}",
    )
    @mock.patch("kanana_garden.device.shutil.disk_usage")
    @mock.patch("kanana_garden.device._device_model", return_value="Generic PC")
    @mock.patch("kanana_garden.device._mem_total", return_value=4 * GIB)
    @mock.patch("kanana_garden.device.platform.machine", return_value="x86_64")
    def test_wrong_device_fails_required_checks(
        self,
        _machine: mock.Mock,
        _memory: mock.Mock,
        _device_model: mock.Mock,
        disk_usage: mock.Mock,
        _boot_id: mock.Mock,
        _device_id: mock.Mock,
    ) -> None:
        disk_usage.return_value = SimpleNamespace(
            total=16 * GIB,
            used=15 * GIB,
            free=1 * GIB,
        )
        report = device_report("/tmp")
        self.assertFalse(report["ready"])
        failed = {
            item["name"]
            for item in report["checks"]
            if item["required"] and not item["passed"]
        }
        self.assertEqual(
            failed,
            {"raspberry_pi_5", "arm64", "memory_8gb_profile", "free_disk"},
        )

    @mock.patch(
        "kanana_garden.device._device_id_sha256",
        return_value=f"sha256:{'d' * 64}",
    )
    @mock.patch(
        "kanana_garden.device._boot_id_sha256",
        return_value=f"sha256:{'a' * 64}",
    )
    @mock.patch("kanana_garden.device.shutil.disk_usage")
    @mock.patch("kanana_garden.device._device_model", return_value="Generic PC")
    @mock.patch("kanana_garden.device._mem_total", return_value=4 * GIB)
    @mock.patch("kanana_garden.device.platform.machine", return_value="x86_64")
    def test_checked_at_can_be_fixed_for_evidence(
        self,
        _machine: mock.Mock,
        _memory: mock.Mock,
        _device_model: mock.Mock,
        disk_usage: mock.Mock,
        _boot_id: mock.Mock,
        _device_id: mock.Mock,
    ) -> None:
        disk_usage.return_value = SimpleNamespace(
            total=16 * GIB,
            used=15 * GIB,
            free=1 * GIB,
        )
        checked_at = datetime(2026, 7, 31, 1, 2, 3, tzinfo=timezone.utc)
        report = device_report("/tmp", checked_at=checked_at)
        self.assertEqual(report["checked_at"], "2026-07-31T01:02:03Z")


if __name__ == "__main__":
    unittest.main()
