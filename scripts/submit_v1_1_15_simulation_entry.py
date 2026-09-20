"""Submit exactly one preflighted v1.1.15 simulation entry.

This is a migration/activation tool, not the long-running strategy executor.
It accepts no account, code, quantity, or price arguments.  The only possible
broker action is the latest eligible v1.1.15 close signal for account 90000001.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kitling_bigqmt.redis_resp import RedisRespClient  # noqa: E402
from kitling_bigqmt.readonly_rpc import ReadOnlyBigQmtClient, encode_rpc_request_payload  # noqa: E402
from kitling_bigqmt.runtime_control import RuntimeControl  # noqa: E402
from kitling_bigqmt.execution_admission import require_admission_for_root  # noqa: E402
from kitling_bigqmt.machine_config import load_gateway  # noqa: E402
from kitling_bigqmt.simulation_execution import ACCOUNT_ID, STRATEGY_ID, build_order_plan  # noqa: E402
from kitling_bigqmt.simulation_cycle import live_broker_orders  # noqa: E402
from kitling_bigqmt.sleeve_accounting import SleeveAccounting  # noqa: E402
from kitling_bigqmt.state_store import RuntimeStateStore  # noqa: E402


def rpc_submit(redis: RedisRespClient, params: dict, timeout: float = 12.0) -> dict:
    request_id = uuid.uuid4().hex
    response_key = "bigqmt:rpc:resp:%s:%s" % (ACCOUNT_ID, request_id)
    request = {
        "schema_version": 1, "request_id": request_id, "account_id": ACCOUNT_ID,
        "method": "submit_order", "params": params, "reply_channel": response_key,
        "reply_list": "bigqmt:rpc:respq:%s:%s" % (ACCOUNT_ID, request_id),
        "reply_key": response_key, "ttl_seconds": 60,
    }
    redis.command("RPUSH", "bigqmt:rpc:queue:%s" % ACCOUNT_ID,
                  encode_rpc_request_payload(request))
    redis.command("EXPIRE", "bigqmt:rpc:queue:%s" % ACCOUNT_ID, 60)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        raw = redis.command("GET", response_key)
        if raw:
            return json.loads(raw)
        time.sleep(0.2)
    return {"ok": False, "request_id": request_id, "error": "TIMEOUT_STATE_UNKNOWN_NO_RETRY"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true", help="submit the one preflighted simulation order")
    args = parser.parse_args()
    config = load_gateway(ROOT, "simulation")
    if config.get("environment") != "simulation" or str(config.get("account_id")) != ACCOUNT_ID:
        raise SystemExit("blocked: simulation account binding mismatch")
    redis = RedisRespClient(**dict(config["redis"]))
    client = ReadOnlyBigQmtClient(redis, ACCOUNT_ID, float(config.get("rpc_timeout_seconds", 12)))
    store = RuntimeStateStore(Path(config["state_db"]), Path(config["audit_dir"]))
    SleeveAccounting(store).register_sleeve(STRATEGY_ID, 100000)
    event = next(item for item in store.latest_strategy_shadow_events(20)
                 if item.get("strategy_id") == STRATEGY_ID)
    target = str((event.get("signal") or {}).get("desired_qmt") or "")
    if not target:
        raise SystemExit("blocked: latest signal has no target")
    ping = client.ping()
    if not bool((ping.get("data") or {}).get("allow_order_methods")):
        raise SystemExit("blocked: QMT Bridge has not loaded the simulation execution route")
    positions = client.positions()
    orders = client.orders()
    asset = client.account_asset()
    tick = client.full_tick([target])
    if not asset.get("ok"):
        raise SystemExit("blocked: account preflight failed")
    if live_broker_orders(list(orders.get("data") or [])):
        raise SystemExit("blocked: account has open orders")
    if (positions.get("data") or {}).get(target):
        raise SystemExit("blocked: target already exists in broker account and cannot be claimed as a new sleeve")
    sleeve = SleeveAccounting(store).summary(STRATEGY_ID, {})
    plan = build_order_plan(
        signal_event=event, activation_signal_not_before="20260910",
        trade_day=datetime.now().strftime("%Y%m%d"), sleeve_summary=sleeve,
        ticks=tick.get("data") or {},
    )
    if not plan or plan.get("side") != "BUY":
        raise SystemExit("blocked: no new v1.1.15 entry is required")
    evidence = {
        "kind": "v1_1_15_simulation_entry_activation", "created_at": datetime.now().astimezone().isoformat(),
        "account_id": ACCOUNT_ID, "strategy_id": STRATEGY_ID, "signal_day": event.get("signal_day"),
        "plan": plan, "ping": ping.get("data"),
        "order_count": len(orders.get("data") or []),
        "open_order_count": len(live_broker_orders(list(orders.get("data") or []))),
        "target_preexisting_position": False, "execution_requested": bool(args.execute),
    }
    if not args.execute:
        print(json.dumps(evidence, ensure_ascii=False, indent=2))
        return 0
    control = RuntimeControl(ROOT / "runtime_data" / "control" / "simulation" / "runtime_control.json")
    response = None
    control.enable_simulation_strategy(
        account_id=ACCOUNT_ID, strategy_id=STRATEGY_ID,
        approval_scope="2026-09-11 explicit user-authorized v1.1.15 simulation entry activation",
    )
    evidence["execution_admission"] = require_admission_for_root(
        ROOT, "simulation", strategy_id=STRATEGY_ID, authorization=control.status(),
    )
    signal_id = "v1_1_15-entry-%s-%s" % (event["signal_day"], uuid.uuid4().hex[:10])
    response = rpc_submit(redis, {
        "account_id": ACCOUNT_ID, "action": "BUY", "stock_code": plan["stock_code"],
        "volume": int(plan["quantity"]), "price": float(plan["limit_price"]), "price_type": "LIMIT",
        "strategy_name": STRATEGY_ID, "signal_id": signal_id, "remark": signal_id,
    })
    evidence["response"] = response
    evidence["no_retry_on_timeout"] = True
    directory = ROOT / "runtime_data" / "evidence" / "simulation" / "strategy_execution"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / ("v1_1_15_entry_%s.json" % datetime.now().strftime("%Y%m%d_%H%M%S"))
    path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"evidence": str(path), **evidence}, ensure_ascii=False, indent=2))
    return 0 if response and response.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
