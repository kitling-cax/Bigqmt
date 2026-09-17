"""Send a sanitized, read-only tray heartbeat to the BigQMT Coordinator.

This command deliberately accepts only service state labels.  It neither reads
credentials nor connects to QMT/Redis, and it cannot convey an order intent.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kitling_bigqmt.coordinator_endpoint import resolve_coordinator  # noqa: E402
from kitling_bigqmt.host_agent_client import HostAgentClient  # noqa: E402


PROFILE_ACCOUNT = {
    "simulation": "90000001",
    "production_readonly": "90000002",
}
ALLOWED = {"UP", "DOWN", "UNKNOWN"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=tuple(PROFILE_ACCOUNT), required=True)
    parser.add_argument("--qmt", choices=tuple(ALLOWED), required=True)
    parser.add_argument("--miniqmt", choices=tuple(ALLOWED), required=True)
    parser.add_argument("--redis", choices=tuple(ALLOWED), required=True)
    parser.add_argument("--bridge", choices=tuple(ALLOWED), required=True)
    parser.add_argument("--dashboard", choices=tuple(ALLOWED), required=True)
    parser.add_argument("--tray", choices=("UP",), default="UP")
    args = parser.parse_args()

    endpoint, host_id = resolve_coordinator(ROOT)
    services = {
        "qmt": args.qmt,
        "miniqmt": args.miniqmt,
        "redis": args.redis,
        "bridge": args.bridge,
        "dashboard": args.dashboard,
        "tray": args.tray,
    }
    result = HostAgentClient(endpoint, host_id).heartbeat(
        services, account_ids=[PROFILE_ACCOUNT[args.profile]], version="native-tray-v1"
    )
    print(json.dumps({"profile": args.profile, "services": services, "result": result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
