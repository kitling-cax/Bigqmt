"""Turn attributable QMT trade rows into idempotent sleeve-fill records."""

from __future__ import annotations

import hashlib
from typing import Any

from .sleeve_accounting import SleeveAccounting, SleeveAccountingError


class FillReconciliationBlocked(ValueError):
    pass


def _field(row: dict[str, Any], *names: str) -> Any:
    for name in names:
        value = row.get(name)
        if value not in (None, ""):
            return value
    return None


def _attribution_for_trade(
    row: dict[str, Any], strategy_id: str, attributions: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Return durable local proof for a bridge-named trade, if one exists."""
    user_order_id = str(_field(row, "user_order_id", "userOrderId") or "")
    order_sys_id = str(_field(row, "order_sys_id", "order_id") or "")
    by_user = {str(item["user_order_id"]): item for item in attributions}
    by_sys = {str(item["order_sys_id"]): item for item in attributions}
    from_user = by_user.get(user_order_id)
    from_sys = by_sys.get(order_sys_id)
    if from_user and from_sys and from_user["attribution_id"] != from_sys["attribution_id"]:
        raise FillReconciliationBlocked("broker trade has conflicting durable order identities")
    attribution = from_user or from_sys
    if attribution is None:
        return None
    if str(attribution.get("strategy_id")) != str(strategy_id):
        raise FillReconciliationBlocked("broker trade maps to another strategy sleeve")
    if user_order_id and user_order_id != str(attribution["user_order_id"]):
        raise FillReconciliationBlocked("broker trade user_order_id conflicts with its durable attribution")
    if order_sys_id and order_sys_id != str(attribution["order_sys_id"]):
        raise FillReconciliationBlocked("broker trade order_sys_id conflicts with its durable attribution")
    return attribution


def normalize_attributable_trade(
    row: dict[str, Any], strategy_id: str, attributions: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Validate a strategy trade, or ignore an unrelated shared-account trade.

    A direct strategy name is valid when Redis identity remains available. If
    QMT only exposes ``BIGQMT_BRIDGE`` after a Redis restart, attribution is
    recovered solely from the local, immutable QMT order-id registry.
    """
    direct_strategy_name = str(row.get("strategy_name") or "") == str(strategy_id)
    attribution = None if direct_strategy_name else _attribution_for_trade(row, strategy_id, attributions)
    if not direct_strategy_name and attribution is None:
        return None
    side = str(_field(row, "action", "side") or "").upper()
    stock_code = str(_field(row, "stock_code", "code") or "").strip()
    try:
        quantity = int(_field(row, "volume", "traded_volume") or 0)
        price = float(_field(row, "price", "traded_price") or 0)
        fee = float(_field(row, "commission", "fee") or 0)
    except (TypeError, ValueError):
        raise FillReconciliationBlocked("attributable broker trade has invalid numeric fields")
    if side not in ("BUY", "SELL") or not stock_code or quantity <= 0 or price <= 0 or fee < 0:
        raise FillReconciliationBlocked("attributable broker trade is incomplete")
    fill_time = _field(row, "traded_time", "trade_time", "fill_time", "traded_at")
    if fill_time in (None, ""):
        raise FillReconciliationBlocked("attributable broker trade has no fill time")
    fill_id = str(_field(row, "trade_id", "traded_id", "business_id") or "").strip()
    if not fill_id:
        fingerprint = "|".join(str(value) for value in (
            _field(row, "order_sys_id", "order_id"), fill_time, stock_code, side, quantity, price, fee,
        ))
        fill_id = "qmt-synthetic-" + hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:24]
    if attribution is not None:
        if stock_code != str(attribution["stock_code"]) or side != str(attribution["side"]):
            raise FillReconciliationBlocked("broker trade fields conflict with its durable attribution")
        if quantity > int(attribution["quantity"]):
            raise FillReconciliationBlocked("broker trade quantity exceeds its durable order attribution")
    return {
        "fill_id": fill_id, "strategy_id": str(strategy_id), "stock_code": stock_code,
        "side": side, "quantity": quantity, "price": price, "fee": fee, "fill_time": str(fill_time),
        "attribution_id": str(attribution["attribution_id"]) if attribution else None,
    }


def reconcile_attributable_trades(
    accounting: SleeveAccounting, strategy_id: str, trades: list[dict[str, Any]],
) -> dict[str, Any]:
    """Idempotently apply only attributable fills from a shared broker account."""
    attributions = accounting.store.strategy_order_attributions(strategy_id)
    records = []
    ignored = 0
    mapped_quantities: dict[str, int] = {}
    for row in list(trades or []):
        record = normalize_attributable_trade(dict(row or {}), strategy_id, attributions)
        if record is None:
            ignored += 1
            continue
        attribution_id = record.pop("attribution_id", None)
        if attribution_id:
            mapped_quantities[attribution_id] = mapped_quantities.get(attribution_id, 0) + int(record["quantity"])
            attribution = next(item for item in attributions if item["attribution_id"] == attribution_id)
            if mapped_quantities[attribution_id] > int(attribution["quantity"]):
                raise FillReconciliationBlocked("broker split fills exceed durable order attribution quantity")
        records.append(record)
    results = []
    for record in records:
        try:
            results.append(accounting.record_fill(record))
        except SleeveAccountingError as exc:
            raise FillReconciliationBlocked("sleeve fill reconciliation failed: %s" % exc)
    return {
        "status": "PASSED", "strategy_id": strategy_id, "broker_trade_count": len(list(trades or [])),
        "attributable_trade_count": len(records), "ignored_unattributable_count": ignored,
        "recorded": sum(1 for result in results if result.get("result") == "RECORDED"),
        "duplicates": sum(1 for result in results if result.get("result") == "DUPLICATE"),
        "fill_results": results,
    }
