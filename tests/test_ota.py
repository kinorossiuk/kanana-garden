import hashlib
import io
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from kanana_garden.ota import download_ota, verify_ota
from kanana_garden.recipe import RecipeError


CHECKED_AT = datetime(2026, 8, 14, 1, 2, 3, tzinfo=timezone.utc)


class FakeResponse(io.BytesIO):
    def geturl(self) -> str:
        return "https://cdn.example.test/releases/update.zip?temporary=secret"


class OTATests(unittest.TestCase):
    def test_download_requires_hash_and_writes_versioned_manifest(self) -> None:
        payload = b"fake signed firmware image"
        expected = hashlib.sha256(payload).hexdigest()

        def opener(_request, timeout):
            self.assertEqual(timeout, 30.0)
            return FakeResponse(payload)

        with tempfile.TemporaryDirectory() as directory:
            report = download_ota(
                version="2026.08.1",
                url="https://vendor.example.test/update.zip?token=secret",
                sha256=expected,
                output_dir=Path(directory),
                timeout=30.0,
                checked_at=CHECKED_AT,
                opener=opener,
            )
            self.assertEqual(report["state"], "downloaded-not-flashed")
            self.assertNotIn("token", report["source_url"])
            self.assertNotIn("temporary", report["final_url"])
            verification = verify_ota(Path(report["manifest"]))
            self.assertTrue(verification["passed"])

    def test_hash_mismatch_removes_partial_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(RecipeError, "SHA-256 불일치"):
                download_ota(
                    version="bad-build",
                    url="https://vendor.example.test/update.zip",
                    sha256="0" * 64,
                    output_dir=root,
                    opener=lambda _request, timeout: FakeResponse(b"wrong"),
                )
            version_dir = root / "bad-build"
            self.assertEqual(list(version_dir.iterdir()), [])

    def test_verify_detects_tampered_ota(self) -> None:
        payload = b"firmware"
        expected = hashlib.sha256(payload).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            report = download_ota(
                version="v1",
                url="https://vendor.example.test/update.zip",
                sha256=expected,
                output_dir=Path(directory),
                opener=lambda _request, timeout: FakeResponse(payload),
            )
            Path(report["path"]).write_bytes(b"tampered")
            self.assertFalse(verify_ota(Path(report["path"]))["passed"])

    def test_plain_http_requires_explicit_opt_in(self) -> None:
        with self.assertRaisesRegex(RecipeError, "--allow-http"):
            download_ota(
                version="v1",
                url="http://vendor.example.test/update.zip",
                sha256="0" * 64,
            )


if __name__ == "__main__":
    unittest.main()
