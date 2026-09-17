"""Fail-closed planning primitives for the Tray-owned simulation cycle.

The functions in this module have no QMT, Redis, filesystem, or clock side
effects.  The runtime script supplies verified facts and may submit at most
one plan only after a short simulation-only control window is armed.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from .simulation_execution import ACCOUNT_ID, STRATEGY_ID, SimulationExecutionBlocked, build_order_plan
from .execution_holding import ActualHoldingBlocked, actual_holding_status, actual_open_entry, normalise_calendar_day


SHANGHAI = ZoneInfo("Asia/Shanghai")
FIRST_EXECUTION_TIME = time(9, 35)
LAST_EXECUTION_TIME = time(14, 50)


def is_execution_window(now: datetime) -> bool:
    """Return whether a local timestamp is inside the bounded A-share window.

    This is deliberately a conservative weekday/time gate, not an exchange
    holiday calendar.  A holiday therefore fails later at quote/account
    preflight, never becomes a reason to retry an order blindly.
    """
    local = now.astimezone(SHANGHAI)
    return local.weekday() < 5 and FIRST_EXECUTION_TIME <= local.time() <= LAST_EXECUTION_TIME


def deterministic_signal_id(signal_event: dict[str, Any], plan: dict[str, Any]) -> str:
    """Create a stable identity for one signal-side-symbol action.

    A retry on the same close signal produces precisely the same identity,
    while a changed side, symbol, or quantity produces a different identity
    that the caller must preflight again.
    """
    payload = {
        "strategy_id": STRATEGY_ID,
        "account_id": ACCOUNT_ID,
        "signal_day": str(signal_event.get("signal_day") or ""),
        "stock_code": str(plan.get("stock_code") or ""),
        "side": str(plan.get("side") or ""),
        "quantity": int(plan.get("quantity") or 0),
    }
    if not payload["signal_day"] or not payload["stock_code"] or payload["quantity"] <= 0:
        raise SimulationExecutionBlocked("cannot create identity for incomplete plan")
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()[:20]
    return "v1_1_15-%s-%s-%s" % (payload["signal_day"], payload["side"].lower(), digest)


def build_cycle_plan(
    *,
    now: datetime,
    signal_event: dict[str, Any],
    activation_signal_not_before: str,
    sleeve_summary: dict[str, Any],
    ticks: dict[str, dict[str, Any]],
    account_id: str,
    open_orders: list[dict[str, Any]],
    reconciliation_status: str,
    attributable_fills: list[dict[str, Any]] | None = None,
    trading_days: list[str] | None = None,
) -> dict[str, Any] | None:
    """Return exactly one executable action, or block before any broker call."""
    if str(account_id) != ACCOUNT_ID:
        raise SimulationExecutionBlocked("simulation account binding mismatch")
    if not is_execution_window(now):
        raise SimulationExecutionBlocked("outside bounded simulation execution window")
    if list(open_orders):
        raise SimulationExecutionBlocked("broker has open orders; reconcile before another submission")
    if str(reconciliation_status).upper() != "PASSED":
        raise SimulationExecutionBlocked("external baseline and sleeve reconciliation is not passed")
    today = now.astimezone(SHANGHAI).strftime("%Y%m%d")
    try:
        calendar_days = {normalise_calendar_day(day) for day in list(trading_days or []) if str(day)}
    except ActualHoldingBlocked as exc:
        raise SimulationExecutionBlocked("QMT exchange calendar guard: %s" % exc)
    if not calendar_days or today not in calendar_days:
        raise SimulationExecutionBlocked("QMT exchange calendar does not identify today as a trading day")
    plan = build_order_plan(
        signal_event=signal_event,
        activation_signal_not_before=activation_signal_not_before,
        trade_day=today,
        sleeve_summary=sleeve_summary,
        ticks=ticks,
    )
    if plan is None:
        return None
    # PTrade v1.1.15 deliberately permits risk exits during its ordinary
    # five-day hold.  Only ordinary rotations must use the real QMT fill day
    # after an ISOLATE_NEW activation; virtual shadow fills are never adopted.
    if plan["side"] == "SELL" and not str(plan.get("reason") or "").startswith("RISK_"):
        try:
            actual_entry = actual_open_entry(list(attributable_fills or []), plan["stock_code"])
            if actual_entry is None:
                raise ActualHoldingBlocked("strategy-owned position has no open real-fill entry")
            holding = actual_holding_status(
                actual_entry["entry_day"], str(signal_event.get("signal_day") or ""),
                list(trading_days or ()), 5,
            )
        except ActualHoldingBlocked as exc:
            raise SimulationExecutionBlocked("real-fill holding-period guard: %s" % exc)
        if not holding["allowed"]:
            raise SimulationExecutionBlocked(
                "real-fill holding-period guard: %s/%s completed sessions"
                % (holding["actual_hold_days"], holding["minimum_hold_days"])
            )
        if str(signal_event.get("signal_day") or "") >= now.astimezone(SHANGHAI).strftime("%Y%m%d"):
            raise SimulationExecutionBlocked("a completed-close signal executes on a later trading day")
        plan["actual_holding"] = holding
    return {**plan, "signal_id": deterministic_signal_id(signal_event, plan)}
