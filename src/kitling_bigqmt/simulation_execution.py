"""Pure, fail-closed order planning for the approved v1.1.15 simulation sleeve.

This module has no broker, Redis, filesystem, or clock dependency.  The Tray
runner supplies verified facts and owns the short QMT execution window.
"""

from __future__ import annotations

from typing import Any


class SimulationExecutionBlocked(ValueError):
    pass


STRATEGY_ID = "S10_D1_U25_NO_ALCOHOL_5D_SIM_MAIN_V1_1_15"
ACCOUNT_ID = "90000001"
LOT_SIZE = 100
TARGET_CASH_RATIO = 0.98
COMMISSION_RATE = 0.0001
MIN_COMMISSION = 5.0
BUY_PROTECTION = 0.003
SELL_PROTECTION = 0.003


def _positive(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise SimulationExecutionBlocked("%s must be a positive number" % field)
    if number <= 0:
        raise SimulationExecutionBlocked("%s must be a positive number" % field)
    return number


def _best_price(tick: dict[str, Any], side: str) -> float:
    levels = tick.get("askPrice") if side == "BUY" else tick.get("bidPrice")
    for value in levels or ():
        try:
            if float(value) > 0:
                return float(value)
        except (TypeError, ValueError):
            pass
    return _positive(tick.get("lastPrice"), "live lastPrice")


def build_order_plan(
    *,
    signal_event: dict[str, Any],
    activation_signal_not_before: str,
    trade_day: str,
    sleeve_summary: dict[str, Any],
    ticks: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    """Return one sell-before-buy order, or ``None`` when already aligned.

    Existing broker holdings do not enter this calculation: only positions
    recorded in the v1.1.15 sleeve are eligible to sell.
    """
    signal_day = str(signal_event.get("signal_day") or "")
    if not signal_day or signal_day < str(activation_signal_not_before):
        raise SimulationExecutionBlocked("signal predates direct-simulation activation")
    signal = dict(signal_event.get("signal") or {})
    desired = signal.get("desired_qmt")
    positions = list(sleeve_summary.get("positions") or [])
    # A same-day close may be materialized so the cycle layer can apply the
    # real-fill holding-period guard first. Entries (and future-day signals)
    # remain blocked here; the cycle layer applies the final completed-close
    # timing guard after that holding check.
    if signal_day > str(trade_day) or (signal_day == str(trade_day) and not positions):
        raise SimulationExecutionBlocked("a completed-close signal executes on a later trading day")
    if len(positions) > 1:
        raise SimulationExecutionBlocked("v1.1.15 sleeve has more than one position")
    current = positions[0] if positions else None
    if current and int(current.get("quantity") or 0) <= 0:
        raise SimulationExecutionBlocked("sleeve position has non-positive quantity")

    # A switch is always split: sell confirmation/reconciliation must finish
    # before a later runner invocation is allowed to buy the new target.
    if current and str(current.get("stock_code")) != str(desired or ""):
        code = str(current["stock_code"])
        raw_price = _best_price(dict(ticks.get(code) or {}), "SELL")
        return {
            "strategy_id": STRATEGY_ID, "account_id": ACCOUNT_ID,
            "signal_day": signal_day, "stock_code": code, "side": "SELL",
            "quantity": int(current["quantity"]),
            "quote_price": raw_price,
            "limit_price": round(raw_price * (1 - SELL_PROTECTION), 3),
            "reason": str(signal.get("reason") or "TARGET_EXIT_OR_SWITCH"),
        }
    if current:
        return None
    if not desired:
        return None

    code = str(desired)
    quote_price = _best_price(dict(ticks.get(code) or {}), "BUY")
    limit_price = round(quote_price * (1 + BUY_PROTECTION), 3)
    cash = _positive(sleeve_summary.get("cash"), "strategy sleeve cash")
    budget = cash * TARGET_CASH_RATIO
    quantity = int((budget - MIN_COMMISSION) / limit_price / LOT_SIZE) * LOT_SIZE
    if quantity < LOT_SIZE:
        raise SimulationExecutionBlocked("strategy sleeve cannot fund one ETF lot")
    fee = max(MIN_COMMISSION, quantity * limit_price * COMMISSION_RATE)
    if quantity * limit_price + fee > cash:
        raise SimulationExecutionBlocked("buy would exceed strategy sleeve cash")
    return {
        "strategy_id": STRATEGY_ID, "account_id": ACCOUNT_ID,
        "signal_day": signal_day, "stock_code": code, "side": "BUY",
        "quantity": quantity, "quote_price": quote_price, "limit_price": limit_price,
        "estimated_fee": fee,
        "reason": str(signal.get("reason") or "TARGET_ENTRY"),
    }
