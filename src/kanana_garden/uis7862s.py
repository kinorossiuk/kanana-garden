"""ADB diagnostics and reproducible evidence capture for UIS7862S head units."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence


GIB = 1024**3
MIN_MEMORY_BYTES = 3 * GIB
MIN_DATA_FREE_BYTES = 2 * GIB
PROFILE = "uis7862s-android-head-unit"
PACKAGE_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+$")
SOC_MARKERS = ("uis7862", "ums512")
SENSITIVE_PROPERTY_MARKERS = (
    "android_id",
    "bluetooth.address",
    "iccid",
    "imei",
    "imsi",
    "macaddr",
    "meid",
    "serialno",
    "subscriber",
)

TRIAGE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "crash",
        re.compile(
            r"fatal exception|fatal signal|am_crash|force finishing activity",
            re.IGNORECASE,
        ),
    ),
    (
        "anr",
        re.compile(r"\banr in\b|am_anr|input dispatching timed out", re.IGNORECASE),
    ),
    (
        "memory",
        re.compile(
            r"outofmemoryerror|lowmemorykiller|low memory|\blmkd\b|memory pressure",
            re.IGNORECASE,
        ),
    ),
    ("watchdog", re.compile(r"\bwatchdog\b", re.IGNORECASE)),
    (
        "thermal",
        re.compile(r"thermal shutdown|overheat|throttl", re.IGNORECASE),
    ),
)


class AdbError(RuntimeError):
    """An actionable ADB discovery or command error."""


@dataclass(frozen=True)
class AdbResult:
    command: tuple[str, ...]
    returncode: int
    stdout: bytes
    stderr: str
    duration_seconds: float

    @property
    def text(self) -> str:
        return self.stdout.decode("utf-8", errors="replace")


def parse_adb_devices(output: str) -> list[dict[str, str]]:
    """Parse ``adb devices -l`` without treating daemon chatter as a device."""
    devices: list[dict[str, str]] = []
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("List of devices") or line.startswith("*"):
            continue
        fields = line.split()
        if len(fields) < 2:
            continue
        details = {"serial": fields[0], "state": fields[1]}
        for field in fields[2:]:
            key, separator, value = field.partition(":")
            if separator:
                details[key] = value
        devices.append(details)
    return devices


class AdbClient:
    """Small dependency-free ADB wrapper that never invokes a local shell."""

    def __init__(
        self,
        serial: str | None = None,
        adb_path: str | Path | None = None,
        timeout: float = 30.0,
    ) -> None:
        executable = str(adb_path) if adb_path is not None else shutil.which("adb")
        if not executable:
            raise AdbError(
                "adb를 찾을 수 없습니다. Android platform-tools를 설치하거나 "
                "--adb-path를 지정하세요."
            )
        if timeout <= 0:
            raise AdbError("ADB 제한 시간은 0보다 커야 합니다.")
        self.executable = executable
        self.timeout = timeout
        self.serial = self._select_device(serial)

    def _invoke(
        self,
        arguments: Sequence[str],
        *,
        include_serial: bool,
        timeout: float | None = None,
    ) -> AdbResult:
        command = [self.executable]
        if include_serial:
            command.extend(("-s", self.serial))
        command.extend(arguments)
        started = time.monotonic()
        try:
            result = subprocess.run(
                command,
                check=False,
                capture_output=True,
                timeout=timeout or self.timeout,
            )
        except FileNotFoundError as exc:
            raise AdbError(f"adb 실행 파일이 없습니다: {self.executable}") from exc
        except subprocess.TimeoutExpired as exc:
            joined = " ".join(arguments)
            raise AdbError(f"ADB 명령 제한 시간 초과: {joined}") from exc
        return AdbResult(
            command=tuple(arguments),
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr.decode("utf-8", errors="replace"),
            duration_seconds=round(time.monotonic() - started, 6),
        )

    def _select_device(self, requested_serial: str | None) -> str:
        result = self._invoke(
            ("devices", "-l"), include_serial=False, timeout=self.timeout
        )
        if result.returncode != 0:
            raise AdbError(f"adb devices 실패: {result.stderr.strip() or result.text.strip()}")
        devices = parse_adb_devices(result.text)
        if requested_serial:
            matches = [item for item in devices if item["serial"] == requested_serial]
            if not matches:
                raise AdbError(f"요청한 ADB 장치를 찾을 수 없습니다: {requested_serial}")
            selected = matches[0]
        else:
            usable = [item for item in devices if item["state"] == "device"]
            if not usable:
                states = ", ".join(
                    f"{item['serial']}={item['state']}" for item in devices
                )
                detail = states or "연결된 장치 없음"
                raise AdbError(
                    f"사용 가능한 ADB 장치가 없습니다 ({detail}). "
                    "USB 디버깅 승인 상태를 확인하세요."
                )
            if len(usable) > 1:
                raise AdbError(
                    "ADB 장치가 여러 대입니다. --serial 또는 ANDROID_SERIAL로 "
                    "대상을 지정하세요."
                )
            selected = usable[0]
        if selected["state"] != "device":
            raise AdbError(
                f"ADB 장치 상태가 device가 아닙니다: {selected['state']}. "
                "헤드유닛에서 디버깅 연결을 승인하세요."
            )
        return selected["serial"]

    def shell(self, arguments: Sequence[str], timeout: float | None = None) -> AdbResult:
        return self._invoke(
            ("shell", *arguments), include_serial=True, timeout=timeout
        )

    def exec_out(
        self, arguments: Sequence[str], timeout: float | None = None
    ) -> AdbResult:
        return self._invoke(
            ("exec-out", *arguments), include_serial=True, timeout=timeout
        )

    def bugreport(self, output: Path, timeout: float = 300.0) -> AdbResult:
        return self._invoke(
            ("bugreport", str(output)), include_serial=True, timeout=timeout
        )


def _utc_timestamp(value: datetime | None = None) -> tuple[datetime, str]:
    timestamp = value or datetime.now(timezone.utc)
    timestamp = timestamp.astimezone(timezone.utc)
    rendered = timestamp.isoformat(timespec="seconds").replace("+00:00", "Z")
    return timestamp, rendered


def _sha256_text(domain: bytes, value: str) -> str:
    digest = hashlib.sha256(domain + b"\0" + value.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _successful_text(client: AdbClient, arguments: Sequence[str]) -> str:
    result = client.shell(arguments)
    if result.returncode != 0:
        return ""
    return result.text.strip()


def _parse_mem_total(value: str) -> int:
    for line in value.splitlines():
        if line.startswith("MemTotal:"):
            fields = line.split()
            try:
                return int(fields[1]) * 1024
            except (IndexError, ValueError):
                return 0
    return 0


def _parse_data_free(value: str) -> int:
    lines = [line.split() for line in value.splitlines() if line.strip()]
    if not lines:
        return 0
    for fields in reversed(lines):
        if len(fields) < 4:
            continue
        try:
            return int(fields[-3]) * 1024
        except ValueError:
            continue
    return 0


def _property(client: AdbClient, name: str) -> str:
    return _successful_text(client, ("getprop", name))


def build_device_report(
    *,
    serial: str,
    properties: dict[str, str],
    meminfo: str,
    data_df: str,
    boot_id: str,
    checked_at: datetime | None = None,
) -> dict[str, Any]:
    """Build the deterministic part of a UIS7862S device report."""
    _, rendered_time = _utc_timestamp(checked_at)
    abi = properties.get("ro.product.cpu.abi", "")
    sdk_text = properties.get("ro.build.version.sdk", "")
    try:
        sdk = int(sdk_text)
    except ValueError:
        sdk = 0
    soc_values = [
        properties.get("ro.soc.model", ""),
        properties.get("ro.board.platform", ""),
        properties.get("ro.hardware", ""),
        properties.get("ro.product.board", ""),
    ]
    soc_detail = " / ".join(value for value in soc_values if value) or "unknown"
    soc_normalized = " ".join(soc_values).lower()
    memory = _parse_mem_total(meminfo)
    data_free = _parse_data_free(data_df)
    boot_hash = _sha256_text(b"kanana-garden-android-boot-v1", boot_id) if boot_id else None
    device_hash = _sha256_text(b"kanana-garden-android-device-v1", serial)
    fingerprint = properties.get("ro.build.fingerprint", "")
    checks = [
        {
            "name": "uis7862s_soc",
            "passed": any(marker in soc_normalized for marker in SOC_MARKERS),
            "required": True,
            "detail": soc_detail,
        },
        {
            "name": "arm64",
            "passed": abi in {"arm64-v8a", "aarch64", "arm64"},
            "required": True,
            "detail": abi or "unknown",
        },
        {
            "name": "android_10_plus",
            "passed": sdk >= 29,
            "required": True,
            "detail": f"SDK {sdk_text or 'unknown'} / Android {properties.get('ro.build.version.release', 'unknown')}",
        },
        {
            "name": "memory_4gb_class",
            "passed": memory >= MIN_MEMORY_BYTES,
            "required": True,
            "detail": f"{memory / GIB:.1f} GiB",
        },
        {
            "name": "data_free",
            "passed": data_free >= MIN_DATA_FREE_BYTES,
            "required": True,
            "detail": f"{data_free / GIB:.1f} GiB free",
        },
        {
            "name": "build_fingerprint",
            "passed": bool(fingerprint),
            "required": True,
            "detail": fingerprint or "unavailable",
        },
        {
            "name": "boot_id",
            "passed": boot_hash is not None,
            "required": True,
            "detail": boot_hash or "unavailable",
        },
        {
            "name": "debuggable_build",
            "passed": properties.get("ro.debuggable") == "1",
            "required": False,
            "detail": properties.get("ro.debuggable", "unknown"),
        },
    ]
    return {
        "schema_version": 1,
        "kind": "kanana-garden-uis7862s-device-check",
        "powered_by": "Kanana",
        "checked_at": rendered_time,
        "profile": PROFILE,
        "device_id_sha256": device_hash,
        "boot_id_sha256": boot_hash,
        "ready": all(check["passed"] for check in checks if check["required"]),
        "checks": checks,
        "device": {
            "manufacturer": properties.get("ro.product.manufacturer", ""),
            "model": properties.get("ro.product.model", ""),
            "soc": soc_detail,
            "hardware": properties.get("ro.hardware", ""),
            "abi": abi,
            "android_release": properties.get("ro.build.version.release", ""),
            "sdk": sdk,
            "build_fingerprint": fingerprint,
            "memory_bytes": memory,
            "data_free_bytes": data_free,
        },
        "recommendations": [
            "실차 주행 전에는 벤치 전원에서 재현 테스트를 먼저 수행하세요.",
            "문제 재현 직후 uis7862s-capture로 로그 링버퍼가 덮이기 전에 증빙을 남기세요.",
            "장시간 부하에서는 Android LMK, 앱별 메모리 한도와 열 스로틀링을 함께 확인하세요.",
            "debuggable=0이어도 기본 캡처는 가능하며 root 권한은 요구하지 않습니다.",
        ],
    }


def device_report(
    *,
    serial: str | None = None,
    adb_path: str | Path | None = None,
    timeout: float = 30.0,
    checked_at: datetime | None = None,
    client: AdbClient | None = None,
) -> dict[str, Any]:
    connected = client or AdbClient(serial=serial, adb_path=adb_path, timeout=timeout)
    names = (
        "ro.product.manufacturer",
        "ro.product.model",
        "ro.product.cpu.abi",
        "ro.build.version.release",
        "ro.build.version.sdk",
        "ro.build.fingerprint",
        "ro.soc.model",
        "ro.board.platform",
        "ro.hardware",
        "ro.product.board",
        "ro.debuggable",
    )
    properties = {name: _property(connected, name) for name in names}
    return build_device_report(
        serial=connected.serial,
        properties=properties,
        meminfo=_successful_text(connected, ("cat", "/proc/meminfo")),
        data_df=_successful_text(connected, ("df", "-k", "/data")),
        boot_id=_successful_text(
            connected, ("cat", "/proc/sys/kernel/random/boot_id")
        ),
        checked_at=checked_at,
    )


def sanitize_getprop(value: str) -> str:
    """Redact common stable identifiers while preserving firmware properties."""
    output: list[str] = []
    for line in value.splitlines():
        match = re.match(r"^\[([^]]+)\]: \[(.*)\]$", line)
        if match and any(
            marker in match.group(1).lower() for marker in SENSITIVE_PROPERTY_MARKERS
        ):
            output.append(f"[{match.group(1)}]: [REDACTED]")
        else:
            output.append(line)
    return "\n".join(output) + ("\n" if value.endswith("\n") else "")


def analyze_logcat(value: str, package: str | None = None) -> dict[str, Any]:
    """Extract bounded triage candidates; this is a lead list, not a diagnosis."""
    severity_counts = {severity: 0 for severity in "VDIWEF"}
    category_counts = {name: 0 for name, _ in TRIAGE_PATTERNS}
    candidates: list[dict[str, Any]] = []
    package_lines = 0
    severity_pattern = re.compile(
        r"^\d\d-\d\d\s+\d\d:\d\d:\d\d\.\d+\s+\d+\s+\d+\s+([VDIWEF])\s"
    )
    lines = value.splitlines()
    for line_number, line in enumerate(lines, start=1):
        severity_match = severity_pattern.match(line)
        if severity_match:
            severity_counts[severity_match.group(1)] += 1
        if package and package in line:
            package_lines += 1
        for category, pattern in TRIAGE_PATTERNS:
            if not pattern.search(line):
                continue
            category_counts[category] += 1
            if len(candidates) < 200:
                candidates.append(
                    {
                        "category": category,
                        "line": line_number,
                        "text": line[:1000],
                    }
                )
    return {
        "logcat_line_count": len(lines),
        "severity_counts": severity_counts,
        "candidate_counts": category_counts,
        "candidate_count": sum(category_counts.values()),
        "candidates_truncated": sum(category_counts.values()) > len(candidates),
        "candidates": candidates,
        "package": package,
        "package_line_count": package_lines,
    }


def _safe_label(value: str | None) -> str | None:
    if value is None:
        return None
    label = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-.")
    if not label:
        raise AdbError("--label에는 파일명으로 사용할 문자가 있어야 합니다.")
    return label[:60]


def _artifact(path: Path, root: Path) -> dict[str, Any]:
    content = path.read_bytes()
    return {
        "path": path.relative_to(root).as_posix(),
        "bytes": len(content),
        "sha256": f"sha256:{hashlib.sha256(content).hexdigest()}",
    }


def _write_result(
    root: Path,
    relative_path: str,
    result: AdbResult,
    *,
    transform: Any = None,
) -> tuple[dict[str, Any], Path]:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = result.stdout
    if transform is not None:
        payload = transform(result.text).encode("utf-8")
    path.write_bytes(payload)
    metadata = {
        "artifact": relative_path,
        "command": list(result.command),
        "returncode": result.returncode,
        "duration_seconds": result.duration_seconds,
        "stderr": result.stderr[:2000],
    }
    return metadata, path


def _filter_logcat_for_package(value: str, package: str, pids: Iterable[str]) -> str:
    pid_patterns = [re.compile(rf"\s{re.escape(pid)}\s") for pid in pids if pid.isdigit()]
    return "\n".join(
        line
        for line in value.splitlines()
        if package in line or any(pattern.search(line) for pattern in pid_patterns)
    ) + "\n"


def capture_diagnostics(
    *,
    output: Path | None = None,
    label: str | None = None,
    package: str | None = None,
    ota_version: str | None = None,
    serial: str | None = None,
    adb_path: str | Path | None = None,
    timeout: float = 30.0,
    include_screenshot: bool = True,
    include_bugreport: bool = False,
    checked_at: datetime | None = None,
    client: AdbClient | None = None,
) -> dict[str, Any]:
    """Capture a local, hash-indexed Android diagnostics bundle."""
    if package and PACKAGE_PATTERN.fullmatch(package) is None:
        raise AdbError(f"유효한 Android package 이름이 아닙니다: {package}")
    if ota_version is not None and not ota_version.strip():
        raise AdbError("--ota-version은 비어 있을 수 없습니다.")
    safe_label = _safe_label(label)
    timestamp, rendered_time = _utc_timestamp(checked_at)
    if output is None:
        directory_name = timestamp.strftime("%Y%m%dT%H%M%SZ")
        if safe_label:
            directory_name += f"-{safe_label}"
        capture_dir = Path("reports") / "uis7862s" / directory_name
    else:
        capture_dir = output
    if capture_dir.exists():
        raise AdbError(f"캡처 디렉터리가 이미 있습니다: {capture_dir}")
    try:
        capture_dir.mkdir(parents=True)
    except OSError as exc:
        raise AdbError(f"캡처 디렉터리를 만들 수 없습니다: {capture_dir}: {exc}") from exc

    connected = client or AdbClient(serial=serial, adb_path=adb_path, timeout=timeout)
    doctor = device_report(client=connected, checked_at=timestamp)
    command_results: list[dict[str, Any]] = []
    artifact_paths: list[Path] = []
    critical_artifacts = {
        "system/getprop.txt",
        "system/proc-meminfo.txt",
        "logs/logcat.txt",
    }
    shell_captures: list[tuple[str, tuple[str, ...], Any]] = [
        ("system/getprop.txt", ("getprop",), sanitize_getprop),
        ("system/uname.txt", ("uname", "-a"), None),
        ("system/uptime.txt", ("uptime",), None),
        ("system/proc-meminfo.txt", ("cat", "/proc/meminfo"), None),
        ("system/proc-cpuinfo.txt", ("cat", "/proc/cpuinfo"), None),
        ("system/df-data.txt", ("df", "-k", "/data"), None),
        ("system/top.txt", ("top", "-b", "-n", "1"), None),
        ("dumpsys/cpuinfo.txt", ("dumpsys", "cpuinfo"), None),
        ("dumpsys/meminfo.txt", ("dumpsys", "meminfo"), None),
        ("dumpsys/thermalservice.txt", ("dumpsys", "thermalservice"), None),
        ("dumpsys/battery.txt", ("dumpsys", "battery"), None),
        (
            "dumpsys/activity-processes.txt",
            ("dumpsys", "activity", "processes"),
            None,
        ),
        ("logs/logcat.txt", ("logcat", "-b", "all", "-d", "-v", "threadtime"), None),
    ]
    if package:
        shell_captures.extend(
            (
                ("app/meminfo.txt", ("dumpsys", "meminfo", package), None),
                ("app/gfxinfo.txt", ("dumpsys", "gfxinfo", package), None),
                ("app/package.txt", ("dumpsys", "package", package), None),
                ("app/pidof.txt", ("pidof", package), None),
            )
        )

    logcat_text = ""
    pid_text = ""
    for relative_path, command, transform in shell_captures:
        result = connected.shell(command, timeout=timeout)
        metadata, path = _write_result(
            capture_dir, relative_path, result, transform=transform
        )
        metadata["stderr"] = metadata["stderr"].replace(
            connected.serial, "[ADB_SERIAL_REDACTED]"
        )
        command_results.append(metadata)
        artifact_paths.append(path)
        if relative_path == "logs/logcat.txt":
            logcat_text = result.text
        elif relative_path == "app/pidof.txt":
            pid_text = result.text

    if package:
        filtered_path = capture_dir / "logs" / "package-logcat.txt"
        filtered_path.write_text(
            _filter_logcat_for_package(logcat_text, package, pid_text.split()),
            encoding="utf-8",
        )
        artifact_paths.append(filtered_path)

    if include_screenshot:
        screenshot = connected.exec_out(("screencap", "-p"), timeout=timeout)
        metadata, path = _write_result(
            capture_dir, "screen/screenshot.png", screenshot
        )
        if screenshot.returncode == 0 and not screenshot.stdout.startswith(b"\x89PNG"):
            metadata["returncode"] = 1
            metadata["stderr"] = (
                metadata["stderr"] + "\nscreencap 결과가 PNG가 아닙니다."
            ).strip()
        command_results.append(metadata)
        artifact_paths.append(path)

    if include_bugreport:
        bugreport_path = capture_dir / "bugreport.zip"
        result = connected.bugreport(bugreport_path)
        command_results.append(
            {
                "artifact": "bugreport.zip",
                "command": list(result.command),
                "returncode": result.returncode,
                "duration_seconds": result.duration_seconds,
                "stderr": result.stderr[:2000],
            }
        )
        command_results[-1]["stderr"] = command_results[-1]["stderr"].replace(
            connected.serial, "[ADB_SERIAL_REDACTED]"
        )
        if bugreport_path.is_file():
            artifact_paths.append(bugreport_path)

    analysis = analyze_logcat(logcat_text, package)
    analysis_path = capture_dir / "analysis.json"
    analysis_path.write_text(
        json.dumps(analysis, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    artifact_paths.append(analysis_path)
    readme_path = capture_dir / "README.txt"
    readme_path.write_text(
        "UIS7862S 진단 캡처\n"
        "\n"
        "1. analysis.json의 crash/anr/memory/watchdog 후보부터 확인합니다.\n"
        "2. 후보 line 번호를 logs/logcat.txt에서 찾아 전후 문맥을 봅니다.\n"
        "3. app/, dumpsys/, system/ 자료로 같은 시각의 상태를 대조합니다.\n"
        "\n"
        "주의: logcat, screenshot, bugreport에는 위치·계정·차량 정보가 포함될 수 "
        "있습니다. 외부 공유 전에 직접 검토하고 필요한 부분을 가리세요.\n",
        encoding="utf-8",
    )
    artifact_paths.append(readme_path)

    critical_failures = [
        result["artifact"]
        for result in command_results
        if result["artifact"] in critical_artifacts and result["returncode"] != 0
    ]
    manifest = {
        "schema_version": 1,
        "kind": "kanana-garden-uis7862s-capture",
        "powered_by": "Kanana",
        "captured_at": rendered_time,
        "profile": PROFILE,
        "label": safe_label,
        "package": package,
        "ota_version": ota_version.strip() if ota_version else None,
        "complete": not critical_failures,
        "critical_failures": critical_failures,
        "device": doctor,
        "analysis": {
            key: value for key, value in analysis.items() if key != "candidates"
        },
        "commands": command_results,
        "artifacts": sorted(
            (_artifact(path, capture_dir) for path in artifact_paths if path.is_file()),
            key=lambda item: item["path"],
        ),
        "privacy": {
            "getprop_identifiers_redacted": True,
            "raw_logcat_requires_review_before_sharing": True,
            "screenshot_requires_review_before_sharing": include_screenshot,
            "bugreport_requires_review_before_sharing": include_bugreport,
        },
        "capture_dir": str(capture_dir),
    }
    manifest_path = capture_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest
