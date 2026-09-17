"""Fail-closed gate for creating a unified Silver/PIT v2 release."""
from __future__ import annotations
from typing import Any


REQUIRED = ("raw_canonical", "corporate_actions_numeric", "available_at", "universe_pit", "source_freshness", "manifest_hash")


def evaluate_pit_inputs(raw_manifest: dict[str, Any], action_manifest: dict[str, Any], universe_status: str = "NOT_STARTED", source_freshness: str = "NOT_STARTED") -> dict[str, Any]:
    gates = {
        "raw_canonical": "PASSED" if raw_manifest.get("status") == "PUBLISHED_ISOLATED_SILVER_RAW_CANDIDATE" and raw_manifest.get("global_publishable") else "BLOCKED_PROVISIONAL_OR_CONFLICT",
        "corporate_actions_numeric": "PASSED" if action_manifest.get("numeric_factor_gate") == "PASSED" else "BLOCKED_UNVERIFIED",
        "available_at": "PASSED" if action_manifest.get("available_at_gate") == "PASSED" else "BLOCKED_DATE_ONLY",
        "universe_pit": universe_status,
        "source_freshness": source_freshness,
        "manifest_hash": "PASSED" if raw_manifest.get("release_id") and action_manifest.get("release_id") else "BLOCKED_MISSING_MANIFEST",
    }
    failed = {key: value for key, value in gates.items() if value != "PASSED"}
    return {"required_gates": list(REQUIRED), "gates": gates, "failed_gates": failed,
            "publishable": not failed, "decision": "READY_FOR_EXPLICIT_PIT_PUBLISH" if not failed else "BLOCKED_PIT_V2"}
