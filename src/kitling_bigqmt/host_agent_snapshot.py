"""Build a sanitized read-only Host Agent heartbeat snapshot.

The builder accepts already-collected facts and never imports QMT/Redis.  It
is the boundary used by the future HTTPS client; order or credential fields
are intentionally not accepted.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def build_heartbeat(host_id: str, state: str, services: dict[str, str], *,
                    account_ids: list[str] | None = None, version: str = "",
                    strategy_instances: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    if not host_id.strip():
        raise ValueError("host_id is required")
    if state not in {"HEALTHY_READONLY", "ACTIVE_EXECUTOR", "DEGRADED", "OFFLINE"}:
        raise ValueError("invalid host state")
    clean_instances: list[dict[str, Any]] = []
    for item in strategy_instances or []:
        if not isinstance(item, dict):
            raise ValueError("strategy instance must be an object")
        allowed = {"strategy_id", "version", "state", "policy_enabled", "authorization_key_state", "bridge_version"}
        if set(item) - allowed or not str(item.get("strategy_id") or "").strip():
            raise ValueError("invalid strategy instance")
        state_value = str(item.get("state") or "UNKNOWN").upper()
        if state_value not in {"RUNNING", "STOPPED", "DEGRADED", "UNKNOWN"}:
            raise ValueError("invalid strategy state")
        clean_instances.append({
            "strategy_id": str(item["strategy_id"]).strip(),
            "version": str(item.get("version") or "").strip(),
            "state": state_value,
            "policy_enabled": bool(item.get("policy_enabled", False)),
            "authorization_key_state": str(item.get("authorization_key_state") or "UNKNOWN").upper(),
            "bridge_version": str(item.get("bridge_version") or "").strip(),
        })
    return {
        "schema_version": 1,
        "host_id": host_id,
        "sent_at": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "state": state,
        "services": dict(services),
        "accounts": list(account_ids or []),
        "agent_version": version,
        "strategy_instances": clean_instances,
    }
