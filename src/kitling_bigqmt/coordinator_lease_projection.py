"""Parse the read-only Coordinator executor preview for one local profile."""
from __future__ import annotations

from typing import Any


ACCOUNT_BY_PROFILE = {
    "simulation": "90000001",
    "production_readonly": "90000002",
}


def project_local_lease(preview: dict[str, Any], profile: str, host_id: str) -> dict[str, Any]:
    if profile not in ACCOUNT_BY_PROFILE:
        raise ValueError("unknown profile")
    if preview.get("mode") != "readonly-preview":
        raise ValueError("unexpected coordinator preview mode")
    account_id = ACCOUNT_BY_PROFILE[profile]
    entry = next((item for item in preview.get("accounts", []) if item.get("account_id") == account_id), None)
    if not isinstance(entry, dict):
        raise ValueError("account is absent from preview")
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
