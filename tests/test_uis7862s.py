import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from kanana_garden.uis7862s import (
    AdbResult,
    analyze_logcat,
    build_device_report,
    capture_diagnostics,
    parse_adb_devices,
    pull_stage_zero_report,
    sanitize_getprop,
)


CHECKED_AT = datetime(2026, 8, 14, 1, 2, 3, tzinfo=timezone.utc)


def ready_properties() -> dict[str, str]:
    return {
        "ro.product.manufacturer": "FYT",
        "ro.product.model": "7862 unit",
        "ro.product.cpu.abi": "arm64-v8a",
        "ro.build.version.release": "12",
        "ro.build.version.sdk": "31",
        "ro.build.fingerprint": "vendor/device/build:12/id:user/release-keys",
        "ro.soc.model": "UMS512",
        "ro.board.platform": "ums512",
        "ro.hardware": "ums512_1h10",
        "ro.product.board": "uis7862s",
        "ro.debuggable": "0",
    }


class FakeAdbClient:
    serial = "secret-device-serial"

    def _result(self, command: tuple[str, ...], value: bytes = b"") -> AdbResult:
        return AdbResult(command, 0, value, "", 0.01)

    def shell(self, arguments, timeout=None):
        command = tuple(arguments)
        if command[:1] == ("getprop",) and len(command) == 2:
            value = ready_properties().get(command[1], "") + "\n"
        elif command == ("getprop",):
            value = (
                "[ro.build.version.release]: [12]\n"
                "[ro.serialno]: [must-not-leak]\n"
            )
        elif command == ("cat", "/proc/meminfo"):
            value = "MemTotal:        6123456 kB\n"
        elif command == ("df", "-k", "/data"):
            value = "Filesystem 1K-blocks Used Available Use% Mounted on\n/dev 10000000 100 9000000 1% /data\n"
        elif command == ("cat", "/proc/sys/kernel/random/boot_id"):
            value = "boot-secret\n"
        elif command[:1] == ("logcat",):
            value = (
                "08-14 10:00:00.000  123  123 E AndroidRuntime: FATAL EXCEPTION: main\n"
                "08-14 10:00:00.010  123  123 E com.example.app: boom\n"
            )
        elif command == ("pidof", "com.example.app"):
            value = "123\n"
        else:
            value = "ok\n"
        return self._result(("shell", *command), value.encode())

    def exec_out(self, arguments, timeout=None):
        return self._result(("exec-out", *arguments), b"\x89PNG\r\n\x1a\n")

    def bugreport(self, output, timeout=300.0):
        output.write_bytes(b"bugreport")
        return self._result(("bugreport", str(output)), b"")


class UIS7862STests(unittest.TestCase):
    def test_parse_adb_devices_keeps_states_and_details(self) -> None:
        devices = parse_adb_devices(
            "List of devices attached\n"
            "ABC device product:foo model:Head_Unit transport_id:1\n"
            "DEF unauthorized usb:1-2\n"
        )
        self.assertEqual(devices[0]["serial"], "ABC")
        self.assertEqual(devices[0]["model"], "Head_Unit")
        self.assertEqual(devices[1]["state"], "unauthorized")

    def test_ums512_alias_builds_ready_profile_without_raw_serial(self) -> None:
        report = build_device_report(
            serial="private-serial",
            properties=ready_properties(),
            meminfo="MemTotal:        6123456 kB\n",
            data_df="fs 10000000 100 9000000 1% /data\n",
            boot_id="private-boot-id",
            checked_at=CHECKED_AT,
        )
        self.assertTrue(report["ready"])
        self.assertEqual(report["profile"], "uis7862s-android-head-unit")
        self.assertRegex(report["device_id_sha256"], r"^sha256:[0-9a-f]{64}$")
        self.assertNotIn("private-serial", json.dumps(report))

    def test_getprop_redacts_stable_identifiers(self) -> None:
        value = (
            "[ro.build.fingerprint]: [safe-build]\n"
            "[ro.serialno]: [secret]\n"
            "[persist.radio.imei]: [123]\n"
        )
        sanitized = sanitize_getprop(value)
        self.assertIn("safe-build", sanitized)
        self.assertNotIn("secret", sanitized)
        self.assertNotIn("[123]", sanitized)
        self.assertEqual(sanitized.count("REDACTED"), 2)

    def test_logcat_analysis_extracts_bounded_triage_categories(self) -> None:
        logcat = (
            "08-14 10:00:00.000  123  123 E AndroidRuntime: FATAL EXCEPTION: main\n"
            "08-14 10:00:01.000  456  456 W ActivityManager: ANR in com.app\n"
            "08-14 10:00:02.000  456  456 E app: OutOfMemoryError com.app\n"
        )
        analysis = analyze_logcat(logcat, "com.app")
        self.assertEqual(analysis["severity_counts"]["E"], 2)
        self.assertEqual(analysis["candidate_counts"]["crash"], 1)
        self.assertEqual(analysis["candidate_counts"]["anr"], 1)
        self.assertEqual(analysis["candidate_counts"]["memory"], 1)
        self.assertEqual(analysis["package_line_count"], 2)

    def test_capture_writes_manifest_hashes_and_package_view(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "capture"
            report = capture_diagnostics(
                output=output,
                label="issue 12",
                package="com.example.app",
                ota_version="2026.08.1",
                include_screenshot=True,
                checked_at=CHECKED_AT,
                client=FakeAdbClient(),
            )
            self.assertTrue(report["complete"])
            self.assertEqual(report["label"], "issue-12")
            self.assertEqual(report["ota_version"], "2026.08.1")
            self.assertEqual(report["analysis"]["candidate_counts"]["crash"], 1)
            self.assertTrue((output / "manifest.json").is_file())
            self.assertTrue((output / "logs/package-logcat.txt").is_file())
            getprop = (output / "system/getprop.txt").read_text(encoding="utf-8")
            self.assertNotIn("must-not-leak", getprop)
            artifact = next(
                item for item in report["artifacts"] if item["path"] == "analysis.json"
            )
            self.assertRegex(artifact["sha256"], r"^sha256:[0-9a-f]{64}$")

    def test_pull_stage_zero_report_uses_bounded_run_as_transport(self) -> None:
        class ReportAdbClient(FakeAdbClient):
            def exec_out(self, arguments, timeout=None):
                self.report_command = tuple(arguments)
                value = (
                    "Kanana Garden UIS7862S 0단계 테스트\n"
                    "앱 버전: 0.0.1-alpha.3\n"
                    "- [PASS] 볼륨 올리기\n"
                ).encode()
                return self._result(tuple(arguments), value)

        with tempfile.TemporaryDirectory() as directory:
            client = ReportAdbClient()
            output = Path(directory) / "stage-zero.txt"
            result = pull_stage_zero_report(
                output=output,
                checked_at=CHECKED_AT,
                client=client,
            )
            self.assertEqual(
                client.report_command,
                (
                    "run-as",
                    "dev.kinorossiuk.kananagarden.bridge",
                    "cat",
                    "files/stage-zero-report.txt",
                ),
            )
            self.assertEqual(result["path"], str(output))
            self.assertIn("[PASS]", output.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
