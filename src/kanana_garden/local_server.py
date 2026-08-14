"""A small OpenAI-compatible server for the official Transformers model."""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Protocol


DEFAULT_REVISION = "c10f59f16af7e3e3a9b2801f528a98c1e4ff6171"


class GenerationBackend(Protocol):
    model_id: str

    def generate(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float,
        top_p: float,
        max_tokens: int,
    ) -> tuple[str, dict[str, int]]:
        ...


class RequestError(ValueError):
    pass


class TransformersBackend:
    """Lazy imports keep the base CLI dependency-free."""

    def __init__(
        self,
        *,
        model_id: str,
        revision: str,
        max_input_tokens: int,
        max_output_tokens: int,
        threads: int,
        dtype: str,
    ) -> None:
        try:
            import torch
            import transformers
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as exc:
            raise RuntimeError(
                "로컬 모델 의존성이 없습니다. "
                "python3 -m pip install -e '.[server]'를 실행하세요."
            ) from exc

        version = tuple(
            int(part) for part in transformers.__version__.split(".")[:2]
        )
        if version < (4, 57):
            raise RuntimeError("Kanana-2 SLM에는 transformers 4.57 이상이 필요합니다.")

        if dtype not in {"auto", "float32", "bfloat16"}:
            raise RuntimeError(f"지원하지 않는 dtype입니다: {dtype}")
        if dtype == "bfloat16":
            try:
                probe = torch.ones((2, 2), dtype=torch.bfloat16)
                torch.matmul(probe, probe)
            except RuntimeError as exc:
                raise RuntimeError(
                    "이 PyTorch 빌드는 CPU BF16 행렬 연산을 지원하지 않습니다. "
                    "--dtype float32로 다시 시도하세요."
                ) from exc

        self.model_id = model_id
        self.max_input_tokens = max_input_tokens
        self.max_output_tokens = max_output_tokens
        self.torch = torch
        self._generation_lock = threading.Lock()
        torch.set_num_threads(threads)
        self.tokenizer = AutoTokenizer.from_pretrained(
            model_id,
            revision=revision,
            trust_remote_code=True,
        )
        torch_dtype: str | Any = "auto"
        if dtype == "float32":
            torch_dtype = torch.float32
        elif dtype == "bfloat16":
            torch_dtype = torch.bfloat16
        self.model = AutoModelForCausalLM.from_pretrained(
            model_id,
            revision=revision,
            trust_remote_code=True,
            torch_dtype=torch_dtype,
            low_cpu_mem_usage=True,
        )
        self.model.eval()

    def generate(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float,
        top_p: float,
        max_tokens: int,
    ) -> tuple[str, dict[str, int]]:
        prompt = self.tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
        inputs = self.tokenizer(prompt, return_tensors="pt")
        prompt_tokens = int(inputs["input_ids"].shape[-1])
        if prompt_tokens > self.max_input_tokens:
            raise RequestError(
                f"입력이 {prompt_tokens}토큰입니다. "
                f"이 장치의 제한은 {self.max_input_tokens}토큰입니다."
            )

        output_limit = min(max_tokens, self.max_output_tokens)
        generation: dict[str, Any] = {
            "max_new_tokens": output_limit,
            "do_sample": temperature > 0,
            "pad_token_id": self.tokenizer.eos_token_id,
        }
        if temperature > 0:
            generation["temperature"] = temperature
            generation["top_p"] = top_p

        # A single CPU model instance is deliberately serialized. Concurrent
        # generations multiply memory pressure and make latency evidence noisy.
        with self._generation_lock, self.torch.inference_mode():
            output = self.model.generate(**inputs, **generation)
        generated = output[0, prompt_tokens:]
        content = self.tokenizer.decode(generated, skip_special_tokens=True)
        completion_tokens = int(generated.shape[-1])
        return content, {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        }


class LocalModelServer(ThreadingHTTPServer):
    def __init__(
        self,
        server_address: tuple[str, int],
        backend: GenerationBackend,
        api_key: str | None,
    ) -> None:
        super().__init__(server_address, LocalModelHandler)
        self.backend = backend
        self.api_key = api_key


class LocalModelHandler(BaseHTTPRequestHandler):
    server: LocalModelServer

    def do_GET(self) -> None:
        if not self._authorized():
            return
        if self.path == "/health":
            self._json(HTTPStatus.OK, {"status": "ok", "model": self.server.backend.model_id})
            return
        if self.path == "/v1/models":
            self._json(
                HTTPStatus.OK,
                {
                    "object": "list",
                    "data": [
                        {
                            "id": self.server.backend.model_id,
                            "object": "model",
                            "owned_by": "kakaocorp",
                        }
                    ],
                },
            )
            return
        self._json(HTTPStatus.NOT_FOUND, {"error": {"message": "Not found"}})

    def do_POST(self) -> None:
        if not self._authorized():
            return
        if self.path != "/v1/chat/completions":
            self._json(HTTPStatus.NOT_FOUND, {"error": {"message": "Not found"}})
            return
        try:
            payload = self._read_payload()
            messages = self._messages(payload)
            if payload.get("stream", False):
                raise RequestError("stream=true는 아직 지원하지 않습니다.")
            model = payload.get("model", self.server.backend.model_id)
            if model != self.server.backend.model_id:
                raise RequestError(f"서버에 없는 모델입니다: {model}")
            temperature = _number(payload.get("temperature", 0.2), "temperature", 0, 2)
            top_p = _number(payload.get("top_p", 0.9), "top_p", 0, 1, lower_open=True)
            max_tokens = _integer(payload.get("max_tokens", 512), "max_tokens", 1, 32768)
            content, usage = self.server.backend.generate(
                messages,
                temperature=temperature,
                top_p=top_p,
                max_tokens=max_tokens,
            )
        except RequestError as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"error": {"message": str(exc)}})
            return
        except Exception as exc:
            self.log_error("generation failed: %s", exc)
            self._json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": {"message": "모델 생성 중 오류가 발생했습니다."}},
            )
            return

        self._json(
            HTTPStatus.OK,
            {
                "id": f"chatcmpl-{uuid.uuid4().hex}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": self.server.backend.model_id,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": content},
                        "finish_reason": "stop",
                    }
                ],
                "usage": usage,
            },
        )

    def _authorized(self) -> bool:
        if self.server.api_key is None:
            return True
        if self.headers.get("Authorization") == f"Bearer {self.server.api_key}":
            return True
        self._json(HTTPStatus.UNAUTHORIZED, {"error": {"message": "Unauthorized"}})
        return False

    def _read_payload(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise RequestError("Content-Length가 올바르지 않습니다.") from exc
        if not 0 < length <= 2 * 1024 * 1024:
            raise RequestError("요청 본문은 1바이트 이상 2MiB 이하여야 합니다.")
        try:
            value = json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise RequestError("요청 본문이 올바른 UTF-8 JSON이 아닙니다.") from exc
        if not isinstance(value, dict):
            raise RequestError("요청 본문의 최상위 값은 JSON 객체여야 합니다.")
        return value

    def _messages(self, payload: dict[str, Any]) -> list[dict[str, str]]:
        messages = payload.get("messages")
        if not isinstance(messages, list) or not messages:
            raise RequestError("messages는 비어 있지 않은 배열이어야 합니다.")
        cleaned: list[dict[str, str]] = []
        for index, message in enumerate(messages):
            if not isinstance(message, dict):
                raise RequestError(f"messages[{index}]는 객체여야 합니다.")
            role = message.get("role")
            content = message.get("content")
            if role not in {"system", "user", "assistant"}:
                raise RequestError(f"messages[{index}].role이 올바르지 않습니다.")
            if not isinstance(content, str) or not content:
                raise RequestError(f"messages[{index}].content가 비어 있습니다.")
            cleaned.append({"role": role, "content": content})
        return cleaned

    def _json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _number(
    value: Any,
    name: str,
    minimum: float,
    maximum: float,
    *,
    lower_open: bool = False,
) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise RequestError(f"{name}은 숫자여야 합니다.")
    if (value <= minimum if lower_open else value < minimum) or value > maximum:
        comparator = "초과" if lower_open else "이상"
        raise RequestError(f"{name}은 {minimum} {comparator} {maximum} 이하여야 합니다.")
    return float(value)


def _integer(value: Any, name: str, minimum: int, maximum: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise RequestError(f"{name}은 정수여야 합니다.")
    if not minimum <= value <= maximum:
        raise RequestError(f"{name}은 {minimum} 이상 {maximum} 이하여야 합니다.")
    return value


def serve(
    *,
    host: str,
    port: int,
    model_id: str,
    revision: str,
    max_input_tokens: int,
    max_output_tokens: int,
    threads: int,
    dtype: str,
    api_key: str | None,
) -> None:
    if host not in {"127.0.0.1", "localhost", "::1"} and not api_key:
        raise RuntimeError("외부 주소에 바인딩하려면 --api-key가 필요합니다.")
    backend = TransformersBackend(
        model_id=model_id,
        revision=revision,
        max_input_tokens=max_input_tokens,
        max_output_tokens=max_output_tokens,
        threads=threads,
        dtype=dtype,
    )
    server = LocalModelServer((host, port), backend, api_key)
    print(f"Powered by Kanana — http://{host}:{port}/v1")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
