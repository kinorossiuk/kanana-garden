import json
import threading
import unittest
from urllib import error, request

from kanana_garden.client import KananaClient
from kanana_garden.local_server import LocalModelServer


MODEL = "kakaocorp/kanana-2-1.3b-instruct"


class FakeBackend:
    model_id = MODEL
    revision = "test-revision"
    dtype = "float32"
    host_profile = "ryzen-5-5600g"

    def __init__(self) -> None:
        self.last_messages = None

    def generate(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float,
        top_p: float,
        max_tokens: int,
    ) -> tuple[str, dict[str, int]]:
        self.last_messages = messages
        return "로컬 카나나 응답", {
            "prompt_tokens": 5,
            "completion_tokens": 4,
            "total_tokens": 9,
        }


class LocalServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.backend = FakeBackend()
        cls.server = LocalModelServer(("127.0.0.1", 0), cls.backend, "test-key")
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        host, port = cls.server.server_address
        cls.root_url = f"http://{host}:{port}"
        cls.base_url = f"{cls.root_url}/v1"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def test_openai_client_round_trip(self) -> None:
        client = KananaClient(self.base_url, api_key="test-key")
        self.assertEqual(client.list_models(), [MODEL])
        runtime_info = client.runtime_info(MODEL)
        self.assertEqual(runtime_info["runtime"]["revision"], "test-revision")
        self.assertEqual(runtime_info["runtime"]["dtype"], "float32")
        self.assertTrue(runtime_info["runtime"]["session_id"])
        result = client.chat(
            model=MODEL,
            messages=[{"role": "user", "content": "안녕"}],
            generation={"temperature": 0.2, "top_p": 0.9, "max_tokens": 20},
        )
        self.assertEqual(result.content, "로컬 카나나 응답")
        self.assertEqual(result.usage["total_tokens"], 9)
        self.assertEqual(self.backend.last_messages[0]["content"], "안녕")

    def test_requires_api_key(self) -> None:
        with self.assertRaises(error.HTTPError) as raised:
            request.urlopen(f"{self.base_url}/models", timeout=2)
        self.assertEqual(raised.exception.code, 401)

    def test_rejects_streaming(self) -> None:
        body = json.dumps(
            {
                "model": MODEL,
                "messages": [{"role": "user", "content": "안녕"}],
                "stream": True,
            }
        ).encode("utf-8")
        api_request = request.Request(
            f"{self.base_url}/chat/completions",
            data=body,
            headers={
                "Authorization": "Bearer test-key",
                "Content-Type": "application/json",
            },
        )
        with self.assertRaises(error.HTTPError) as raised:
            request.urlopen(api_request, timeout=2)
        self.assertEqual(raised.exception.code, 400)
        response = json.loads(raised.exception.read())
        self.assertIn("stream=true", response["error"]["message"])


if __name__ == "__main__":
    unittest.main()
