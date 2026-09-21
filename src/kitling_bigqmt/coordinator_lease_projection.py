"""Parse the read-only Coordinator executor preview for one local profile."""
from __future__ import annotations

from typing import Any


ACCOUNT_BY_PROFILE = {
    "simulation": "90000001",
    "production_readonly": "90000002",
}


def _deployment_account(profile: str) -> str:
    """Real per-host account from gitignored machine.local.json (never committed)."""
    try:
        from . import machine_config

        machine = machine_config.load_machine_local(machine_config.project_root())
        return str(machine_config.machine_environment(machine, profile).get("account_id") or "").strip()
    except Exception:
        return ""


def project_local_lease(preview: dict[str, Any], profile: str, host_id: str) -> dict[str, Any]:
    if profile not in ACCOUNT_BY_PROFILE:
        raise ValueError("unknown profile")
    if preview.get("mode") != "readonly-preview":
        raise ValueError("unexpected coordinator preview mode")
    candidates = (ACCOUNT_BY_PROFILE[profile], _deployment_account(profile))
    entry = next((item for item in preview.get("accounts", []) if item.get("account_id") in candidates), None)
    if not isinstance(entry, dict):
        raise ValueError("account is absent from preview")
    account_id = str(entry.get("account_id"))
    candidate = next((item for item in entry.get("candidates", []) if item.get("host_id") == host_id), {})
    return {
        "profile": profile,
        "account_id": account_id,
        "lease_state": str(entry.get("lease_state", "UNKNOWN")),
        "current_executor": entry.get("current_executor"),
        "fencing_token": entry.get("fencing_token"),
        "coordinator_epoch": entry.get("coordinator_epoch"),
        "candidate_eligible": bool(candidate.get("eligible", False)),
        "candidate_reason": str(candidate.get("health_reason", "NOT_REPORTED")),
        "orders_enabled": False,
    }
