"""Preflight diagnostics for a Raspberry Pi 5 local model deployment."""

from __future__ import annotations

import hashlib
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


GIB = 1024**3
MIN_MEMORY_BYTES = 7 * GIB
MIN_DISK_BYTES = 8 * GIB


def _mem_total() -> int:
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("MemTotal:"):
                return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        pass
    return 0


def _cpu_features() -> set[str]:
    try:
        for line in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
            key, _, value = line.partition(":")
            if key.strip().lower() in {"features", "flags"}:
                return set(value.split())
    except OSError:
        pass
    return set()


def _temperature_c() -> float | None:
    thermal_path = Path("/sys/class/thermal/thermal_zone0/temp")
    try:
        return int(thermal_path.read_text(encoding="utf-8").strip()) / 1000
    except (OSError, ValueError):
        return None


def _device_model() -> str:
    try:
        return (
            Path("/proc/device-tree/model")
            .read_text(encoding="utf-8")
            .rstrip("\x00")
            .strip()
        )
    except OSError:
        return platform.node()


def _throttled() -> str | None:
    command = shutil.which("vcgencmd")
    if command is None:
        return None
    try:
        result = subprocess.run(
            [command, "get_throttled"],
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    value = result.stdout.strip()
    return value or None


def _boot_id_sha256() -> str | None:
    try:
        boot_id = Path("/proc/sys/kernel/random/boot_id").read_text(
            encoding="utf-8"
        ).strip()
    except OSError:
        return None
    if not boot_id:
        return None
    digest = hashlib.sha256(boot_id.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _device_id_sha256() -> str | None:
    source = os.getenv("KANANA_DEVICE_ID")
    if source is None:
        try:
            source = Path("/etc/machine-id").read_text(encoding="utf-8").strip()
        except OSError:
            return None
    if not source:
        return None
    digest = hashlib.sha256(
        b"kanana-garden-device-v1\0" + source.encode("utf-8")
    ).hexdigest()
    return f"sha256:{digest}"


def runtime_telemetry() -> dict[str, float | str | None]:
    """Return the thermal signals sampled between model generations."""
    return {
        "temperature_c": _temperature_c(),
        "throttled": _throttled(),
    }


def device_report(
    model_dir: str | Path | None = None,
    checked_at: datetime | None = None,
) -> dict[str, Any]:
    target = Path(model_dir or os.getenv("HF_HOME") or Path.home() / ".cache")
    disk_probe = target
    while not disk_probe.exists() and disk_probe != disk_probe.parent:
        disk_probe = disk_probe.parent
    disk = shutil.disk_usage(disk_probe)
    architecture = platform.machine().lower()
    memory = _mem_total()
    python_ok = sys.version_info >= (3, 10)
    hardware = _device_model()
    temperature = _temperature_c()
    throttled = _throttled()
    boot_id_sha256 = _boot_id_sha256()
    device_id_sha256 = _device_id_sha256()
    cpu_features = _cpu_features()

    checks = [
        {
            "name": "raspberry_pi_5",
            "passed": "raspberry pi 5" in hardware.lower(),
            "required": True,
            "detail": hardware or "unknown",
        },
        {
            "name": "arm64",
            "passed": architecture in {"aarch64", "arm64"},
            "required": True,
            "detail": architecture,
        },
        {
            "name": "memory_8gb_profile",
            "passed": memory >= MIN_MEMORY_BYTES,
            "required": True,
            "detail": f"{memory / GIB:.1f} GiB",
        },
        {
            "name": "free_disk",
            "passed": disk.free >= MIN_DISK_BYTES,
            "required": True,
            "detail": f"{disk.free / GIB:.1f} GiB free at {disk_probe}",
        },
        {
            "name": "python",
            "passed": python_ok,
            "required": True,
            "detail": platform.python_version(),
        },
        {
            "name": "boot_id",
            "passed": boot_id_sha256 is not None,
            "required": True,
            "detail": boot_id_sha256 or "unavailable",
        },
        {
            "name": "device_id",
            "passed": device_id_sha256 is not None,
            "required": True,
            "detail": device_id_sha256 or "unavailable",
        },
        {
            "name": "native_bf16",
            "passed": "bf16" in cpu_features,
            "required": False,
            "detail": "available" if "bf16" in cpu_features else "not advertised by CPU",
        },
    ]
    if temperature is not None:
        checks.append(
            {
                "name": "temperature",
                "passed": temperature < 80,
                "required": True,
                "detail": f"{temperature:.1f} °C",
            }
        )
    if throttled is not None:
        checks.append(
            {
                "name": "throttling",
                "passed": throttled == "throttled=0x0",
                "required": True,
                "detail": throttled,
            }
        )
    timestamp = checked_at or datetime.now(timezone.utc)
    return {
        "schema_version": 1,
        "kind": "kanana-garden-device-check",
        "powered_by": "Kanana",
        "checked_at": timestamp.astimezone(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        "profile": "raspberry-pi-5-8gb",
        "boot_id_sha256": boot_id_sha256,
        "device_id_sha256": device_id_sha256,
        "ready": all(check["passed"] for check in checks if check["required"]),
        "checks": checks,
        "temperature_c": temperature,
        "throttled": throttled,
        "recommendations": [
            "64-bit Raspberry Pi OS를 사용하세요.",
            "장시간 추론에는 Active Cooler 또는 팬 케이스를 사용하세요.",
            "모델 캐시는 여유 공간 8 GiB 이상의 SSD에 두는 것을 권장합니다.",
            "27 W USB-C 전원 공급 장치를 권장합니다.",
            "Cortex-A76에는 네이티브 BF16이 없어 첫 실측 전 성능을 가정하지 마세요.",
        ],
    }
