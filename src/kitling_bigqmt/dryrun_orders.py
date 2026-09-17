"""Fail-closed local planner for simulation order Dry-run evidence.

This module deliberately has no Redis or QMT dependency. It cannot submit,
cancel, or query a broker order; it only validates and records a local intent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .state_store import RuntimeStateStore


class DryRunRejected(ValueError):
    pass


@dataclass(frozen=True)
class DryRunOrderPlanner:
    store: RuntimeStateStore

    def plan(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.store.record_dryrun_intent(self._normalize(payload))

    @staticmethod
    def _normalize(payload: dict[str, Any]) -> dict[str, Any]:
        required = (
            "request_id", "strategy_id", "signal_id", "stock_code", "side", "quantity",
            "limit_price", "quote_admission", "preflight_admission", "parity_admission",
        )
        missing = [name for name in required if not payload.get(name)]
        if missing:
            raise DryRunRejected("missing required fields: %s" % ", ".join(missing))
        if payload.get("environment") != "simulation":
            raise DryRunRejected("dry-run is simulation-only")
        if bool(payload.get("orders_enabled", False)):
            raise DryRunRejected("orders_enabled must remain false for dry-run")
        if payload.get("quote_admission") != "ALLOWED":
            raise DryRunRejected("quote is not admitted by freshness gate")
        if payload.get("preflight_admission") != "ALLOWED":
            raise DryRunRejected("runtime preflight is not admitted")
        if payload.get("parity_admission") != "ALLOWED":
            raise DryRunRejected("strategy parity is not admitted")
        side = str(payload["side"]).upper()
        if side not in ("BUY", "SELL"):
            raise DryRunRejected("side must be BUY or SELL")
        quantity = int(payload["quantity"])
        if quantity <= 0 or quantity % 100:
            raise DryRunRejected("quantity must be a positive 100-share lot")
        try:
            limit_price = float(payload["limit_price"])
            estimated_fee = float(payload.get("estimated_fee", 0.0))
        except (TypeError, ValueError):
            raise DryRunRejected("limit_price and estimated_fee must be numeric")
        if limit_price <= 0 or estimated_fee < 0:
            raise DryRunRejected("limit_price must be positive and estimated_fee non-negative")
        if side == "BUY":
            try:
                strategy_cash = float(payload["strategy_cash"])
            except (KeyError, TypeError, ValueError):
                raise DryRunRejected("BUY requires numeric strategy_cash")
            if quantity * limit_price + estimated_fee > strategy_cash:
                raise DryRunRejected("BUY exceeds strategy sleeve cash")
        else:
            try:
                owned = int(payload["strategy_owned_quantity"])
                available = int(payload["broker_available_quantity"])
            except (KeyError, TypeError, ValueError):
                raise DryRunRejected("SELL requires strategy_owned_quantity and broker_available_quantity")
            if quantity > owned:
                raise DryRunRejected("SELL exceeds strategy-owned quantity")
            if quantity > available:
                raise DryRunRejected("SELL exceeds broker available quantity")
        return {
            "schema_version": 1,
            "request_id": str(payload["request_id"]),
            "environment": "simulation",
            "strategy_id": str(payload["strategy_id"]),
            "signal_id": str(payload["signal_id"]),
            "stock_code": str(payload["stock_code"]),
            "side": side,
            "quantity": quantity,
            "limit_price": limit_price,
            "estimated_fee": estimated_fee,
            "quote_run_id": payload.get("quote_run_id"),
            "quote_admission": "ALLOWED",
            "preflight_admission": "ALLOWED",
            "parity_admission": "ALLOWED",
            "orders_enabled": False,
            "state": "PLANNED",
        }
