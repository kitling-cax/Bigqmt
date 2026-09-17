"""Local operator commands used by the portable BigQMT Tray candidate.

No command in this script starts QMT or touches QMT/Redis.  First release is
read-only and only exposes status plus a persistent fail-closed order lock.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from kitling_bigqmt.runtime_control import RuntimeControl  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("status", "lock-orders"))
    parser.add_argument("--reason", default="operator lock")
    parser.add_argument("--profile", choices=("simulation", "production_readonly"), default="simulation")
    parser.add_argument("--control-path", type=Path, default=None)
    args = parser.parse_args()
    environment = "simulation" if args.profile == "simulation" else "production"
    control_path = args.control_path or (
        ROOT / "runtime_data" / "control" / args.profile / "runtime_control.json"
    )
    control = RuntimeControl(control_path, environment=environment)
    result = control.status() if args.command == "status" else control.lock_orders(args.reason)
    result["broker_call_made"] = False
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
