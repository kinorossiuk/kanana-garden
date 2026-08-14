"""Bounded, token-authenticated UIS7862S report receiver for a local tunnel origin."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


REPORT_ENDPOINT = "/v1/uis7862s/reports"
HEALTH_ENDPOINT = "/health"
REPORT_HEADER = "Kanana Garden UIS7862S 0단계 테스트\n"
MAX_REPORT_BYTES = 64 * 1024
MAX_TOKEN_LENGTH = 512


class ReportReceiverError(RuntimeError):
    """A safe configuration or submitted-report error."""


def validate_receiver_token(token: str | None) -> str:
    if (
        not isinstance(token, str)
        or not 32 <= len(token) <= MAX_TOKEN_LENGTH
        or "\n" in token
        or "\r" in token
    ):
        raise ReportReceiverError("KANANA_REPORT_TOKEN은 줄바꿈 없는 32~512자여야 합니다.")
    return token


def store_stage_zero_report(
    payload: bytes,
    output_dir: Path,
    *,
    received_at: datetime | None = None,
    nonce: str | None = None,
) -> dict[str, Any]:
    if not payload:
        raise ReportReceiverError("보고서가 비어 있습니다.")
    if len(payload) > MAX_REPORT_BYTES:
        raise ReportReceiverError("보고서가 허용 크기 64 KiB를 초과했습니다.")
    try:
        report_text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ReportReceiverError("보고서는 올바른 UTF-8 텍스트여야 합니다.") from exc
    if not report_text.startswith(REPORT_HEADER):
        raise ReportReceiverError("보고서 헤더가 예상 형식과 다릅니다.")
    if "\0" in report_text:
        raise ReportReceiverError("보고서에 NUL 문자를 사용할 수 없습니다.")

    timestamp = (received_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    rendered_time = timestamp.isoformat(timespec="seconds").replace("+00:00", "Z")
    digest = hashlib.sha256(payload).hexdigest()
    safe_nonce = nonce or secrets.token_hex(4)
    if not safe_nonce.isalnum() or len(safe_nonce) > 32:
        raise ReportReceiverError("내부 보고서 nonce가 유효하지 않습니다.")
    report_id = f"{timestamp.strftime('%Y%m%dT%H%M%SZ')}-{safe_nonce}"
    report_path = output_dir / f"{report_id}.txt"
    metadata_path = output_dir / f"{report_id}.json"
    if report_path.exists() or metadata_path.exists():
        raise ReportReceiverError(f"보고서 ID가 이미 있습니다: {report_id}")

    metadata = {
        "schema_version": 1,
        "kind": "kanana-garden-uis7862s-stage-zero-submission",
        "report_id": report_id,
        "received_at": rendered_time,
        "report_path": str(report_path),
        "bytes": len(payload),
        "sha256": f"sha256:{digest}",
        "transport": "https-reverse-proxy",
    }
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        report_path.write_bytes(payload)
        metadata_path.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        for created in (report_path, metadata_path):
            try:
                created.unlink(missing_ok=True)
            except OSError:
                pass
        raise ReportReceiverError(f"보고서를 저장하지 못했습니다: {exc}") from exc
    return metadata


class ReportHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, server_address: tuple[str, int], token: str, output_dir: Path):
        self.receiver_token = validate_receiver_token(token)
        self.output_dir = output_dir
        super().__init__(server_address, ReportRequestHandler)


class ReportRequestHandler(BaseHTTPRequestHandler):
    server: ReportHTTPServer
    protocol_version = "HTTP/1.1"
    server_version = "KananaReportReceiver/1"
    sys_version = ""

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        if self.path != HEALTH_ENDPOINT:
            self._json_response(404, {"ok": False, "error": "not_found"})
            return
        self._json_response(200, {"ok": True, "service": "kanana-report-receiver"})

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
        if self.path != REPORT_ENDPOINT:
            self._json_response(404, {"ok": False, "error": "not_found"})
            return
        if not self._authorized():
            self._json_response(
                401,
                {"ok": False, "error": "unauthorized"},
                extra_headers={"WWW-Authenticate": "Bearer"},
            )
            return
        content_type = self.headers.get_content_type()
        if content_type != "text/plain":
            self._json_response(415, {"ok": False, "error": "text_plain_required"})
            return
        if self.headers.get("Transfer-Encoding"):
            self._json_response(400, {"ok": False, "error": "chunked_not_allowed"})
            return
        raw_length = self.headers.get("Content-Length")
        try:
            content_length = int(raw_length or "")
        except ValueError:
            self._json_response(411, {"ok": False, "error": "content_length_required"})
            return
        if content_length <= 0:
            self._json_response(400, {"ok": False, "error": "empty_report"})
            return
        if content_length > MAX_REPORT_BYTES:
            self._json_response(413, {"ok": False, "error": "report_too_large"})
            return
        payload = self.rfile.read(content_length)
        if len(payload) != content_length:
            self._json_response(400, {"ok": False, "error": "incomplete_report"})
            return
        try:
            report = store_stage_zero_report(payload, self.server.output_dir)
        except ReportReceiverError as error:
            self._json_response(400, {"ok": False, "error": str(error)})
            return
        self._json_response(
            201,
            {
                "ok": True,
                "report_id": report["report_id"],
                "sha256": report["sha256"],
            },
        )

    def _authorized(self) -> bool:
        authorization = self.headers.get("Authorization", "")
        prefix = "Bearer "
        if not authorization.startswith(prefix):
            return False
        return hmac.compare_digest(
            authorization[len(prefix) :],
            self.server.receiver_token,
        )

    def _json_response(
        self,
        status: int,
        value: dict[str, Any],
        *,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        payload = (json.dumps(value, ensure_ascii=False) + "\n").encode("utf-8")
        self.close_connection = True
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        for name, header_value in (extra_headers or {}).items():
            self.send_header(name, header_value)
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:
        # BaseHTTPRequestHandler never logs request headers; retain only its bounded line log.
        super().log_message(format, *args)


def serve_report_receiver(
    *,
    host: str,
    port: int,
    token: str,
    output_dir: Path,
) -> None:
    if host not in {"127.0.0.1", "::1", "localhost"}:
        raise ReportReceiverError(
            "보고서 수신기는 직접 인터넷에 노출하지 말고 loopback에만 바인딩하세요."
        )
    if not 1 <= port <= 65535:
        raise ReportReceiverError("수신 포트는 1 이상 65535 이하여야 합니다.")
    server = ReportHTTPServer((host, port), token, output_dir)
    try:
        print(f"Kanana report receiver: http://{host}:{port}")
        print(f"Report directory: {output_dir}")
        server.serve_forever()
    finally:
        server.server_close()
