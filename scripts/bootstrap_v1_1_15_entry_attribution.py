"""Register the 2026-09-11 authorized simulation entry's durable QMT identity.

This one-time recovery tool reads the immutable submission evidence and the
existing local sleeve fill ledger.  It never connects to Redis or QMT and it
cannot submit, cancel, or amend a broker order.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kitling_bigqmt.simulation_cycle import ACCOUNT_ID, STRATEGY_ID  # noqa: E402
from kitling_bigqmt.machine_config import load_gateway  # noqa: E402
from kitling_bigqmt.sleeve_accounting import SleeveAccounting  # noqa: E402
from kitling_bigqmt.state_store import RuntimeStateStore  # noqa: E402


EVIDENCE_RELATIVE = Path("runtime_data/evidence/simulation/strategy_execution/v1_1_15_entry_20260911_102034.json")


def main() -> int:
    config = load_gateway(ROOT, "simulation")
    if config.get("environment") != "simulation" or str(config.get("account_id")) != ACCOUNT_ID:
        raise SystemExit("blocked: recovery tool is bound to simulation account 90000001")
    evidence = json.loads((ROOT / EVIDENCE_RELATIVE).read_text(encoding="utf-8"))
    plan = dict(evidence.get("plan") or {})
    reply = dict((evidence.get("response") or {}).get("data") or {})
    if str(evidence.get("strategy_id")) != STRATEGY_ID or str(evidence.get("account_id")) != ACCOUNT_ID:
        raise SystemExit("blocked: evidence strategy/account binding mismatch")
    store = RuntimeStateStore(Path(config["state_db"]), Path(config["audit_dir"]))
    accounting = SleeveAccounting(store)
    fills = accounting.fill_records(STRATEGY_ID)
    matching = [row for row in fills if row["stock_code"] == str(plan.get("stock_code")) and row["side"] == str(plan.get("side"))]
    filled_quantity = sum(int(row["quantity"]) for row in matching)
    planned_quantity = int(plan.get("quantity") or 0)
    if planned_quantity <= 0 or filled_quantity <= 0 or filled_quantity > planned_quantity:
        raise SystemExit("blocked: local sleeve fills do not reconcile to the immutable submitted plan")
    result = store.register_strategy_order_attribution({
        "strategy_id": STRATEGY_ID, "account_id": ACCOUNT_ID,
        "user_order_id": reply.get("user_order_id"), "order_sys_id": reply.get("order_sys_id"),
        "stock_code": plan.get("stock_code"), "side": plan.get("side"), "quantity": planned_quantity,
        "source_evidence": EVIDENCE_RELATIVE.as_posix(),
    })
    print(json.dumps({"status": "PASSED", "attribution": result, "filled_quantity": filled_quantity,
                      "planned_quantity": planned_quantity, "broker_call_made": False, "orders_enabled": False},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
