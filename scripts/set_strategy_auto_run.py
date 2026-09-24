"""Set one local simulation strategy's tray auto-run switch.

This changes only the local policy file.  It never enables broker orders and
cannot modify the production policy.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "config" / "strategy_runtime_policy.json"
V1115 = "S10_D1_U25_NO_ALCOHOL_5D_SIM_MAIN_V1_1_15"


def main() -> int:
    parser = argparse.ArgumentParser(description="Set a local simulation strategy auto-run flag")
    parser.add_argument("--strategy-id", required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--enabled", choices=("true", "false"))
    group.add_argument("--clear", action="store_true")
    args = parser.parse_args()

    if args.strategy_id == "" or any(x in args.strategy_id for x in ("/", "\\")):
        print(json.dumps({"status": "REJECTED", "reason": "invalid strategy id", "orders_enabled": False}))
        return 2
    try:
        document = json.loads(POLICY.read_text(encoding="utf-8"))
        simulation = document.setdefault("simulation", {})
        strategies = simulation.setdefault("strategies", {})
        if args.clear:
            strategies.pop(args.strategy_id, None)
            if args.strategy_id == V1115:
                simulation["v1_1_15_auto_run_enabled"] = False
            action = "cleared"
            enabled = False
        else:
            enabled = args.enabled == "true"
            strategies[args.strategy_id] = {"auto_run_enabled": enabled}
            if args.strategy_id == V1115:
                simulation["v1_1_15_auto_run_enabled"] = enabled
            action = "enabled" if enabled else "disabled"
        POLICY.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "REJECTED", "reason": str(exc), "orders_enabled": False}, ensure_ascii=False))
        return 2
    print(json.dumps({"status": "UPDATED", "strategy_id": args.strategy_id,
                      "auto_run_enabled": enabled, "action": action,
                      "orders_enabled": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
