import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from kanana_garden.client import ChatResult
from kanana_garden.cli import build_parser, main


class CLITests(unittest.TestCase):
    def invoke(self, *args: str, stdin: str = "") -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
            mock.patch("sys.stdin", io.StringIO(stdin)),
        ):
            status = main(list(args))
        return status, stdout.getvalue(), stderr.getvalue()

    def test_version_uses_package_version(self) -> None:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            with self.assertRaises(SystemExit) as raised:
                build_parser().parse_args(["--version"])
        self.assertEqual(raised.exception.code, 0)
        self.assertEqual(stdout.getvalue().strip(), "kanana-garden 0.2.2")

    def test_list_json(self) -> None:
        status, stdout, stderr = self.invoke("list", "--json")
        self.assertEqual(status, 0)
        self.assertEqual(stderr, "")
        items = json.loads(stdout)
        self.assertTrue(any(item["slug"] == "plain-korean-ko" for item in items))

    def test_validate_builtins(self) -> None:
        status, stdout, stderr = self.invoke("validate")
        self.assertEqual(status, 0)
        self.assertIn("4개 레시피가 유효합니다.", stdout)
        self.assertEqual(stderr, "")

    def test_catalog_output_and_drift_check(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reports_dir = root / "reports"
            reports_dir.mkdir()
            output = root / "CATALOG.md"
            status, stdout, stderr = self.invoke(
                "catalog",
                "--reports-dir",
                str(reports_dir),
                "--output",
                str(output),
            )
            self.assertEqual(status, 0)
            self.assertEqual(stderr, "")
            self.assertIn("생성:", stdout)
            self.assertIn("스키마만 검증", output.read_text(encoding="utf-8"))

            status, stdout, stderr = self.invoke(
                "catalog",
                "--reports-dir",
                str(reports_dir),
                "--check",
                str(output),
            )
            self.assertEqual(status, 0)
            self.assertEqual(stderr, "")
            self.assertIn("OK", stdout)

            output.write_text("stale\n", encoding="utf-8")
            status, stdout, stderr = self.invoke(
                "catalog",
                "--reports-dir",
                str(reports_dir),
                "--check",
                str(output),
            )
            self.assertEqual(status, 1)
            self.assertEqual(stdout, "")
            self.assertIn("현재 recipe", stderr)

    def test_validate_parity_suite(self) -> None:
        status, stdout, stderr = self.invoke(
            "suite-validate", "runtime-stability-ko-v1"
        )
        self.assertEqual(status, 0)
        self.assertIn("runtime-stability-ko-v1", stdout)
        self.assertIn("cases", stdout)
        self.assertEqual(stderr, "")

    @mock.patch("kanana_garden.baseline.write_server_baseline_report")
    @mock.patch("kanana_garden.baseline.run_server_baseline")
    @mock.patch("kanana_garden.cli.KananaClient")
    def test_server_baseline_command_reports_summary(
        self,
        _client_class: mock.Mock,
        run_baseline: mock.Mock,
        write_report: mock.Mock,
    ) -> None:
        run_baseline.return_value = {
            "passed": True,
            "runtime": {
                "session_id": "11111111-1111-4111-8111-111111111111",
                "revision": "revision",
                "dtype": "float32",
            },
            "summary": {
                "passed_sample_count": 9,
                "sample_count": 9,
                "median_latency_seconds": 1.25,
                "p95_latency_seconds": 1.5,
                "median_tokens_per_second": 4.2,
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "baseline.json"
            status, stdout, stderr = self.invoke(
                "server-baseline",
                "--output",
                str(output),
            )
        self.assertEqual(status, 0)
        self.assertEqual(stderr, "")
        self.assertIn("9/9 samples", stdout)
        self.assertIn("report-validate", stdout)
        write_report.assert_called_once()

    def test_server_compare_command_reports_distinct_sessions(self) -> None:
        comparison = {
            "passed": True,
            "checks": [
                {
                    "name": "distinct_server_sessions",
                    "passed": True,
                    "detail": "different server session IDs",
                }
            ],
            "performance_delta": {
                "median_latency_percent": 1.0,
                "p95_latency_percent": 2.0,
                "median_tokens_per_second_percent": -1.0,
            },
        }
        with (
            mock.patch(
                "kanana_garden.report_validation.load_report",
                side_effect=[{}, {}],
            ),
            mock.patch(
                "kanana_garden.stability.compare_server_baselines",
                return_value=comparison,
            ),
        ):
            status, stdout, stderr = self.invoke(
                "server-compare",
                "first.json",
                "second.json",
            )
        self.assertEqual(status, 0)
        self.assertEqual(stderr, "")
        self.assertIn("PASS 5600G 서버 재시작 안정성", stdout)
        self.assertIn("distinct_server_sessions", stdout)

    def test_uis7862s_doctor_prints_build_identity(self) -> None:
        report = {
            "ready": True,
            "checks": [
                {
                    "name": "uis7862s_soc",
                    "passed": True,
                    "required": True,
                    "detail": "UMS512",
                }
            ],
            "device": {
                "manufacturer": "FYT",
                "model": "head unit",
                "android_release": "12",
                "sdk": 31,
                "build_fingerprint": "vendor/build",
            },
            "recommendations": [],
        }
        with mock.patch(
            "kanana_garden.uis7862s.device_report", return_value=report
        ):
            status, stdout, stderr = self.invoke("uis7862s-doctor")
        self.assertEqual(status, 0)
        self.assertEqual(stderr, "")
        self.assertIn("UMS512", stdout)
        self.assertIn("vendor/build", stdout)

    def test_uis7862s_capture_reports_triage_counts(self) -> None:
        report = {
            "complete": True,
            "capture_dir": "reports/uis7862s/example",
            "critical_failures": [],
            "analysis": {
                "candidate_counts": {
                    "crash": 1,
                    "anr": 0,
                    "memory": 2,
                    "watchdog": 0,
                    "thermal": 0,
                }
            },
        }
        with mock.patch(
            "kanana_garden.uis7862s.capture_diagnostics", return_value=report
        ) as capture:
            status, stdout, stderr = self.invoke(
                "uis7862s-capture",
                "--label",
                "issue-12",
                "--ota-version",
                "v1",
            )
        self.assertEqual(status, 0)
        self.assertEqual(stderr, "")
        self.assertIn("crash=1", stdout)
        capture.assert_called_once()

    def test_uis7862s_report_pull_prints_repository_path(self) -> None:
        report = {
            "path": "reports/uis7862s/example-stage-zero-report.txt",
            "sha256": "sha256:abc",
        }
        with mock.patch(
            "kanana_garden.uis7862s.pull_stage_zero_report", return_value=report
        ) as pull:
            status, stdout, stderr = self.invoke("uis7862s-report-pull")
        self.assertEqual(status, 0)
        self.assertEqual(stderr, "")
        self.assertIn(report["path"], stdout)
        pull.assert_called_once()

    def test_ota_verify_returns_failure_for_tampered_artifact(self) -> None:
        report = {
            "passed": False,
            "version": "v1",
            "path": "var/ota/v1/update.zip",
            "actual_sha256": "sha256:bad",
            "actual_bytes": 7,
        }
        with mock.patch("kanana_garden.ota.verify_ota", return_value=report):
            status, stdout, stderr = self.invoke(
                "ota-verify", "var/ota/v1/manifest.json"
            )
        self.assertEqual(status, 1)
        self.assertEqual(stderr, "")
        self.assertIn("FAIL OTA v1", stdout)

    def test_parity_rejects_same_endpoint(self) -> None:
        status, _, stderr = self.invoke(
            "parity",
            "runtime-stability-ko-v1",
            "--reference-url",
            "http://same-host:8000/v1/",
            "--candidate-url",
            "http://same-host:8000/v1",
        )
        self.assertEqual(status, 2)
        self.assertIn("서로 달라야", stderr)

    @mock.patch("kanana_garden.cli.KananaClient")
    def test_vehicle_command_returns_validated_action(
        self, client_class: mock.Mock
    ) -> None:
        model = "kakaocorp/kanana-2-1.3b-instruct"
        client_class.return_value.list_models.return_value = [model]
        client_class.return_value.chat.return_value = ChatResult(
            content=(
                '{"action":"volume_up","slots":{},"confidence":"high",'
                '"requires_confirmation":false}'
            ),
            model=model,
            usage={},
        )
        status, stdout, stderr = self.invoke(
            "vehicle-command", "--input", "볼륨 올려줘"
        )
        self.assertEqual(status, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(json.loads(stdout)["action"], "volume_up")

    @mock.patch("kanana_garden.cli.KananaClient")
    def test_vehicle_command_rejects_executable_model_output(
        self, client_class: mock.Mock
    ) -> None:
        model = "kakaocorp/kanana-2-1.3b-instruct"
        client_class.return_value.list_models.return_value = [model]
        client_class.return_value.chat.return_value = ChatResult(
            content=(
                '{"action":"app_open","slots":{"package":"evil.app"},'
                '"confidence":"high","requires_confirmation":false}'
            ),
            model=model,
            usage={},
        )
        status, _, stderr = self.invoke(
            "vehicle-command", "--input", "앱 열어"
        )
        self.assertEqual(status, 2)
        self.assertIn("app_open", stderr)

    def test_report_validate_rejects_unknown_kind(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            path.write_text('{"kind": "unknown"}', encoding="utf-8")
            status, stdout, stderr = self.invoke("report-validate", str(path))
            self.assertEqual(status, 1)
            self.assertEqual(stdout, "")
            self.assertIn("지원하지 않는 report kind", stderr)

    def test_report_validate_rejects_malformed_json_as_report_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            path.write_text("{", encoding="utf-8")
            status, stdout, stderr = self.invoke("report-validate", str(path))
            self.assertEqual(status, 1)
            self.assertEqual(stdout, "")
            self.assertIn("JSON 문법 오류", stderr)

    def test_report_validate_without_stored_reports_is_a_noop(self) -> None:
        with (
            tempfile.TemporaryDirectory() as directory,
            mock.patch("pathlib.Path.glob", return_value=iter(())),
        ):
            status, stdout, stderr = self.invoke("report-validate")
            self.assertEqual(status, 0)
            self.assertIn("검증할 JSON 리포트가 없습니다.", stdout)
            self.assertEqual(stderr, "")

    def test_render_from_stdin(self) -> None:
        status, stdout, stderr = self.invoke(
            "render",
            "plain-korean-ko",
            "--input-file",
            "-",
            stdin="어려운 문장",
        )
        self.assertEqual(status, 0)
        messages = json.loads(stdout)
        self.assertIn("어려운 문장", messages[1]["content"])
        self.assertEqual(stderr, "")

    def test_new_and_validate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "new.json"
            status, _, stderr = self.invoke(
                "new", "community-helper", "--output", str(path)
            )
            self.assertEqual(status, 0)
            self.assertEqual(stderr, "")
            status, stdout, stderr = self.invoke("validate", str(path))
            self.assertEqual(status, 0)
            self.assertIn("OK  community-helper", stdout)
            self.assertEqual(stderr, "")

    def test_external_recipe_can_render(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "external.json"
            status, _, _ = self.invoke(
                "new", "external-recipe", "--output", str(path)
            )
            self.assertEqual(status, 0)
            status, stdout, stderr = self.invoke(
                "render", str(path), "--input", "외부 입력"
            )
            self.assertEqual(status, 0)
            self.assertIn("외부 입력", stdout)
            self.assertEqual(stderr, "")

    @mock.patch("kanana_garden.cli.KananaClient")
    def test_check_passes_expected_text(self, client_class: mock.Mock) -> None:
        client_class.return_value.list_models.return_value = [
            "kakaocorp/kanana-2-1.3b-instruct"
        ]
        client_class.return_value.chat.return_value = ChatResult(
            content="액션 아이템 표입니다.",
            model="kakaocorp/kanana-2-1.3b-instruct",
            usage={},
        )
        status, stdout, stderr = self.invoke("check", "meeting-action-items-ko")
        self.assertEqual(status, 0)
        self.assertIn("PASS 예제 1", stdout)
        self.assertEqual(stderr, "")

    @mock.patch("kanana_garden.cli.KananaClient")
    def test_check_fails_missing_expected_text(self, client_class: mock.Mock) -> None:
        client_class.return_value.list_models.return_value = [
            "kakaocorp/kanana-2-1.3b-instruct"
        ]
        client_class.return_value.chat.return_value = ChatResult(
            content="관련 없는 결과",
            model="kakaocorp/kanana-2-1.3b-instruct",
            usage={},
        )
        status, stdout, stderr = self.invoke("check", "meeting-action-items-ko")
        self.assertEqual(status, 1)
        self.assertIn("FAIL 예제 1", stdout)
        self.assertIn("기대 문자열", stderr)

    @mock.patch("kanana_garden.cli.KananaClient")
    def test_check_writes_machine_readable_report(
        self, client_class: mock.Mock
    ) -> None:
        model = "kakaocorp/kanana-2-1.3b-instruct"
        client_class.return_value.list_models.return_value = [model]
        client_class.return_value.chat.return_value = ChatResult(
            content="액션 아이템",
            model=model,
            usage={"total_tokens": 42},
        )
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "reports" / "check.json"
            status, stdout, stderr = self.invoke(
                "check",
                "meeting-action-items-ko",
                "--json",
                "--output",
                str(output),
            )
            self.assertEqual(status, 0)
            self.assertEqual(stderr, "")
            report = json.loads(stdout)
            self.assertTrue(report["passed"])
            self.assertEqual(report["requested_model"], model)
            self.assertEqual(report["cases"][0]["usage"]["total_tokens"], 42)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), report)

    @mock.patch("kanana_garden.cli.KananaClient")
    def test_check_rejects_unexposed_model(self, client_class: mock.Mock) -> None:
        client_class.return_value.list_models.return_value = ["different-model"]
        status, _, stderr = self.invoke("check", "meeting-action-items-ko")
        self.assertEqual(status, 2)
        self.assertIn("서버 모델 목록", stderr)
        client_class.return_value.chat.assert_not_called()

    @mock.patch("kanana_garden.cli.KananaClient")
    def test_doctor_finds_default_model(self, client_class: mock.Mock) -> None:
        client_class.return_value.list_models.return_value = [
            "kakaocorp/kanana-2-1.3b-instruct"
        ]
        status, stdout, stderr = self.invoke("doctor")
        self.assertEqual(status, 0)
        self.assertIn("OK  기본 모델", stdout)
        self.assertEqual(stderr, "")

    @mock.patch("kanana_garden.cli.KananaClient")
    def test_doctor_reports_missing_model(self, client_class: mock.Mock) -> None:
        client_class.return_value.list_models.return_value = ["another-model"]
        status, stdout, stderr = self.invoke("doctor")
        self.assertEqual(status, 1)
        self.assertIn("OK  API 연결", stdout)
        self.assertIn("FAIL 요청 모델", stderr)

    def test_new_does_not_overwrite_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "exists.json"
            path.write_text("keep", encoding="utf-8")
            status, _, stderr = self.invoke(
                "new", "community-helper", "--output", str(path)
            )
            self.assertEqual(status, 2)
            self.assertIn("--force", stderr)
            self.assertEqual(path.read_text(encoding="utf-8"), "keep")

    def test_rejects_empty_input(self) -> None:
        status, _, stderr = self.invoke(
            "render", "plain-korean-ko", "--input", "   "
        )
        self.assertEqual(status, 2)
        self.assertIn("비어", stderr)


if __name__ == "__main__":
    unittest.main()
