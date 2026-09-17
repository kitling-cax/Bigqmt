"""Read-only quality check for K-line data already cached by BigQMT.

The verifier never calls ``download_history_data`` and never writes to QMT,
Redis, or a broker.  It only requests cached ``get_market_data_ex`` frames and
writes a local JSON evidence file for a candidate data-source release.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kitling_bigqmt.readonly_rpc import ReadOnlyBigQmtClient  # noqa: E402
from kitling_bigqmt.redis_resp import RedisRespClient  # noqa: E402
from kitling_bigqmt.machine_config import load_gateway  # noqa: E402


SHANGHAI = ZoneInfo("Asia/Shanghai")
FIELDS = ["time", "open", "high", "low", "close", "volume", "amount"]


def _rows(response: dict[str, Any], code: str) -> list[dict[str, Any]]:
    if not response.get("ok"):
        raise ValueError("QMT response is not ok")
    frame = (response.get("data") or {}).get(code)
    if not isinstance(frame, dict):
        raise ValueError("QMT response has no frame for %s" % code)
    records = frame.get("records") if "records" in frame else frame
    if isinstance(records, dict):
        lengths = {len(value) for value in records.values() if isinstance(value, list)}
        if len(lengths) != 1 or any(not isinstance(value, list) for value in records.values()):
            raise ValueError("columnar records have inconsistent lengths")
        return [{column: records[column][index] for column in records} for index in range(next(iter(lengths), 0))]
    if isinstance(records, list) and all(isinstance(item, dict) for item in records):
        return [dict(item) for item in records]
    raise ValueError("unsupported QMT record envelope")


def _time_text(value: Any) -> str:
    numeric = float(value)
    if numeric > 10_000_000_000:
        numeric /= 1000.0
    return datetime.fromtimestamp(numeric, tz=SHANGHAI).isoformat()


def _number(value: Any, field: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("%s is non-numeric" % field) from exc


def inspect_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"status": "BLOCKED", "reason": "empty cached frame", "rows": 0}
    violations: list[dict[str, Any]] = []
    timestamps: list[float] = []
    dates: dict[str, int] = {}
    for index, row in enumerate(rows):
        try:
            timestamp = _number(row.get("time"), "time")
            open_price, high, low, close = (_number(row.get(key), key) for key in ("open", "high", "low", "close"))
            volume, amount = _number(row.get("volume"), "volume"), _number(row.get("amount"), "amount")
            if min(open_price, high, low, close) <= 0:
                violations.append({"row": index, "rule": "positive_ohlc"})
            if high < max(open_price, low, close) or low > min(open_price, high, close):
                violations.append({"row": index, "rule": "ohlc_relationship"})
            if volume < 0 or amount < 0:
                violations.append({"row": index, "rule": "nonnegative_volume_amount"})
            timestamps.append(timestamp)
            day = _time_text(timestamp).split("T", 1)[0]
            dates[day] = dates.get(day, 0) + 1
        except ValueError as exc:
            violations.append({"row": index, "rule": "numeric_fields", "detail": str(exc)})
    monotonic = all(later > earlier for earlier, later in zip(timestamps, timestamps[1:]))
    unique = len(set(timestamps)) == len(timestamps)
    if not monotonic:
        violations.append({"rule": "monotonic_time"})
    if not unique:
        violations.append({"rule": "unique_time"})
    return {
        "status": "PASSED" if not violations else "BLOCKED",
        "rows": len(rows), "first_time": _time_text(timestamps[0]) if timestamps else None,
        "last_time": _time_text(timestamps[-1]) if timestamps else None,
        "rows_by_trade_date": dates, "columns": sorted({key for row in rows for key in row}),
        "violations": violations,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate cached BigQMT daily/intraday bars without downloading.")
    parser.add_argument("--codes", default="510300.SH,160723.SZ,518880.SH,159915.SZ")
    parser.add_argument("--start", default="20260908")
    parser.add_argument("--end", default="20260912")
    parser.add_argument("--config", type=Path, default=None)
    args = parser.parse_args()
    config = load_gateway(ROOT, "simulation") if args.config is None else json.loads(args.config.read_text(encoding="utf-8"))
    if str(config.get("environment")) != "simulation" or str(config.get("account_id")) != "90000001":
        raise SystemExit("history-cache verification is bound to simulation account 90000001")
    client = ReadOnlyBigQmtClient(RedisRespClient(**dict(config["redis"])), str(config["account_id"]),
                                  float(config.get("rpc_timeout_seconds", 12)))
    codes = [item.strip().upper() for item in args.codes.split(",") if item.strip()]
    results: list[dict[str, Any]] = []
    for code in codes:
        for period, dividends in (("1d", ("none", "front", "back")), ("5m", ("none", "front")), ("1m", ("none", "front"))):
            frames: dict[str, list[dict[str, Any]]] = {}
            for dividend_type in dividends:
                item: dict[str, Any] = {"code": code, "period": period, "dividend_type": dividend_type}
                try:
                    rows = _rows(client.market_data_ex([code], FIELDS, period, args.start, args.end, -1, dividend_type), code)
                    frames[dividend_type] = rows
                    item.update(inspect_rows(rows))
                except Exception as exc:
                    item.update({"status": "BLOCKED", "error_type": type(exc).__name__, "error": str(exc)})
                results.append(item)
            if "none" in frames:
                for item in [row for row in results if row["code"] == code and row["period"] == period and row["dividend_type"] != "none"]:
                    adjusted = frames.get(str(item["dividend_type"]))
                    if adjusted is not None:
                        item["adjustment_comparison"] = {
                            "same_row_count": len(frames["none"]) == len(adjusted),
                            "changed_close_rows": sum(
                                float(left.get("close") or 0) != float(right.get("close") or 0)
                                for left, right in zip(frames["none"], adjusted)
                            ),
                        }
    passed = all(item.get("status") == "PASSED" for item in results)
    report = {
        "schema_version": 1, "kind": "bigqmt_cached_history_readonly_quality_check",
        "created_at": datetime.now(SHANGHAI).isoformat(), "account_id": "90000001",
        "source": "BigQMT cached get_market_data_ex", "download_called": False,
        "broker_call_made": False, "orders_enabled": False, "start": args.start, "end": args.end,
        "results": results, "status": "PASSED" if passed else "BLOCKED",
    }
    evidence_dir = ROOT / "runtime_data" / "evidence" / "simulation" / "qmt_history_cache"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    evidence_path = evidence_dir / ("cached_history_quality_%s.json" % datetime.now(SHANGHAI).strftime("%Y%m%d_%H%M%S"))
    evidence_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": report["status"], "evidence": str(evidence_path), "summary": [
        {key: item.get(key) for key in ("code", "period", "dividend_type", "status", "rows", "first_time", "last_time", "adjustment_comparison")}
        for item in results
    ], "download_called": False, "broker_call_made": False, "orders_enabled": False}, ensure_ascii=False, indent=2))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
