"""Build a sanitized read-only Host Agent heartbeat snapshot.

The builder accepts already-collected facts and never imports QMT/Redis.  It
is the boundary used by the future HTTPS client; order or credential fields
are intentionally not accepted.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def build_heartbeat(host_id: str, state: str, services: dict[str, str], *,
                    account_ids: list[str] | None = None, version: str = "") -> dict[str, Any]:
    if not host_id.strip():
        raise ValueError("host_id is required")
    if state not in {"HEALTHY_READONLY", "ACTIVE_EXECUTOR", "DEGRADED", "OFFLINE"}:
        raise ValueError("invalid host state")
    return {
        "schema_version": 1,
        "host_id": host_id,
        "sent_at": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "state": state,
        "services": dict(services),
        "accounts": list(account_ids or []),
        "agent_version": version,
    }
