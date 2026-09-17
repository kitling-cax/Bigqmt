"""Capture one read-only tray runtime fact into the local Host Agent Outbox.

This command is deliberately local-only.  It reads the latest native-tray
audit line, normalizes it into a ``STRATEGY_RUNTIME`` fact, and stores it in a
SQLite WAL Outbox.  It does not call QMT, Redis, Coordinator, NAS, or any
order/lease endpoint.  A later uploader may sign and deliver pending rows to
the Shadow Coordinator after an explicit transport gate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from kitling_bigqmt.coordinator_outbox import LocalOutbox  # noqa: E402
from kitling_bigqmt.host_agent_account_policy import resolve_account_policy  # noqa: E402


STRATEGY_BY_PROFILE = {
    "simulation": "S10_D1_U25_NO_ALCOHOL_5D_SIM_MAIN_V1_1_15",
    "production_readonly": "NONE_READONLY",
}


def _latest_audit_line(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"audit file does not exist: {path}")
    latest: dict[str, Any] | None = None
    with path.open("r", encoding="utf-8") as handle:
        for raw in handle:
            raw = raw.strip()
            if not raw:
                continue
            try:
                item = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                latest = item
    if latest is None:
        raise ValueError(f"audit file contains no JSON object: {path}")
    return latest


def build_runtime_fact(*, profile: str, host_id: str, audit_path: Path) -> dict[str, Any]:
    policy = resolve_account_policy(profile)
    audit = _latest_audit_line(audit_path)
    # Hash the normalized latest record, not the whole growing JSONL file.
    # This keeps the event ID stable when the same last observation is
    # collected again after newer unrelated lines were appended elsewhere.
    audit_digest = hashlib.sha256(
        json.dumps(audit, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:24]
    source_key = f"{host_id}|{profile}|{audit.get('event_time', '')}|{audit.get('event', '')}|{audit_digest}"
    event_id = str(uuid.uuid5(uuid.NAMESPACE_URL, "kitling-bigqmt:runtime:" + source_key))
    return {
        "event_id": event_id,
        "account_id": policy.account_id,
        "strategy_id": STRATEGY_BY_PROFILE[profile],
        "state": "RUNNING" if audit.get("event") == "status_refreshed" else "OBSERVED",
        "profile": profile,
        "host_id": host_id,
        "observed_at": audit.get("event_time"),
        "audit_event": audit.get("event"),
        "audit_detail": str(audit.get("detail") or "")[:512],
        "orders_enabled": False,
        "execution_consumer_enabled": False,
        "source": "native_tray_audit_local_only",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, choices=("simulation", "production_readonly"))
    parser.add_argument("--host-id", required=True)
    parser.add_argument("--audit-path", type=Path, required=True)
    parser.add_argument("--outbox-path", type=Path, required=True)
    args = parser.parse_args(argv)
    payload = build_runtime_fact(profile=args.profile, host_id=args.host_id, audit_path=args.audit_path)
    result = LocalOutbox(args.outbox_path).enqueue("STRATEGY_RUNTIME", payload)
    print(json.dumps({"status": result["status"], "event_id": result["event_id"], "profile": args.profile, "account_id": payload["account_id"], "orders_enabled": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
