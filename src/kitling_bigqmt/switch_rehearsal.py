"""Offline, broker-free rehearsal of one split v1.1.15 simulation switch.

The live cycle submits at most one order per invocation and deliberately
splits a switch into a sell leg followed by a later buy leg.  This module
replays both legs against real sleeve facts and the production order-planning
code, so an operator can prove before the open that the next session will
produce valid order parameters -- and see exactly which guard would block it.

It has no broker, Redis, filesystem, or clock dependency: every fact is
supplied by the caller, and nothing here can submit or claim an order.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from .execution_holding import (
    ActualHoldingBlocked,
    actual_holding_status,
    actual_open_entry,
)
from .simulation_cycle import build_cycle_plan
from .simulation_execution import (
    ACCOUNT_ID,
    COMMISSION_RATE,
    MIN_COMMISSION,
    STRATEGY_ID,
    SimulationExecutionBlocked,
)

SHANGHAI = ZoneInfo("Asia/Shanghai")
DEFAULT_REHEARSAL_TIME = "09:36"
MINIMUM_HOLD_DAYS = 5
REHEARSAL_REASON = "REHEARSAL_ORDINARY_ROTATION"


def _fee(quantity: int, price: float) -> float:
    return max(MIN_COMMISSION, int(quantity) * float(price) * COMMISSION_RATE)


def _rehearsal_now(trade_day: str, at_time: str) -> datetime:
    return datetime.strptime("%s %s" % (trade_day, at_time), "%Y%m%d %H:%M").replace(tzinfo=SHANGHAI)


def _rehearse_leg(
    *,
    signal_day: str,
    desired_qmt: str,
    trade_day: str,
    at_time: str,
    trading_days: list[Any],
    activation_signal_not_before: str,
    sleeve_summary: dict[str, Any],
    ticks: dict[str, dict[str, Any]],
    attributable_fills: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return the plan this sleeve state would produce, or the blocking guard."""
    event = {
        "signal_day": str(signal_day),
        "signal": {"desired_qmt": str(desired_qmt or ""), "reason": REHEARSAL_REASON},
    }
    try:
        plan = build_cycle_plan(
            now=_rehearsal_now(trade_day, at_time),
            signal_event=event,
            activation_signal_not_before=str(activation_signal_not_before),
            sleeve_summary=sleeve_summary,
            ticks=ticks,
            account_id=ACCOUNT_ID,
            open_orders=[],
            reconciliation_status="PASSED",
            attributable_fills=list(attributable_fills),
            trading_days=list(trading_days),
        )
    except SimulationExecutionBlocked as exc:
        return {"status": "BLOCKED", "blocked_reason": str(exc)}
    if plan is None:
        return {"status": "ALIGNED_NO_ORDER"}
    return {"status": "PLAN", "plan": plan}


def holding_guard_view(
    *,
    attributable_fills: list[dict[str, Any]],
    stock_code: str,
    signal_day: str,
    trading_days: list[Any],
) -> dict[str, Any]:
    """Report the real-fill holding counter that gates an ordinary rotation."""
    entry = actual_open_entry(list(attributable_fills), str(stock_code))
    if entry is None:
        return {"stock_code": str(stock_code), "entry_day": None, "status": "NO_OPEN_REAL_FILL"}
    try:
        status = actual_holding_status(
            entry["entry_day"], str(signal_day), list(trading_days), MINIMUM_HOLD_DAYS,
        )
    except ActualHoldingBlocked as exc:
        return {"stock_code": str(stock_code), "entry_day": entry["entry_day"],
                "status": "UNEVALUABLE", "blocked_reason": str(exc)}
    return {"stock_code": str(stock_code), "entry_day": entry["entry_day"],
            "status": "ALLOWED" if status["allowed"] else "HELD",
            "actual_hold_days": status["actual_hold_days"],
            "minimum_hold_days": status["minimum_hold_days"], "detail": status}


def rehearse_switch(
    *,
    sleeve_summary: dict[str, Any],
    attributable_fills: list[dict[str, Any]],
    ticks: dict[str, dict[str, Any]],
    signal_day: str,
    trade_day: str,
    trading_days: list[Any],
    activation_signal_not_before: str,
    desired_qmt: str,
    at_time: str = DEFAULT_REHEARSAL_TIME,
    assume_trade_day_is_trading: bool = False,
) -> dict[str, Any]:
    """Replay the sell leg and the follow-on buy leg of one planned switch.

    The buy leg is only reachable when the runner is invoked a second time
    inside the same bounded window, after the sell fill reconciles.  The
    report states that requirement instead of hiding it, because a runner
    that stops after one invocation would leave the sleeve in cash.
    """
    if assume_trade_day_is_trading:
        calendar = sorted({str(day) for day in trading_days} | {str(signal_day), str(trade_day)})
    positions = list(sleeve_summary.get("positions") or [])
    report: dict[str, Any] = {
        "schema_version": 1,
        "kind": "v1_1_15_switch_rehearsal",
        "generated_at": datetime.now(SHANGHAI).isoformat(),
        "strategy_id": STRATEGY_ID,
        "account_id": ACCOUNT_ID,
        "signal_day": str(signal_day),
        "trade_day": str(trade_day),
        "desired_qmt": str(desired_qmt or ""),
        "broker_call_made": False,
        "orders_enabled": False,
        "execution_claim_made": False,
        "assumed_fill_price_is_quote": True,
    }
    held = str(positions[0].get("stock_code")) if positions else ""
    if held:
        report["holding_guard"] = holding_guard_view(
            attributable_fills=attributable_fills, stock_code=held,
            signal_day=signal_day, trading_days=trading_days,
        )

    first = _rehearse_leg(
        signal_day=signal_day, desired_qmt=desired_qmt, trade_day=trade_day, at_time=at_time,
        trading_days=trading_days, activation_signal_not_before=activation_signal_not_before,
        sleeve_summary=sleeve_summary, ticks=ticks, attributable_fills=attributable_fills,
    )
    if first["status"] != "PLAN":
        report["sell_leg"] = first
        report["buy_leg"] = {"status": "NOT_REHEARSED", "blocked_reason": "first leg produced no sell"}
        report["verdict"] = "SWITCH_NOT_AVAILABLE_%s" % first["status"]
        report["second_invocation_required"] = False
        return report

    if str(first["plan"]["side"]) != "SELL":
        # The sleeve is already flat: one buy leg completes the rotation.
        report["sell_leg"] = {"status": "ALIGNED_NO_SELL_REQUIRED"}
        report["buy_leg"] = first
        report["verdict"] = "SINGLE_BUY_LEG_REHEARSED_OK"
        report["second_invocation_required"] = False
        return report

    report["sell_leg"] = first
    sell = dict(first["plan"])
    quantity = int(sell["quantity"])
    quote = float(sell["quote_price"])
    proceeds = quantity * quote - _fee(quantity, quote)
    post_sell_summary = {
        "strategy_id": STRATEGY_ID,
        "cash": float(sleeve_summary.get("cash") or 0.0) + proceeds,
        "positions": [],
    }
    report["projected_sleeve_after_sell"] = {
        "cash": post_sell_summary["cash"],
        "sold_stock_code": sell["stock_code"],
        "sold_quantity": quantity,
        "assumed_sell_price": quote,
        "estimated_fee": _fee(quantity, quote),
    }
    report["buy_leg"] = _rehearse_leg(
        signal_day=signal_day, desired_qmt=desired_qmt, trade_day=trade_day, at_time=at_time,
        trading_days=trading_days, activation_signal_not_before=activation_signal_not_before,
        sleeve_summary=post_sell_summary, ticks=ticks, attributable_fills=[],
    )
    buy = report["buy_leg"]
    report["second_invocation_required"] = True
    if buy["status"] != "PLAN" or str(buy["plan"]["side"]) != "BUY":
        report["verdict"] = "BUY_LEG_NOT_REHEARSED"
        return report
    report["signal_ids_distinct"] = sell["signal_id"] != buy["plan"]["signal_id"]
    report["verdict"] = "SWITCH_REHEARSED_OK" if report["signal_ids_distinct"] else "SIGNAL_ID_COLLISION"
    return report
