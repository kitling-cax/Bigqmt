"""Run one Tray-owned v1.1.15 simulation execution cycle.

Default mode is preflight-only.  ``--execute`` is deliberately explicit and
can submit no more than one deterministically identified order after all
checks pass.  Every execution path locks the runtime control in ``finally``;
an unknown response is journaled and must be reconciled, never retried.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kitling_bigqmt.daily_operations import reconcile_daily_positions  # noqa: E402
from kitling_bigqmt.execution_admission import require_admission_for_root  # noqa: E402
from kitling_bigqmt.fill_reconciliation import reconcile_attributable_trades  # noqa: E402
from kitling_bigqmt.redis_resp import RedisRespClient  # noqa: E402
from kitling_bigqmt.readonly_rpc import ReadOnlyBigQmtClient, encode_rpc_request_payload  # noqa: E402
from kitling_bigqmt.runtime_control import RuntimeControl  # noqa: E402
from kitling_bigqmt.machine_config import load_gateway  # noqa: E402
from kitling_bigqmt.simulation_cycle import (  # noqa: E402
    STRATEGY_ID, SimulationExecutionBlocked, build_cycle_plan, live_broker_orders,
)
from kitling_bigqmt.sleeve_accounting import SleeveAccounting  # noqa: E402
from kitling_bigqmt.state_store import RuntimeStateStore  # noqa: E402


SHANGHAI = ZoneInfo("Asia/Shanghai")


def _rpc_submit(redis: RedisRespClient, params: dict[str, Any], timeout: float, account_id: str) -> dict[str, Any]:
    request_id = uuid.uuid4().hex
    response_key = "bigqmt:rpc:resp:%s:%s" % (account_id, request_id)
    request = {
        "schema_version": 1, "request_id": request_id, "account_id": account_id,
        "method": "submit_order", "params": params, "reply_channel": response_key,
        "reply_list": "bigqmt:rpc:respq:%s:%s" % (account_id, request_id),
        "reply_key": response_key, "ttl_seconds": 60,
    }
    redis.command("RPUSH", "bigqmt:rpc:queue:%s" % account_id,
                  encode_rpc_request_payload(request))
    redis.command("EXPIRE", "bigqmt:rpc:queue:%s" % account_id, 60)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        raw = redis.command("GET", response_key)
        if raw:
            return json.loads(raw)
        time.sleep(0.2)
    return {"ok": False, "request_id": request_id, "error": "TIMEOUT_STATE_UNKNOWN_NO_RETRY"}


def _write_evidence(value: dict[str, Any]) -> Path:
    directory = ROOT / "runtime_data" / "evidence" / "simulation" / "strategy_execution_cycles"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / ("v1_1_15_cycle_%s.json" % datetime.now(SHANGHAI).strftime("%Y%m%d_%H%M%S"))
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _preflight_only_dates(root: Path) -> set[str]:
    """Date-scoped preflight-only gate from the simulation runtime policy.

    When a local date is listed, the cycle degrades to read-only preflight
    even if --execute is passed: it performs the full account/quote/
    reconciliation/plan check chain but never submits an order.  Intended for
    a controlled, one-session preflight before a separately authorized
    execution; it does not widen any order capability.
    """
    try:
        policy = json.loads((root / "config" / "strategy_runtime_policy.json").read_text(encoding="utf-8"))
        dates = policy.get("simulation", {}).get("v1_1_15_preflight_only_dates") or []
        return {str(item) for item in dates} if isinstance(dates, list) else set()
    except (OSError, json.JSONDecodeError):
        return set()


def main() -> int:
    parser = argparse.ArgumentParser(description="One idempotent v1.1.15 simulation cycle.")
    parser.add_argument("--execute", action="store_true", help="submit the single preflighted simulation order")
    args = parser.parse_args()
    now = datetime.now(SHANGHAI)
    execute = bool(args.execute)
    preflight_only_gate = now.strftime("%Y-%m-%d") in _preflight_only_dates(ROOT)
    if preflight_only_gate:
        execute = False
    config = load_gateway(ROOT, "simulation")
    account_id = str(config.get("account_id") or "").strip()
    if config.get("environment") != "simulation" or not account_id:
        raise SystemExit("blocked: simulation account is not configured")
    registry = json.loads((ROOT / "config" / "strategy_registry.json").read_text(encoding="utf-8"))
    registered = next((item for item in registry.get("strategies", []) if item.get("strategy_id") == STRATEGY_ID), None)
    if not registered or registered.get("execution_enabled") is not True:
        raise SystemExit("blocked: v1.1.15 simulation execution is not enabled in the registry")

    redis = RedisRespClient(**dict(config["redis"]))
    client = ReadOnlyBigQmtClient(redis, account_id, float(config.get("rpc_timeout_seconds", 12)))
    store = RuntimeStateStore(Path(config["state_db"]), Path(config["audit_dir"]))
    accounting = SleeveAccounting(store)
    attributable_trades_reply = client.trades()
    fill_reconciliation = reconcile_attributable_trades(
        accounting, STRATEGY_ID, list(attributable_trades_reply.get("data") or []),
    )
    event = next((item for item in store.latest_strategy_shadow_events(50)
                  if item.get("strategy_id") == STRATEGY_ID), None)
    report: dict[str, Any] = {
        "schema_version": 1, "kind": "v1_1_15_tray_simulation_cycle", "created_at": now.isoformat(),
        "account_id": account_id, "strategy_id": STRATEGY_ID,
        "execute_requested": bool(args.execute), "execute_effective": bool(execute),
        "preflight_only_date_gate": bool(preflight_only_gate),
        "broker_call_made": False, "orders_enabled_after": False,
    }
    try:
        if event is None:
            raise SimulationExecutionBlocked("no persisted v1.1.15 completed-close signal")
        signal = dict(event.get("signal") or {})
        desired = str(signal.get("desired_qmt") or "")
        owned = accounting.position_quantities(STRATEGY_ID)
        price_codes = sorted(set(owned) | ({desired} if desired else set()))
        ping = client.ping()
        asset = client.account_asset()
        positions_reply = client.positions()
        orders_reply = client.orders()
        ticks_reply = client.full_tick(price_codes) if price_codes else {"data": {}}
        prices = {code: float(((ticks_reply.get("data") or {}).get(code) or {}).get("lastPrice") or 0)
                  for code in owned}
        sleeve = accounting.summary(STRATEGY_ID, prices)
        calendar_reply = client.trading_dates("SH", "20260101", now.strftime("%Y%m%d"), -1)
        trading_days = list(calendar_reply.get("data") or [])
        baseline = json.loads((ROOT / "runtime_data" / "baselines" / ("simulation_%s_external_positions.json" % account_id)).read_text(encoding="utf-8"))
        broker_positions = dict(positions_reply.get("data") or {})
        broker_quantities = {code: int((row or {}).get("volume") or 0) for code, row in broker_positions.items()}
        reconciliation = reconcile_daily_positions(broker_quantities, dict(baseline.get("positions") or {}), owned)
        broker_orders = list(orders_reply.get("data") or [])
        live_orders = live_broker_orders(broker_orders)
        report.update({"signal_event": event, "bridge": ping.get("data"), "account": asset.get("data"),
                       "broker_order_count": len(broker_orders),
                       "broker_open_order_count": len(live_orders),
                       "broker_live_orders": live_orders,
                       "sleeve": sleeve,
                       "reconciliation": reconciliation, "trading_calendar_days": trading_days,
                       "fill_reconciliation": fill_reconciliation})
        plan = build_cycle_plan(
            now=now, signal_event=event,
            activation_signal_not_before=str(registered["activation_policy"]["activation_signal_not_before"]),
            sleeve_summary=sleeve, ticks=dict(ticks_reply.get("data") or {}), account_id=account_id,
            open_orders=list(orders_reply.get("data") or []), reconciliation_status=str(reconciliation.get("status")),
            attributable_fills=accounting.fill_records(STRATEGY_ID), trading_days=trading_days,
        )
        report["plan"] = plan
        if plan is None:
            report["status"] = "ALIGNED_NO_ORDER"
            report["reason"] = "sleeve already matches latest completed-close target or signal is cash"
            path = _write_evidence(report)
            print(json.dumps({"status": report["status"], "evidence": str(path), "broker_call_made": False}, ensure_ascii=False, indent=2))
            return 0
        if plan["side"] == "SELL":
            available = int((broker_positions.get(plan["stock_code"]) or {}).get("available") or 0)
            if available < int(plan["quantity"]):
                raise SimulationExecutionBlocked("strategy sleeve sell quantity is not broker-available (T+1 or reconciliation pending)")
        if not execute:
            report["status"] = "PREFLIGHT_PASSED_NO_ORDER"
            path = _write_evidence(report)
            print(json.dumps({"status": report["status"], "plan": plan, "evidence": str(path), "broker_call_made": False}, ensure_ascii=False, indent=2))
            return 0
        if not bool((ping.get("data") or {}).get("allow_order_methods")):
            raise SimulationExecutionBlocked("QMT Bridge execution route is not loaded")
        claim = store.claim_strategy_execution_attempt({
            "signal_id": plan["signal_id"], "strategy_id": STRATEGY_ID, "account_id": account_id,
            "signal_day": str(event["signal_day"]), "stock_code": plan["stock_code"],
            "side": plan["side"], "quantity": int(plan["quantity"]),
        })
        report["execution_claim"] = claim
        if claim["result"] != "CLAIMED":
            report["status"] = "BLOCKED_DUPLICATE_OR_UNRECONCILED_ATTEMPT"
            path = _write_evidence(report)
            print(json.dumps({"status": report["status"], "claim": claim, "evidence": str(path), "broker_call_made": False}, ensure_ascii=False, indent=2))
            return 2
        control = RuntimeControl(ROOT / "runtime_data" / "control" / "simulation" / "runtime_control.json")
        response: dict[str, Any] | None = None
        try:
            control.arm_simulation_strategy(account_id=account_id, strategy_id=STRATEGY_ID,
                                            approval_scope="Tray-owned v1.1.15 simulation cycle", valid_for_seconds=120)
            # Single fail-closed order gate: formal accounts, a missing or
            # expired local window, and a Coordinator that does not designate
            # this host all deny before any RPC write happens.
            report["execution_admission"] = require_admission_for_root(
                ROOT, "simulation", strategy_id=STRATEGY_ID, authorization=control.status(),
            )
            response = _rpc_submit(redis, {
                "account_id": account_id, "action": plan["side"], "stock_code": plan["stock_code"],
                "volume": int(plan["quantity"]), "price": float(plan["limit_price"]), "price_type": "LIMIT",
                "strategy_name": STRATEGY_ID, "signal_id": plan["signal_id"], "remark": plan["signal_id"],
            }, float(config.get("rpc_timeout_seconds", 12)), account_id)
            report["broker_call_made"] = True
            report["response"] = response
            final_state = "SUBMITTED" if response.get("ok") else (
                "UNKNOWN_TIMEOUT" if "TIMEOUT" in str(response.get("error", "")) else "REJECTED"
            )
            if final_state == "SUBMITTED":
                reply = dict(response.get("data") or {})
                report["order_attribution"] = store.register_strategy_order_attribution({
                    "strategy_id": STRATEGY_ID, "account_id": account_id,
                    "user_order_id": reply.get("user_order_id"), "order_sys_id": reply.get("order_sys_id"),
                    "stock_code": plan["stock_code"], "side": plan["side"], "quantity": int(plan["quantity"]),
                    "source_evidence": "strategy_execution_cycle:" + str(plan["signal_id"]),
                })
            report["attempt_finalization"] = store.finish_strategy_execution_attempt(plan["signal_id"], final_state, response)
            report["status"] = final_state
        finally:
            control.lock_orders("v1.1.15 Tray cycle finished; reconcile broker facts before another order")
        path = _write_evidence(report)
        print(json.dumps({"status": report["status"], "plan": plan, "response": response,
                          "evidence": str(path), "broker_call_made": True, "orders_enabled": False}, ensure_ascii=False, indent=2))
        return 0 if report["status"] == "SUBMITTED" else 2
    except Exception as exc:
        # A local admission/configuration failure happens before any broker
        # RPC.  Finalize the durable claim as rejected so a corrected gate can
        # retry the same deterministic signal without leaving SUBMITTING
        # forever.  Unknown broker responses are never finalized here.
        claim = report.get("execution_claim") or {}
        if claim.get("result") == "CLAIMED" and not report.get("broker_call_made"):
            try:
                report["attempt_finalization"] = store.finish_strategy_execution_attempt(
                    str(claim.get("signal_id") or ""), "REJECTED", {"error": str(exc), "broker_call_made": False}
                )
            except Exception as finalize_exc:
                report["attempt_finalization_error"] = "%s: %s" % (type(finalize_exc).__name__, finalize_exc)
        report.update({"status": "BLOCKED", "error_type": type(exc).__name__, "error": str(exc)})
        path = _write_evidence(report)
        print(json.dumps({"status": "BLOCKED", "error": str(exc), "evidence": str(path),
                          "broker_call_made": bool(report.get("broker_call_made", False)),
                          "orders_enabled": False}, ensure_ascii=False, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
