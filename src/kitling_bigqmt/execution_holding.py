"""Real-fill holding-period guard for the v1.1.15 simulation adapter.

The frozen v1.1.15 close-shadow state remains the signal source.  This layer
does not alter its ranking, SMA, risk, or target rules; it prevents an
ordinary rotation from treating a pre-activation *virtual* fill as a broker
fill in an ISOLATE_NEW sleeve.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo


class ActualHoldingBlocked(ValueError):
    pass


SHANGHAI = ZoneInfo("Asia/Shanghai")


def _day_from_fill_time(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        raise ActualHoldingBlocked("attributable fill has no fill_time")
    try:
        return datetime.fromtimestamp(float(text), tz=SHANGHAI).strftime("%Y%m%d")
    except (TypeError, ValueError, OSError, OverflowError):
        try:
            return datetime.fromisoformat(text).astimezone(SHANGHAI).strftime("%Y%m%d")
        except ValueError:
            raise ActualHoldingBlocked("attributable fill has an unparseable fill_time")


def normalise_calendar_day(value: Any) -> str:
    """Accept QMT's YYYYMMDD strings and its millisecond epoch calendar rows."""
    text = str(value or "").strip()
    digits = "".join(char for char in text if char.isdigit())
    if len(digits) == 8:
        return digits
    try:
        epoch = float(text)
        # QMT BigQMT returns millisecond epochs from get_trading_dates on this
        # terminal; retaining the seconds path keeps the adapter portable.
        if epoch > 100000000000:
            epoch /= 1000.0
        return datetime.fromtimestamp(epoch, tz=SHANGHAI).strftime("%Y%m%d")
    except (TypeError, ValueError, OSError, OverflowError):
        raise ActualHoldingBlocked("QMT trading calendar contains an unparseable day")


def actual_open_entry(fills: list[dict[str, Any]], stock_code: str) -> dict[str, Any] | None:
    """Derive the current lot's entry from the fill-driven sleeve ledger."""
    relevant = [row for row in fills if str(row.get("stock_code") or "") == str(stock_code)]
    relevant.sort(key=lambda row: (str(row.get("fill_time") or ""), str(row.get("fill_id") or "")))
    quantity = 0
    entry: dict[str, Any] | None = None
    entry_fill_ids: list[str] = []
    for row in relevant:
        side = str(row.get("side") or "").upper()
        amount = int(row.get("quantity") or 0)
        if side not in ("BUY", "SELL") or amount <= 0:
            raise ActualHoldingBlocked("invalid attributable sleeve fill")
        if side == "BUY":
            if quantity == 0:
                entry = {"stock_code": str(stock_code), "entry_day": _day_from_fill_time(row.get("fill_time"))}
                entry_fill_ids = []
            quantity += amount
            entry_fill_ids.append(str(row.get("fill_id") or ""))
        else:
            if amount > quantity:
                raise ActualHoldingBlocked("sleeve sell exceeds prior attributable buys")
            quantity -= amount
            if quantity == 0:
                entry = None
                entry_fill_ids = []
    if quantity <= 0:
        return None
    if entry is None:
        raise ActualHoldingBlocked("open sleeve position has no attributable entry")
    return {**entry, "quantity": quantity, "fill_ids": entry_fill_ids}


def actual_holding_status(
    entry_day: str,
    signal_day: str,
    trading_days: list[str],
    minimum_hold_days: int = 5,
) -> dict[str, Any]:
    """Count entry day as day one, matching v1.1.15's close-state counter."""
    if int(minimum_hold_days) < 1:
        raise ValueError("minimum_hold_days must be positive")
    entry = str(entry_day or "")
    signal = str(signal_day or "")
    normalized = sorted({normalise_calendar_day(day) for day in trading_days if str(day)})
    if entry not in normalized:
        raise ActualHoldingBlocked("actual entry day is absent from QMT trading calendar")
    if signal not in normalized:
        raise ActualHoldingBlocked("signal day is absent from QMT trading calendar")
    if signal < entry:
        raise ActualHoldingBlocked("signal day precedes actual entry")
    elapsed = [day for day in normalized if entry <= day <= signal]
    return {
        "entry_day": entry,
        "signal_day": signal,
        "actual_hold_days": len(elapsed),
        "minimum_hold_days": int(minimum_hold_days),
        "allowed": len(elapsed) >= int(minimum_hold_days),
    }
