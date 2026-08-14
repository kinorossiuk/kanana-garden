import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from kanana_garden.client import KananaAPIError, KananaClient


class FakeOpenAIHandler(BaseHTTPRequestHandler):
    last_authorization = None
    last_payload = None
    last_user_agent = None

    def do_GET(self) -> None:
        type(self).last_user_agent = self.headers.get("User-Agent")
        if self.path == "/v1/models":
            self._send(
                200,
                {
                    "object": "list",
                    "data": [
                        {
                            "id": "kakaocorp/kanana-2-1.3b-instruct",
                            "object": "model",
                        }
                    ],
                },
            )
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path != "/v1/chat/completions":
            self._send(404, {"error": "not found"})
            return
        length = int(self.headers["Content-Length"])
        type(self).last_payload = json.loads(self.rfile.read(length))
        type(self).last_authorization = self.headers.get("Authorization")
        type(self).last_user_agent = self.headers.get("User-Agent")
        self._send(
            200,
            {
                "model": "kakaocorp/kanana-2-1.3b-instruct",
                "choices": [{"message": {"role": "assistant", "content": "결과입니다."}}],
                "usage": {
                    "prompt_tokens": 11,
                    "completion_tokens": 4,
                    "noise": "drop",
                    "boolean": True,
                    "negative": -1,
                },
            },
        )

    def log_message(self, format: str, *args: object) -> None:
        return

    def _send(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class ClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeOpenAIHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        host, port = cls.server.server_address
        cls.base_url = f"http://{host}:{port}/v1"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def test_list_models(self) -> None:
        client = KananaClient(self.base_url)
        self.assertEqual(
            client.list_models(),
            ["kakaocorp/kanana-2-1.3b-instruct"],
        )

    def test_chat_payload_auth_and_result(self) -> None:
        client = KananaClient(self.base_url, api_key="secret")
        result = client.chat(
            model="kakaocorp/kanana-2-1.3b-instruct",
            messages=[{"role": "user", "content": "안녕"}],
            generation={"temperature": 0.2, "max_tokens": 100},
        )
        self.assertEqual(result.content, "결과입니다.")
        self.assertEqual(result.usage, {"prompt_tokens": 11, "completion_tokens": 4})
        self.assertEqual(FakeOpenAIHandler.last_authorization, "Bearer secret")
        self.assertEqual(FakeOpenAIHandler.last_user_agent, "kanana-garden/0.2.1")
        self.assertFalse(FakeOpenAIHandler.last_payload["stream"])

    def test_http_error_is_readable(self) -> None:
        client = KananaClient(f"{self.base_url}/wrong")
        with self.assertRaisesRegex(KananaAPIError, "HTTP 404"):
            client.list_models()

    def test_rejects_non_http_base_url(self) -> None:
        with self.assertRaisesRegex(ValueError, "http"):
            KananaClient("localhost:8000/v1")


if __name__ == "__main__":
    unittest.main()
