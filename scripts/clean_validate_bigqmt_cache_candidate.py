"""Clean and validate a bounded BigQMT cache sample without writing to the lake.

The output is a local evidence/candidate artifact only.  No download, Redis
write, broker call, Parquet write, or catalog/LATEST update is performed.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from kitling_bigqmt.readonly_rpc import ReadOnlyBigQmtClient  # noqa: E402
from kitling_bigqmt.redis_resp import RedisRespClient  # noqa: E402
from kitling_bigqmt.machine_config import load_gateway  # noqa: E402

SHANGHAI = timezone(timedelta(hours=8))
FIELDS = ["time", "open", "high", "low", "close", "volume", "amount"]
EXPECTED_BARS = {"1m": 241, "5m": 48}


def _rows(response: dict[str, Any], code: str) -> list[dict[str, Any]]:
    if not response.get("ok"):
        raise ValueError("QMT response is not ok")
    frame = (response.get("data") or {}).get(code)
    if not isinstance(frame, dict):
        raise ValueError("QMT response has no frame for %s" % code)
    records = frame.get("records", frame)
    if isinstance(records, dict):
        values = list(records.values())
        if not values or any(not isinstance(value, list) for value in values):
            raise ValueError("unsupported columnar records")
        lengths = {len(value) for value in values}
        if len(lengths) != 1:
            raise ValueError("columnar records have inconsistent lengths")
        return [{column: records[column][index] for column in records} for index in range(next(iter(lengths), 0))]
    if isinstance(records, list) and all(isinstance(item, dict) for item in records):
        return [dict(item) for item in records]
    raise ValueError("unsupported QMT record envelope")


def _timestamp(value: Any) -> float:
    number = float(value)
    return number / 1000.0 if number > 10_000_000_000 else number


def _time_text(value: Any) -> str:
    return datetime.fromtimestamp(_timestamp(value), tz=SHANGHAI).isoformat()


def _number(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("%s is non-numeric" % field) from exc
    if not math.isfinite(number):
        raise ValueError("%s is non-finite" % field)
    return number


def _clean_rows(raw_rows: list[dict[str, Any]], code: str, period: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    cleaned: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_rows):
        try:
            ts = _timestamp(raw.get("time"))
            dt = datetime.fromtimestamp(ts, tz=SHANGHAI)
            values = {field: _number(raw.get(field), field) for field in FIELDS[1:]}
            if min(values[field] for field in ("open", "high", "low", "close")) <= 0:
                raise ValueError("non_positive_ohlc")
            if values["high"] < max(values["open"], values["low"], values["close"]):
                raise ValueError("high_relationship")
            if values["low"] > min(values["open"], values["high"], values["close"]):
                raise ValueError("low_relationship")
            if values["volume"] < 0 or values["amount"] < 0:
                raise ValueError("negative_volume_or_amount")
            item = {
                "code": code.upper(),
                "bar_time": dt.isoformat(),
                "trade_date": dt.strftime("%Y%m%d"),
                "period": period,
                "adjustment_mode": "none",
                "open": values["open"], "high": values["high"],
                "low": values["low"], "close": values["close"],
                "volume_lots": values["volume"], "amount_yuan": values["amount"],
                "source": "bigqmt_cache",
            }
            cleaned.append(item)
        except (TypeError, ValueError, OverflowError) as exc:
            # Some QMT caches include zero-filled daily rows before an
            # instrument's listing date (notably 688981.SH). They are not
            # valid market bars, so quarantine them rather than treating them
            # as a repairable price value.
            try:
                zero_placeholder = (str(exc) == "non_positive_ohlc" and
                                    all(float(raw.get(field, 0) or 0) == 0 for field in ("open", "high", "low", "close")) and
                                    float(raw.get("volume", 0) or 0) == 0 and float(raw.get("amount", 0) or 0) == 0)
            except (TypeError, ValueError):
                zero_placeholder = False
            detail = {"code": code, "period": period, "row": index,
                      "rule": "pre_listing_placeholder" if zero_placeholder else str(exc)}
            try:
                detail["trade_date"] = datetime.fromtimestamp(_timestamp(raw.get("time")), tz=SHANGHAI).strftime("%Y%m%d")
            except (TypeError, ValueError, OverflowError):
                pass
            issues.append(detail)
    cleaned.sort(key=lambda item: item["bar_time"])
    times = [item["bar_time"] for item in cleaned]
    if len(times) != len(set(times)):
        issues.append({"code": code, "period": period, "rule": "duplicate_bar_time"})
    if any(later <= earlier for earlier, later in zip(times, times[1:])):
        issues.append({"code": code, "period": period, "rule": "non_monotonic_bar_time"})
    return cleaned, issues


def _cross_period_checks(cleaned_by_key: dict[tuple[str, str], list[dict[str, Any]]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    issues: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    for (code, period), rows in cleaned_by_key.items():
        if period not in EXPECTED_BARS:
            continue
        counts = Counter(row["trade_date"] for row in rows)
        for day, count in counts.items():
            if count != EXPECTED_BARS[period]:
                issues.append({"code": code, "period": period, "trade_date": day,
                               "rule": "unexpected_session_bar_count", "actual": count,
                               "expected": EXPECTED_BARS[period]})
    daily = {(code, row["trade_date"]): row for (code, period), rows in cleaned_by_key.items()
             if period == "1d" for row in rows}
    for (code, period), rows in cleaned_by_key.items():
        if period not in EXPECTED_BARS:
            continue
        grouped: dict[str, dict[str, float]] = defaultdict(lambda: {"volume": 0.0, "amount": 0.0})
        for row in rows:
            grouped[row["trade_date"]]["volume"] += row["volume_lots"]
            grouped[row["trade_date"]]["amount"] += row["amount_yuan"]
        for day, sums in grouped.items():
            reference = daily.get((code, day))
            if not reference:
                continue
            if abs(sums["volume"] - reference["volume_lots"]) > 1e-6:
                issues.append({"code": code, "period": period, "trade_date": day,
                               "rule": "intraday_volume_not_equal_daily", "intraday": sums["volume"],
                               "daily": reference["volume_lots"]})
            denominator = max(abs(reference["amount_yuan"]), 1.0)
            delta = abs(sums["amount"] - reference["amount_yuan"])
            # QMT aggregates minute amounts with per-bar rounding. Keep the
            # delta visible, but only block material deviations.
            tolerance = max(1000.0, abs(reference["amount_yuan"]) * 1e-5)
            if delta > 1e-6 and delta <= tolerance:
                warnings.append({"code": code, "period": period, "trade_date": day,
                                 "rule": "intraday_amount_rounding_delta", "delta_yuan": delta,
                                 "tolerance_yuan": tolerance})
            elif delta > tolerance:
                issues.append({"code": code, "period": period, "trade_date": day,
                               "rule": "intraday_amount_not_equal_daily", "intraday": sums["amount"],
                               "daily": reference["amount_yuan"]})
    return issues, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only clean/validate BigQMT cache candidate")
    parser.add_argument("--codes", default="600519.SH,000001.SZ,300750.SZ,688981.SH,510300.SH,518880.SH")
    parser.add_argument("--start", default="20260908")
    parser.add_argument("--end", default="20260911")
    parser.add_argument("--config", type=Path, default=None)
    args = parser.parse_args()
    config = load_gateway(ROOT, "simulation") if args.config is None else json.loads(args.config.read_text(encoding="utf-8"))
    codes = list(dict.fromkeys(code.strip().upper() for code in args.codes.split(",") if code.strip()))
    client = ReadOnlyBigQmtClient(RedisRespClient(**dict(config["redis"])), str(config["account_id"]),
                                  float(config.get("rpc_timeout_seconds", 12)))
    cleaned_by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
    errors: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    for code in codes:
        for period in ("1d", "5m", "1m"):
            try:
                raw = _rows(client.market_data_ex([code], FIELDS, period, args.start, args.end, -1, "none", subscribe=False), code)
                cleaned, row_issues = _clean_rows(raw, code, period)
                cleaned_by_key[(code, period)] = cleaned
                issues.extend(row_issues)
            except Exception as exc:
                errors.append({"code": code, "period": period, "error": "%s: %s" % (type(exc).__name__, exc)})
    cross_issues, warnings = _cross_period_checks(cleaned_by_key)
    issues.extend(cross_issues)
    rows = [row for key in sorted(cleaned_by_key) for row in cleaned_by_key[key]]
    report = {
        "schema_version": 1,
        "kind": "bigqmt_cache_clean_validate_candidate",
        "created_at": datetime.now(SHANGHAI).isoformat(),
        "mode": "READ_ONLY_NO_LAKE_WRITE",
        "account_id": str(config["account_id"]),
        "range": {"start": args.start, "end": args.end},
        "codes": codes,
        "periods": ["1d", "5m", "1m"],
        "business_key": ["code", "bar_time", "period", "adjustment_mode"],
        "normalization": {"timezone": "Asia/Shanghai", "volume": "volume_lots", "amount": "amount_yuan",
                           "raw_source": "BigQMT dividend_type=none", "forward_fill": False, "ohlc_clip": False},
        "summary": {"cleaned_rows": len(rows), "issue_count": len(issues), "warning_count": len(warnings), "rpc_error_count": len(errors),
                    "rows_by_period": dict(Counter(row["period"] for row in rows))},
        "quality_issues": issues,
        "quality_warnings": warnings,
        "errors": errors,
        "lake_write": False,
        "global_latest_updated": False,
        "release_status": "CANDIDATE_VALIDATED" if not issues and not errors else "BLOCKED",
        "next_gate": "PIT/adjustment-source validation and separate intraday lake schema review before overlay publication",
        "rows": rows,
    }
    destination = ROOT / "runtime_data" / "evidence" / "simulation" / "qmt_history_cache"
    destination.mkdir(parents=True, exist_ok=True)
    path = destination / ("clean_validate_candidate_%s.json" % datetime.now(SHANGHAI).strftime("%Y%m%d_%H%M%S"))
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"release_status": report["release_status"], "evidence": str(path),
                      "summary": report["summary"], "lake_write": False,
                      "global_latest_updated": False}, ensure_ascii=False, indent=2))
    return 0 if report["release_status"] == "CANDIDATE_VALIDATED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
