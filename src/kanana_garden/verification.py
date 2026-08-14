"""Machine-readable evidence for model-backed recipe checks."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from .recipe import Recipe


def recipe_digest(recipe: Recipe) -> str:
    canonical = json.dumps(
        recipe.to_mapping(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(canonical).hexdigest()}"


def sanitized_endpoint(base_url: str) -> str:
    """Remove embedded credentials, query strings, and fragments."""
    parts = urlsplit(base_url)
    hostname = parts.hostname
    if hostname is None:
        netloc = ""
    else:
        rendered_host = f"[{hostname}]" if ":" in hostname else hostname
        port = parts.port
        netloc = f"{rendered_host}:{port}" if port is not None else rendered_host
    return urlunsplit((parts.scheme, netloc, parts.path.rstrip("/"), "", ""))


def build_report(
    *,
    recipe: Recipe,
    endpoint: str,
    requested_model: str,
    exposed_models: list[str],
    cases: list[dict[str, Any]],
    checked_at: datetime | None = None,
) -> dict[str, Any]:
    timestamp = checked_at or datetime.now(timezone.utc)
    return {
        "schema_version": 1,
        "kind": "kanana-garden-model-check",
        "powered_by": "Kanana",
        "checked_at": timestamp.astimezone(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        "endpoint": sanitized_endpoint(endpoint),
        "recipe": {
            "slug": recipe.slug,
            "sha256": recipe_digest(recipe),
        },
        "requested_model": requested_model,
        "exposed_models": exposed_models,
        "passed": bool(cases) and all(case.get("passed") is True for case in cases),
        "cases": cases,
    }
