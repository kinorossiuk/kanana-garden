import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VERIFY_SCRIPT = ROOT / "ops" / "android-signing" / "verify-apk.sh"
CREATE_SCRIPT = ROOT / "ops" / "android-signing" / "create.sh"
EXPECTED_SIGNER = (
    "c60bfc4428e62f5d54684f855bc20da7"
    "c0fefa2057b2f6a56cfa8d8e2e30d63a"
)


class AndroidSigningTests(unittest.TestCase):
    def run_verifier(
        self, signer_output: str, exit_code: int = 0
    ) -> subprocess.CompletedProcess:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            apk = root / "release candidate.apk"
            apk.write_bytes(b"test APK placeholder")
            fake_apksigner = root / "apksigner"
            fake_apksigner.write_text(
                "#!/usr/bin/env bash\n"
                "printf '%s\\n' \"$FAKE_APKSIGNER_OUTPUT\"\n"
                "exit \"$FAKE_APKSIGNER_EXIT\"\n",
                encoding="utf-8",
            )
            fake_apksigner.chmod(0o700)
            environment = os.environ.copy()
            environment.update(
                {
                    "APKSIGNER": str(fake_apksigner),
                    "FAKE_APKSIGNER_OUTPUT": signer_output,
                    "FAKE_APKSIGNER_EXIT": str(exit_code),
                }
            )
            return subprocess.run(
                [str(VERIFY_SCRIPT), str(apk)],
                check=False,
                capture_output=True,
                text=True,
                env=environment,
            )

    def test_accepts_the_pinned_release_signer(self) -> None:
        result = self.run_verifier(
            f"Signer #1 certificate SHA-256 digest: {EXPECTED_SIGNER}"
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Pinned Android OTA signer verified", result.stdout)

    def test_rejects_a_different_valid_signer(self) -> None:
        result = self.run_verifier(
            "Signer #1 certificate SHA-256 digest: " + ("0" * 64)
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("does not match the pinned OTA certificate", result.stderr)

    def test_rejects_missing_signer_details(self) -> None:
        result = self.run_verifier("Verified")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Expected exactly one Android APK signer, found 0", result.stderr)

    def test_rejects_multiple_signers(self) -> None:
        result = self.run_verifier(
            "\n".join(
                (
                    f"Signer #1 certificate SHA-256 digest: {EXPECTED_SIGNER}",
                    "Signer #2 certificate SHA-256 digest: " + ("0" * 64),
                )
            )
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Expected exactly one Android APK signer, found 2", result.stderr)

    def test_rejects_apksigner_verification_failure(self) -> None:
        result = self.run_verifier("DOES NOT VERIFY", exit_code=1)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("signature verification failed", result.stderr)

    def test_signing_setup_refuses_to_generate_a_replacement_key(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            signing_dir = Path(temp_dir) / "signing"
            environment = os.environ.copy()
            environment["KANANA_SIGNING_DIR"] = str(signing_dir)
            result = subprocess.run(
                [str(CREATE_SCRIPT)],
                check=False,
                capture_output=True,
                text=True,
                env=environment,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Refusing to generate a replacement key", result.stderr)
            self.assertFalse(signing_dir.exists())

    def test_signing_setup_rejects_a_different_keystore(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            signing_dir = Path(temp_dir) / "signing"
            signing_dir.mkdir()
            password = "a" * 64
            password_file = signing_dir / "android-signing-password"
            private_key = signing_dir / "different-private-key.pem"
            certificate = signing_dir / "different-certificate.pem"
            keystore = signing_dir / "kanana-bridge-release.p12"
            password_file.write_text(password + "\n", encoding="utf-8")
            subprocess.run(
                [
                    "openssl",
                    "req",
                    "-x509",
                    "-newkey",
                    "rsa:2048",
                    "-nodes",
                    "-days",
                    "1",
                    "-subj",
                    "/CN=Different Android Signer",
                    "-keyout",
                    str(private_key),
                    "-out",
                    str(certificate),
                ],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                [
                    "openssl",
                    "pkcs12",
                    "-export",
                    "-out",
                    str(keystore),
                    "-inkey",
                    str(private_key),
                    "-in",
                    str(certificate),
                    "-name",
                    "kanana-bridge",
                    "-passout",
                    f"pass:{password}",
                ],
                check=True,
                capture_output=True,
            )
            environment = os.environ.copy()
            environment["KANANA_SIGNING_DIR"] = str(signing_dir)
            result = subprocess.run(
                [str(CREATE_SCRIPT)],
                check=False,
                capture_output=True,
                text=True,
                env=environment,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("does not match the pinned release certificate", result.stderr)
            self.assertFalse((signing_dir / "android-signing-key.base64").exists())


if __name__ == "__main__":
    unittest.main()
