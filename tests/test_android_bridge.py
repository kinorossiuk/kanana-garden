import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / "android" / "uis7862s-bridge"
JAVA = BRIDGE / "app" / "src" / "main" / "java"


class AndroidBridgeTests(unittest.TestCase):
    def test_release_and_android_versions_match(self) -> None:
        version = (BRIDGE / "version.properties").read_text(encoding="utf-8")
        package = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        release = (ROOT / ".github" / "workflows" / "release-android.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("VERSION_CODE=201", version)
        self.assertIn("VERSION_NAME=0.2.1", version)
        self.assertIn('version = "0.2.1"', package)
        self.assertIn('tags:\n      - "v*"', release)
        self.assertIn("secrets.ANDROID_SIGNING_KEY_BASE64", release)
        self.assertIn("secrets.ANDROID_SIGNING_PASSWORD", release)
        self.assertNotIn("secrets.ANDROID_KEY_PASSWORD", release)

    def test_bridge_declares_only_required_sensitive_permission(self) -> None:
        manifest = (BRIDGE / "app" / "src" / "main" / "AndroidManifest.xml").read_text(
            encoding="utf-8"
        )
        permissions = re.findall(r'<uses-permission android:name="([^"]+)"', manifest)
        self.assertEqual(
            permissions,
            [
                "android.permission.MODIFY_AUDIO_SETTINGS",
                "android.permission.INTERNET",
                "android.permission.REQUEST_INSTALL_PACKAGES",
            ],
        )
        self.assertNotIn("AccessibilityService", manifest)

    def test_release_keeps_private_bounded_crash_diagnostics(self) -> None:
        manifest = (BRIDGE / "app" / "src" / "main" / "AndroidManifest.xml").read_text(
            encoding="utf-8"
        )
        build = (BRIDGE / "app" / "build.gradle").read_text(encoding="utf-8")
        diagnostics = next(JAVA.rglob("CrashDiagnostics.java")).read_text(
            encoding="utf-8"
        )
        activity = next(JAVA.rglob("MainActivity.java")).read_text(encoding="utf-8")

        self.assertIn('android:name=".BridgeApplication"', manifest)
        self.assertNotIn('android:debuggable="true"', manifest)
        self.assertNotIn("debuggable true", build)
        self.assertIn("Thread.setDefaultUncaughtExceptionHandler", diagnostics)
        self.assertIn("delegate.uncaughtException(thread, error)", diagnostics)
        self.assertIn("Context.MODE_PRIVATE", diagnostics)
        self.assertIn("MAX_CRASH_BYTES = 12 * 1024", diagnostics)
        self.assertIn("MAX_HANDLED_BYTES = 16 * 1024", diagnostics)
        self.assertIn("[REDACTED]", diagnostics)
        self.assertIn("CrashDiagnostics.readPending(this)", activity)
        self.assertIn("이전 앱 비정상 종료 진단", activity)
        self.assertIn("CrashDiagnostics.readHandled(this)", activity)
        self.assertIn("처리된 내부 오류 상세", activity)
        self.assertIn("CrashDiagnostics.clearAll(this)", activity)
        self.assertIn("Build.HARDWARE", activity)
        self.assertIn("Build.BOARD", activity)
        self.assertIn("Build.SUPPORTED_ABIS", activity)
        self.assertIn("Build.VERSION.SECURITY_PATCH", activity)
        self.assertIn("Build.FINGERPRINT", activity)
        self.assertNotIn("Build.SERIAL", activity)

    def test_bridge_has_no_arbitrary_execution_primitives(self) -> None:
        sources = "\n".join(
            path.read_text(encoding="utf-8") for path in sorted(JAVA.rglob("*.java"))
        )
        for forbidden in (
            "Runtime.getRuntime",
            "ProcessBuilder",
            "getLaunchIntentForPackage",
            "AccessibilityService",
            "dispatchGesture",
            "input keyevent",
            "input tap",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, sources)

    def test_external_payload_is_loaded_but_not_auto_executed(self) -> None:
        activity = next(JAVA.rglob("MainActivity.java")).read_text(encoding="utf-8")
        loader = activity[activity.index("private void loadIntentPayload") :]
        loader = loader[: loader.index("private void addPresetButton")]
        self.assertIn("actionInput.setText(payload)", loader)
        self.assertNotIn("execute(", loader)
        self.assertNotIn("validateAndExecute(", loader)

    def test_checklist_and_submission_remain_user_initiated(self) -> None:
        activity = next(JAVA.rglob("MainActivity.java")).read_text(encoding="utf-8")
        uploader = next(JAVA.rglob("ReportUploader.java")).read_text(encoding="utf-8")
        self.assertIn("CheckBox", activity)
        self.assertIn("PASS", activity)
        self.assertIn("FAIL", activity)
        self.assertIn("submitReportOverLte(submitReport)", activity)
        self.assertIn("HttpsURLConnection", uploader)
        self.assertIn('"https".equalsIgnoreCase', uploader)
        self.assertIn("setInstanceFollowRedirects(false)", uploader)

    def test_ota_update_is_user_initiated_and_verifies_release(self) -> None:
        activity = next(JAVA.rglob("MainActivity.java")).read_text(encoding="utf-8")
        updater = next(JAVA.rglob("UpdateManager.java")).read_text(encoding="utf-8")
        self.assertIn("checkForAppUpdate(updateButton)", activity)
        self.assertIn("setPositiveButton(\"다운로드\"", activity)
        self.assertNotIn("checkForAppUpdate(updateButton);", activity)
        self.assertIn("candidateVersion <= BuildConfig.VERSION_CODE", updater)
        self.assertIn("signatureSet(installed).equals(signatureSet(candidate))", updater)
        self.assertIn("actualSha256.equals(update.sha256)", updater)
        self.assertIn("Intent.ACTION_INSTALL_PACKAGE", updater)

    def test_report_receiver_deployment_is_separate_from_5600g(self) -> None:
        report_ops = ROOT / "ops" / "report-host"
        model_ops = ROOT / "ops" / "5600g"

        self.assertTrue((report_ops / "install.sh").is_file())
        self.assertTrue((report_ops / "kanana-report-receiver.service").is_file())
        self.assertTrue((report_ops / "report-receiver.env.example").is_file())
        self.assertTrue((report_ops / "nginx-report-receiver.conf.example").is_file())
        self.assertFalse((model_ops / "kanana-report-receiver.service").exists())
        model_install = (model_ops / "install.sh").read_text(encoding="utf-8")
        self.assertNotIn("report-receiver", model_install)


if __name__ == "__main__":
    unittest.main()
