"""Probe only the empty read-only Host Agent intent-preview endpoint.

The probe issues a single authenticated GET.  It cannot submit, acknowledge,
lease, confirm, execute or cancel an intent, and it always exits 0: an
unreachable Coordinator is reported as a degraded read-only envelope so an
account tray can display it without inventing any execution authority.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from kitling_bigqmt.coordinator_endpoint import resolve_coordinator  # noqa: E402
from kitling_bigqmt.host_agent_client import HostAgentClient  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only Host Agent intent-preview probe")
    parser.add_argument("--endpoint", default="", help="optional; defaults to machine.local.json")
    parser.add_argument("--host-id", default="", help="optional; defaults to machine.local.json")
    parser.add_argument("--account-id", default="90000001")
    parser.add_argument("--timeout", type=float, default=3.0)
    args = parser.parse_args()

    endpoint, host_id = resolve_coordinator(ROOT)
    endpoint = args.endpoint.strip() or endpoint
    host_id = args.host_id.strip() or host_id
    try:
        client = HostAgentClient(endpoint, host_id, timeout_seconds=max(0.1, args.timeout))
        result = client.readonly_intent_preview(args.account_id)
    except Exception as exc:  # a control-plane outage must stay read-only
        print(json.dumps({
            "status": "DEGRADED", "endpoint": endpoint, "host_id": host_id,
            "account_id": args.account_id, "intent_count": 0, "reason": type(exc).__name__,
            "readonly": True, "orders_enabled": False,
        }, ensure_ascii=False))
        return 0
    print(json.dumps({
        "status": "passed", "endpoint": endpoint, "host_id": result.host_id,
        "account_id": result.account_id, "intent_count": len(result.intents),
        "readonly": True, "orders_enabled": result.orders_enabled,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
