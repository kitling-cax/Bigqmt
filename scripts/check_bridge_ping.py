"""Run one bounded, read-only Bridge liveness ping for a Tray profile."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kitling_bigqmt.bridge_probe import load_profile_config, probe_bridge_ping  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=("simulation", "production_readonly"), default="simulation")
    parser.add_argument("--timeout", type=float, default=3.0)
    args = parser.parse_args()
    try:
        result = probe_bridge_ping(load_profile_config(ROOT, args.profile), args.timeout)
        result["profile"] = args.profile
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        result = {
            "profile": args.profile,
            "status": "FAIL",
            "detail": "%s: %s" % (type(exc).__name__, exc),
            "broker_call_made": False,
            "order_capability": False,
        }
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
