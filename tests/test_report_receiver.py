import hashlib
import http.client
import json
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path

from kanana_garden.report_receiver import (
    REPORT_HEADER,
    ReportHTTPServer,
    ReportReceiverError,
    store_stage_zero_report,
    validate_receiver_token,
)


TOKEN = "a" * 64
RECEIVED_AT = datetime(2026, 8, 14, 3, 4, 5, tzinfo=timezone.utc)
REPORT = (REPORT_HEADER + "앱 버전: 0.0.1-alpha.3\n- [PASS] 볼륨 올리기\n").encode()


class ReportReceiverTests(unittest.TestCase):
    def test_token_must_be_long_and_single_line(self) -> None:
        self.assertEqual(validate_receiver_token(TOKEN), TOKEN)
        for value in (None, "short", "x" * 32 + "\n"):
            with self.subTest(value=value):
                with self.assertRaises(ReportReceiverError):
                    validate_receiver_token(value)

    def test_store_writes_report_and_hash_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "inbox"
            metadata = store_stage_zero_report(
                REPORT,
                output,
                received_at=RECEIVED_AT,
                nonce="abcd1234",
            )
            self.assertEqual(metadata["report_id"], "20260814T030405Z-abcd1234")
            self.assertEqual(
                metadata["sha256"], f"sha256:{hashlib.sha256(REPORT).hexdigest()}"
            )
            self.assertEqual((output / f"{metadata['report_id']}.txt").read_bytes(), REPORT)
            stored = json.loads(
                (output / f"{metadata['report_id']}.json").read_text(encoding="utf-8")
            )
            self.assertEqual(stored["bytes"], len(REPORT))

    def test_http_receiver_rejects_bad_token_and_accepts_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            server = ReportHTTPServer(("127.0.0.1", 0), TOKEN, Path(directory))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                connection = http.client.HTTPConnection(*server.server_address, timeout=5)
                connection.request(
                    "POST",
                    "/v1/uis7862s/reports",
                    body=REPORT,
                    headers={
                        "Authorization": "Bearer wrong",
                        "Content-Type": "text/plain; charset=utf-8",
                    },
                )
                self.assertEqual(connection.getresponse().status, 401)
                connection.close()

                connection = http.client.HTTPConnection(*server.server_address, timeout=5)
                connection.request(
                    "POST",
                    "/v1/uis7862s/reports",
                    body=REPORT,
                    headers={
                        "Authorization": f"Bearer {TOKEN}",
                        "Content-Type": "text/plain; charset=utf-8",
                    },
                )
                response = connection.getresponse()
                body = json.loads(response.read())
                self.assertEqual(response.status, 201)
                self.assertTrue(body["ok"])
                self.assertTrue(next(Path(directory).glob("*.txt")).is_file())
                connection.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
