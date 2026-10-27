import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


class OpsTests(unittest.TestCase):
    def test_external_model_server_rejects_example_api_key(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env = Path(directory) / "server.env"
            env.write_text(
                (ROOT / "ops/5600g/server.env.example").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            result = subprocess.run(
                ["bash", str(ROOT / "ops/5600g/run.sh")],
                env={**os.environ, "KANANA_SERVER_ENV": str(env)},
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("at least 32 characters", result.stderr)

    def test_model_install_preserves_env_and_restricts_permissions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "repo"
            (repo / "ops").mkdir(parents=True)
            shutil.copytree(ROOT / "ops/5600g", repo / "ops/5600g")
            home = root / "home"
            home.mkdir()
            fake_bin = root / "bin"
            fake_bin.mkdir()
            fake_python = fake_bin / "python3"
            fake_python.write_text(
                "#!/bin/sh\n"
                f"mkdir -p '{repo}/.venv/bin'\n"
                f"printf '#!/bin/sh\\nexit 0\\n' > '{repo}/.venv/bin/python'\n"
                f"chmod +x '{repo}/.venv/bin/python'\n",
                encoding="utf-8",
            )
            fake_python.chmod(0o755)
            fake_systemctl = fake_bin / "systemctl"
            fake_systemctl.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            fake_systemctl.chmod(0o755)
            env = {**os.environ, "HOME": str(home), "PATH": f"{fake_bin}:{os.environ['PATH']}"}
            install = repo / "ops/5600g/install.sh"
            subprocess.run(["bash", str(install)], env=env, check=True, capture_output=True)
            server_env = home / ".config/kanana-garden/server.env"
            self.assertEqual(stat.S_IMODE(server_env.stat().st_mode), 0o600)

            original = server_env.read_text(encoding="utf-8") + "CUSTOM=value\n"
            server_env.write_text(original, encoding="utf-8")
            server_env.chmod(0o644)
            subprocess.run(["bash", str(install)], env=env, check=True, capture_output=True)
            self.assertEqual(server_env.read_text(encoding="utf-8"), original)
            self.assertEqual(stat.S_IMODE(server_env.stat().st_mode), 0o600)

    def test_duckdns_config_reads_unterminated_token_and_preserves_job_nodes(self) -> None:
        script = (ROOT / "ops/report-host/apply-duckdns-config.sh").read_text(encoding="utf-8")
        store = (ROOT / "ops/report-host/store-duckdns-token.sh").read_text(encoding="utf-8")
        self.assertIn("printf '%s' \"$new_token\"", store)
        self.assertIn('token="$(<"$secret_file")', script)
        self.assertNotIn("IFS= read -r token <", script)
        self.assertIn('tree = ET.parse(source)', script)
        self.assertNotIn("<publishers/>", script)
        self.assertLess(script.index("Certbot DuckDNS 토큰 항목"), script.index("changes_started=1"))
        self.assertIn("rollback_on_exit", script)
        self.assertIn('mv -f "$job_tmp" "$jenkins_job"', script)

    def test_duckdns_jenkins_update_preserves_custom_configuration(self) -> None:
        script = (ROOT / "ops/report-host/apply-duckdns-config.sh").read_text(encoding="utf-8")
        marker = 'python3 - "$jenkins_job" "$job_tmp" <<\'PY\'\n'
        updater = script.split(marker, 1)[1].split("\nPY\n", 1)[0]
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.xml"
            destination = Path(directory) / "destination.xml"
            source.write_text(
                "<project><properties><custom/></properties><triggers>"
                "<customTrigger/></triggers><builders><hudson.tasks.Shell>"
                "<command>echo old; curl https://www.duckdns.org/update</command>"
                "</hudson.tasks.Shell></builders><publishers><customPublisher/>"
                "</publishers><buildWrappers><customWrapper/></buildWrappers></project>",
                encoding="utf-8",
            )
            with mock.patch.object(sys, "argv", ["update", str(source), str(destination)]):
                exec(compile(updater, "apply-duckdns-config.sh<python>", "exec"), {})
            updated = ET.parse(destination).getroot()
            self.assertIsNotNone(updated.find("properties/custom"))
            self.assertIsNotNone(updated.find("publishers/customPublisher"))
            self.assertIsNotNone(updated.find("buildWrappers/customWrapper"))
            self.assertIsNotNone(updated.find("triggers/customTrigger"))
            command = updated.findtext("builders/hudson.tasks.Shell/command")
            self.assertIn("/run/secrets/duckdns-token", command)
            self.assertNotIn("echo old", command)


if __name__ == "__main__":
    unittest.main()
