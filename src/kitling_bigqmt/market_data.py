"""Host-side normalization for the read-only QMT market-data envelope.

QMT's ``get_market_data_ex`` is returned through the embedded bridge as a
JSON-safe DataFrame envelope.  Depending on the adapter version, ``records``
is either a dict of column -> list (the current simulation bridge) or a list
of row dicts.  The reproduction layer must normalize both forms before any
PTrade signal calculation; it must not silently treat a malformed response as
an empty history.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Iterable


class MarketDataFormatError(ValueError):
    """Raised when a QMT response cannot be safely normalized."""


@dataclass(frozen=True)
class DailyBar:
    code: str
    trade_date: str
    close: float | None
    pre_close: float | None
    suspend_flag: int | None
    raw: dict[str, Any]


def _date_text(value: Any) -> str:
    if value is None:
        raise MarketDataFormatError("bar has no date/time value")
    if isinstance(value, datetime):
        return value.strftime("%Y%m%d")
    if isinstance(value, date):
        return value.strftime("%Y%m%d")
    text = str(value).strip()
    if len(text) == 8 and text.isdigit():
        return text[:8]
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).strftime("%Y%m%d")
        except ValueError:
            pass
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        raise MarketDataFormatError("unsupported bar date/time: %r" % (value,))
    # QMT's time field is epoch milliseconds; accept seconds for older bridges.
    if numeric > 10_000_000_000:
        numeric /= 1000.0
    return datetime.fromtimestamp(numeric, tz=timezone.utc).strftime("%Y%m%d")


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        raise MarketDataFormatError("non-numeric price value: %r" % (value,))


def _int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        raise MarketDataFormatError("non-numeric suspendFlag value: %r" % (value,))


def _rows_from_records(records: Any) -> list[dict[str, Any]]:
    if isinstance(records, list):
        if not all(isinstance(row, dict) for row in records):
            raise MarketDataFormatError("records list contains a non-object row")
        return [dict(row) for row in records]
    if isinstance(records, dict):
        if not records:
            return []
        lengths = {len(value) for value in records.values() if isinstance(value, list)}
        if len(lengths) != 1 or any(not isinstance(value, list) for value in records.values()):
            raise MarketDataFormatError("columnar records have inconsistent lengths")
        size = next(iter(lengths))
        columns = list(records)
        return [{column: records[column][index] for column in columns} for index in range(size)]
    raise MarketDataFormatError("unsupported records container: %s" % type(records).__name__)


def _unwrap_frame(value: Any) -> Any:
    if value is None:
        return []
    if isinstance(value, dict) and value.get("__bigqmt_type__") == "DataFrame":
        if "records" not in value:
            raise MarketDataFormatError("DataFrame envelope has no records")
        return value["records"]
    # Some adapters omit the marker but keep the same shape.
    if isinstance(value, dict) and "records" in value:
        return value["records"]
    return value


def normalize_daily_bars(response: dict[str, Any], code: str) -> list[DailyBar]:
    """Normalize one-code ``get_market_data_ex`` response into dated bars.

    ``response`` is the complete RPC response.  A missing code, malformed
    frame, duplicate date, or missing date is an error: callers must block
    signal calculation rather than silently fallback to another data source.
    """
    if not isinstance(response, dict) or not response.get("ok", False):
        raise MarketDataFormatError("QMT market-data response is not ok")
    data = response.get("data")
    if not isinstance(data, dict) or code not in data:
        raise MarketDataFormatError("QMT response has no requested code: %s" % code)
    rows = _rows_from_records(_unwrap_frame(data[code]))
    result: list[DailyBar] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise MarketDataFormatError("bar row is not an object")
        date_value = row.get("stime", row.get("trade_date", row.get("time")))
        trade_date = _date_text(date_value)
        if trade_date in seen:
            raise MarketDataFormatError("duplicate QMT daily bar: %s %s" % (code, trade_date))
        seen.add(trade_date)
        result.append(DailyBar(
            code=code,
            trade_date=trade_date,
            close=_float_or_none(row.get("close")),
            pre_close=_float_or_none(row.get("preClose", row.get("pre_close"))),
            suspend_flag=_int_or_none(row.get("suspendFlag", row.get("suspend_flag"))),
            raw=dict(row),
        ))
    result.sort(key=lambda bar: bar.trade_date)
    return result


def bars_to_dict(bars: Iterable[DailyBar]) -> list[dict[str, Any]]:
    """Stable JSON-friendly representation for evidence artifacts."""
    return [{
        "code": bar.code,
        "trade_date": bar.trade_date,
        "close": bar.close,
        "pre_close": bar.pre_close,
        "suspend_flag": bar.suspend_flag,
    } for bar in bars]
