"""Resolve non-secret Coordinator connection settings from machine.local.json."""
from __future__ import annotations

import json
import os
from pathlib import Path


DEFAULT_ENDPOINT = "http://192.0.2.121:18443"
DEFAULT_HOST_ID = "192.0.2.105"


def resolve_coordinator(root: Path) -> tuple[str, str]:
    """Return endpoint and host ID; environment variables are local overrides."""
    endpoint = os.environ.get("BIGQMT_COORDINATOR_ENDPOINT", "").strip()
    host_id = os.environ.get("BIGQMT_HOST_ID", "").strip()
    path = root / "config" / "machine.local.json"
    if path.is_file():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            node = payload.get("coordinator") or {}
            endpoint = endpoint or str(node.get("endpoint") or "").strip()
            host_id = host_id or str(node.get("host_id") or "").strip()
        except (OSError, json.JSONDecodeError):
            pass
    return endpoint or DEFAULT_ENDPOINT, host_id or DEFAULT_HOST_ID
