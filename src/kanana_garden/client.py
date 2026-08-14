"""Small OpenAI-compatible HTTP client implemented with the standard library."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib import error, request


class KananaAPIError(RuntimeError):
    """A connection, protocol, or remote API failure."""


@dataclass(frozen=True)
class ChatResult:
    content: str
    model: str
    usage: dict[str, int]


class KananaClient:
    def __init__(
        self,
        base_url: str = "http://localhost:8000/v1",
        api_key: str | None = None,
        timeout: float = 120.0,
    ) -> None:
        if not base_url.startswith(("http://", "https://")):
            raise ValueError("base_url은 http:// 또는 https://로 시작해야 합니다.")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "kanana-garden/0.1.0",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _json_request(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        api_request = request.Request(
            f"{self.base_url}{path}",
            data=body,
            headers=self._headers(),
            method=method,
        )
        try:
            with request.urlopen(api_request, timeout=self.timeout) as response:
                raw = response.read()
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise KananaAPIError(
                f"카나나 서버가 HTTP {exc.code}을 반환했습니다: {detail[:500]}"
            ) from exc
        except error.URLError as exc:
            raise KananaAPIError(
                f"카나나 서버({self.base_url})에 연결할 수 없습니다: {exc.reason}"
            ) from exc
        except TimeoutError as exc:
            raise KananaAPIError(
                f"카나나 서버 응답이 {self.timeout:g}초 안에 오지 않았습니다."
            ) from exc

        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise KananaAPIError("카나나 서버가 올바른 JSON을 반환하지 않았습니다.") from exc
        if not isinstance(parsed, dict):
            raise KananaAPIError("카나나 서버 응답의 최상위 값이 JSON 객체가 아닙니다.")
        return parsed

    def list_models(self) -> list[str]:
        response = self._json_request("GET", "/models")
        return self._model_ids(response)

    @staticmethod
    def _model_ids(response: dict[str, Any]) -> list[str]:
        data = response.get("data")
        if not isinstance(data, list):
            raise KananaAPIError("모델 목록 응답에 data 배열이 없습니다.")
        model_ids = [
            item["id"]
            for item in data
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        ]
        if not model_ids:
            raise KananaAPIError("서버가 노출한 모델 ID가 없습니다.")
        return model_ids

    def runtime_info(self, model: str) -> dict[str, Any]:
        """Read immutable runtime identity exposed by ``serve-local``."""

        response = self._json_request("GET", "/models")
        exposed_models = self._model_ids(response)
        data = response["data"]
        record = next(
            (
                item
                for item in data
                if isinstance(item, dict) and item.get("id") == model
            ),
            None,
        )
        if record is None:
            return {"exposed_models": exposed_models, "runtime": {}}
        runtime = record.get("kanana_garden")
        if not isinstance(runtime, dict):
            raise KananaAPIError(
                "5600G 기준선에는 kanana-garden serve-local의 런타임 "
                "메타데이터가 필요합니다."
            )
        clean_runtime: dict[str, str] = {}
        for name in ("session_id", "revision", "dtype", "host_profile"):
            value = runtime.get(name)
            if isinstance(value, str) and value:
                clean_runtime[name] = value
        missing = sorted(
            {"session_id", "revision", "dtype"} - clean_runtime.keys()
        )
        if missing:
            raise KananaAPIError(
                "서버 런타임 메타데이터가 불완전합니다: " + ", ".join(missing)
            )
        return {"exposed_models": exposed_models, "runtime": clean_runtime}

    def chat(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        generation: dict[str, int | float],
    ) -> ChatResult:
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            **generation,
            "stream": False,
        }
        response = self._json_request("POST", "/chat/completions", payload)
        try:
            content = response["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise KananaAPIError("채팅 응답에 choices[0].message.content가 없습니다.") from exc
        if not isinstance(content, str):
            raise KananaAPIError("채팅 응답 content가 문자열이 아닙니다.")

        response_model = response.get("model", model)
        if not isinstance(response_model, str):
            response_model = model
        usage = response.get("usage", {})
        clean_usage = {
            key: value
            for key, value in usage.items()
            if isinstance(key, str)
            and isinstance(value, int)
            and not isinstance(value, bool)
            and value >= 0
        } if isinstance(usage, dict) else {}
        return ChatResult(content=content, model=response_model, usage=clean_usage)
