"""Enable the local, persistent v1.1.15 simulation execution switch.

This command only writes runtime_control.json after verifying the local order
authorization Key.  It does not contact Coordinator, QMT, Redis, or submit an
order.  Use lock_v1_1_15_simulation_execution.py (or the Tray menu) to stop.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kitling_bigqmt.order_authorization_key import status as key_status
from kitling_bigqmt.runtime_control import RuntimeControl


STRATEGY_ID = "S10_D1_U25_NO_ALCOHOL_5D_SIM_MAIN_V1_1_15"
ACCOUNT_ID = "99022040"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--account-id", default=ACCOUNT_ID)
    parser.add_argument("--strategy-id", default=STRATEGY_ID)
    args = parser.parse_args()
    state = key_status("simulation", args.account_id)
    if not state.get("installed") or not state.get("valid"):
        print(json.dumps({"status": "BLOCKED", "reason": "LOCAL_ORDER_KEY_INVALID", "key": state}, ensure_ascii=False, indent=2))
        return 2
    control = RuntimeControl(ROOT / "runtime_data" / "control" / "simulation" / "runtime_control.json")
    value = control.enable_simulation_strategy(
        account_id=args.account_id,
        strategy_id=args.strategy_id,
        approval_scope="operator-approved persistent local simulation execution",
    )
    print(json.dumps({"status": "ENABLED", "coordinator": "MONITOR_ONLY", "runtime_control": value, "key": state}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
