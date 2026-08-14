"""Download and verify OTA artifacts without ever flashing a device."""

from __future__ import annotations

import hashlib
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO, Callable

from .recipe import RecipeError


VERSION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")


def _safe_source_url(value: str, *, allow_http: bool) -> tuple[str, str]:
    try:
        parts = urllib.parse.urlsplit(value)
        parts.port
    except ValueError as exc:
        raise RecipeError(f"OTA URL이 올바르지 않습니다: {exc}") from exc
    allowed_schemes = {"https", "http"} if allow_http else {"https"}
    if parts.scheme not in allowed_schemes or parts.hostname is None:
        hint = "http는 --allow-http를 명시해야 합니다." if not allow_http else ""
        raise RecipeError(f"OTA URL은 허용된 HTTP(S) 주소여야 합니다. {hint}".strip())
    if parts.username is not None or parts.password is not None:
        raise RecipeError("OTA URL에 사용자명이나 비밀번호를 넣을 수 없습니다.")
    sanitized = urllib.parse.urlunsplit(
        (parts.scheme, parts.netloc, parts.path, "", "")
    )
    return value, sanitized


def _expected_digest(value: str) -> str:
    normalized = value.removeprefix("sha256:")
    if SHA256_PATTERN.fullmatch(normalized) is None:
        raise RecipeError("--sha256은 64자리 SHA-256 16진수여야 합니다.")
    return normalized.lower()


def _filename_from_url(url: str) -> str:
    name = Path(urllib.parse.unquote(urllib.parse.urlsplit(url).path)).name
    if not name or name in {".", ".."}:
        return "update.zip"
    return name


def _checked_filename(value: str) -> str:
    if Path(value).name != value or value in {"", ".", ".."}:
        raise RecipeError("--filename은 디렉터리 없는 파일명이어야 합니다.")
    return value


def _timestamp(value: datetime | None = None) -> str:
    timestamp = (value or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return timestamp.isoformat(timespec="seconds").replace("+00:00", "Z")


def download_ota(
    *,
    version: str,
    url: str,
    sha256: str,
    output_dir: Path = Path("var/ota"),
    filename: str | None = None,
    allow_http: bool = False,
    timeout: float = 120.0,
    checked_at: datetime | None = None,
    opener: Callable[..., BinaryIO] | None = None,
) -> dict[str, Any]:
    """Stream a pinned OTA to a versioned directory and write its manifest."""
    if VERSION_PATTERN.fullmatch(version) is None:
        raise RecipeError(
            "OTA version은 영문자·숫자로 시작하는 80자 이하의 "
            "영문자/숫자/점/밑줄/하이픈이어야 합니다."
        )
    if timeout <= 0:
        raise RecipeError("OTA 다운로드 제한 시간은 0보다 커야 합니다.")
    source_url, sanitized_url = _safe_source_url(url, allow_http=allow_http)
    expected = _expected_digest(sha256)
    artifact_name = _checked_filename(filename or _filename_from_url(source_url))
    version_dir = output_dir / version
    target = version_dir / artifact_name
    manifest_path = version_dir / "manifest.json"
    temporary = version_dir / f".{artifact_name}.part"
    if target.exists() or manifest_path.exists() or temporary.exists():
        raise RecipeError(
            f"OTA {version} 저장 위치가 이미 사용 중입니다: {version_dir}"
        )
    try:
        version_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise RecipeError(f"OTA 저장 디렉터리를 만들 수 없습니다: {exc}") from exc

    request = urllib.request.Request(
        source_url,
        headers={"User-Agent": "kanana-garden-ota/1"},
    )
    open_url = opener or urllib.request.urlopen
    digest = hashlib.sha256()
    size = 0
    final_url = sanitized_url
    try:
        with open_url(request, timeout=timeout) as response, temporary.open("xb") as file:
            geturl = getattr(response, "geturl", None)
            if callable(geturl):
                _, final_url = _safe_source_url(geturl(), allow_http=allow_http)
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                file.write(chunk)
                digest.update(chunk)
                size += len(chunk)
        actual = digest.hexdigest()
        if actual != expected:
            raise RecipeError(
                "OTA SHA-256 불일치: "
                f"expected={expected}, actual={actual}. 임시 파일은 삭제했습니다."
            )
        temporary.replace(target)
    except (OSError, urllib.error.URLError) as exc:
        if temporary.exists():
            temporary.unlink()
        raise RecipeError(f"OTA 다운로드 실패: {exc}") from exc
    except RecipeError:
        if temporary.exists():
            temporary.unlink()
        raise

    manifest = {
        "schema_version": 1,
        "kind": "kanana-garden-ota-artifact",
        "downloaded_at": _timestamp(checked_at),
        "version": version,
        "source_url": sanitized_url,
        "final_url": final_url,
        "artifact": artifact_name,
        "bytes": size,
        "sha256": f"sha256:{expected}",
        "state": "downloaded-not-flashed",
    }
    try:
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        raise RecipeError(f"OTA manifest를 쓸 수 없습니다: {exc}") from exc
    return {**manifest, "path": str(target), "manifest": str(manifest_path)}


def verify_ota(path: Path) -> dict[str, Any]:
    """Re-hash an OTA using the sibling manifest as the source of truth."""
    manifest_path = path if path.name == "manifest.json" else path.parent / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise RecipeError(f"OTA manifest를 읽을 수 없습니다: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RecipeError(f"OTA manifest JSON 오류: {exc.msg}") from exc
    if not isinstance(manifest, dict) or manifest.get("kind") != "kanana-garden-ota-artifact":
        raise RecipeError("지원하는 OTA manifest가 아닙니다.")
    artifact = manifest.get("artifact")
    expected = manifest.get("sha256")
    if not isinstance(artifact, str) or not isinstance(expected, str):
        raise RecipeError("OTA manifest에 artifact 또는 sha256이 없습니다.")
    artifact_path = manifest_path.parent / artifact
    digest = hashlib.sha256()
    size = 0
    try:
        with artifact_path.open("rb") as file:
            while True:
                chunk = file.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
                size += len(chunk)
    except OSError as exc:
        raise RecipeError(f"OTA 파일을 읽을 수 없습니다: {exc}") from exc
    actual = f"sha256:{digest.hexdigest()}"
    size_matches = manifest.get("bytes") == size
    return {
        "passed": actual == expected and size_matches,
        "version": manifest.get("version"),
        "path": str(artifact_path),
        "expected_sha256": expected,
        "actual_sha256": actual,
        "expected_bytes": manifest.get("bytes"),
        "actual_bytes": size,
        "size_matches": size_matches,
    }
