"""Read-only evidence builder for QMT full-tick health.

This module deliberately reports QMT fields as observed.  It does not infer a
broker-specific meaning for ``stockStatus`` and it never replaces an unusable
QMT quote with a third-party source.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .state_store import quote_age_seconds


def inspect_tick(stock_code: str, tick: dict[str, Any], received_at: str, max_age_seconds: float) -> dict[str, Any]:
    """Return an explainable, source-qualified health observation."""
    row = dict(tick or {})
    age_seconds = quote_age_seconds(row.get("timetag"), received_at)
    empty_book = not any(float(value or 0.0) for value in (
        list(row.get("askPrice") or []) + list(row.get("bidPrice") or [])
    ))
    no_activity = float(row.get("amount") or 0.0) == 0.0 and float(row.get("volume") or 0.0) == 0.0
    fresh = age_seconds is not None and age_seconds <= float(max_age_seconds)
    observations = []
    if not fresh:
        observations.append("STALE_OR_UNKNOWN_TIMETAG")
    if no_activity:
        observations.append("ZERO_TRADE_ACTIVITY")
    if empty_book:
        observations.append("EMPTY_FIVE_LEVEL_BOOK")
    if not observations:
        observations.append("HEALTHY_SNAPSHOT")
    return {
        "stock_code": stock_code,
        "source": "QMT.get_full_tick",
        "source_event_time": row.get("timetag"),
        "received_at": received_at,
        "age_seconds": age_seconds,
        "freshness_state": "FRESH" if fresh else "STALE",
        "stock_status_observed": row.get("stockStatus"),
        "last_price": row.get("lastPrice"),
        "amount": row.get("amount"),
        "volume": row.get("volume"),
        "empty_five_level_book": empty_book,
        "observations": observations,
        "admission": "ALLOWED" if fresh else "BLOCKED",
    }


def inspect_response(response: dict[str, Any], codes: list[str], max_age_seconds: float) -> dict[str, Any]:
    """Normalize one Redis RPC response into an immutable diagnostic sample."""
    received_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    ticks = dict(response.get("data") or {})
    results = [inspect_tick(str(code), dict(ticks.get(code) or {}), received_at, max_age_seconds) for code in codes]
    return {
        "schema_version": 1,
        "received_at": received_at,
        "source": "simulation_bigqmt_redis_rpc",
        "max_age_seconds": float(max_age_seconds),
        "symbols": results,
        "status": "PASSED" if all(item["admission"] == "ALLOWED" for item in results) else "ATTENTION",
        "orders_enabled": False,
    }
