"""One-time, fail-closed bridge test for simulation account 90000001.

This script intentionally supports only 510300.SH, exactly 100 shares, and a
single side per run.  A response timeout is terminal: it never retries an
order.  It is not a strategy runner and cannot address the formal account.
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

from kitling_bigqmt.redis_resp import RedisRespClient
from kitling_bigqmt.readonly_rpc import ReadOnlyBigQmtClient, encode_rpc_request_payload
from kitling_bigqmt.execution_admission import require_admission_for_root  # noqa: E402

ACCOUNT_ID = "90000001"
STOCK_CODE = "510300.SH"
QUANTITY = 100
STRATEGY_NAME = "SIMULATION_510300_BRIDGE_TEST_20260909"


def _rpc_write(redis: RedisRespClient, method: str, params: dict, timeout: float = 12.0) -> dict:
    request_id = uuid.uuid4().hex
    response_key = "bigqmt:rpc:resp:%s:%s" % (ACCOUNT_ID, request_id)
    request = {
        "schema_version": 1,
        "request_id": request_id,
        "account_id": ACCOUNT_ID,
        "method": method,
        "params": params,
        "reply_channel": response_key,
        "reply_list": "bigqmt:rpc:respq:%s:%s" % (ACCOUNT_ID, request_id),
        "reply_key": response_key,
        "ttl_seconds": 60,
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
    parser.add_argument("side", choices=("BUY", "SELL"))
    args = parser.parse_args()
    control = json.loads((ROOT / "runtime_data" / "control" / "simulation" / "runtime_control.json").read_text(encoding="utf-8"))
    if str(control.get("environment", "")).upper() != "SIMULATION" or str(control.get("account_id")) != ACCOUNT_ID:
        raise SystemExit("blocked: wrong runtime-control environment or account")
    if not control.get("orders_enabled") or not control.get("execution_consumer_enabled"):
        raise SystemExit("blocked: runtime order controls are locked")
    if float(control.get("valid_until_epoch", 0)) <= time.time():
        raise SystemExit("blocked: one-time runtime permission has expired")
    # Single fail-closed order gate, identical to the tray-owned cycle path.
    admission = require_admission_for_root(ROOT, "simulation", authorization=control)
    redis = RedisRespClient(host="127.0.0.1", port=6379, db=5, password="")
    readonly = ReadOnlyBigQmtClient(redis, ACCOUNT_ID, 12.0)
    quote = (readonly.full_tick([STOCK_CODE]).get("data") or {}).get(STOCK_CODE) or {}
    price_list = quote.get("askPrice") if args.side == "BUY" else quote.get("bidPrice")
    price = float((price_list or [0])[0] or 0)
    if price <= 0:
        price = float(quote.get("lastPrice") or 0)
    if price <= 0:
        raise SystemExit("blocked: no positive live limit price")
    signal_id = "sim-510300-%s-%s" % (args.side.lower(), datetime.now().strftime("%Y%m%d%H%M%S"))
    params = {
        "account_id": ACCOUNT_ID,
        "action": args.side,
        "stock_code": STOCK_CODE,
        "volume": QUANTITY,
        "price": price,
        "price_type": "LIMIT",
        "strategy_name": STRATEGY_NAME,
        "signal_id": signal_id,
        "remark": signal_id,
    }
    response = _rpc_write(redis, "submit_order", params)
    result = {
        "kind": "one_time_simulation_510300_bridge_test",
        "created_at": datetime.now().astimezone().isoformat(),
        "account_id": ACCOUNT_ID,
        "stock_code": STOCK_CODE,
        "side": args.side,
        "quantity": QUANTITY,
        "limit_price": price,
        "quote_time": quote.get("timetag"),
        "response": response,
        "no_retry_on_timeout": True,
        "execution_admission": admission,
    }
    evidence = ROOT / "runtime_data" / "evidence" / "simulation" / ("one_time_510300_%s_%s.json" % (args.side.lower(), datetime.now().strftime("%Y%m%d_%H%M%S")))
    evidence.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"evidence": str(evidence), **result}, ensure_ascii=False, indent=2))
    return 0 if response.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
