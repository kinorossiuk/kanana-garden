import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / "android" / "uis7862s-bridge"
JAVA = BRIDGE / "app" / "src" / "main" / "java"


class AndroidBridgeTests(unittest.TestCase):
    def test_release_and_android_versions_match(self) -> None:
        build = (BRIDGE / "app" / "build.gradle").read_text(encoding="utf-8")
        package = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        release = (ROOT / ".github" / "workflows" / "release-android.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn('versionName "0.0.1-alpha.3"', build)
        self.assertIn('version = "0.0.1a3"', package)
        self.assertIn("v0.0.1-alpha.3", release)

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
            ],
        )
        self.assertNotIn("AccessibilityService", manifest)

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


if __name__ == "__main__":
    unittest.main()
