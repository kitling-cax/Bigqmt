"""Validate BigQMT daily rows that are absent from the shared lake.

The validator is intentionally copy-free: it reads QMT and existing Parquet,
then writes only a JSON evidence report.  A passing report is still
``CANDIDATE_ONLY`` until a separate release publisher is approved.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import duckdb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kitling_bigqmt.etf_pool_benchmark import load_pool  # noqa: E402
from kitling_bigqmt.market_data import DailyBar, normalize_daily_bars  # noqa: E402
from kitling_bigqmt.readonly_rpc import ReadOnlyBigQmtClient  # noqa: E402
from kitling_bigqmt.redis_resp import RedisRespClient  # noqa: E402
from kitling_bigqmt.machine_config import load_gateway  # noqa: E402


SHANGHAI = ZoneInfo("Asia/Shanghai")
DEFAULT_A_SHARE_CODES = ("600519.SH", "000001.SZ", "300750.SZ", "688981.SH", "600000.SH", "000333.SZ")


def _lake_rows(glob_path: str, codes: list[str], start: str, end: str) -> dict[tuple[str, str], dict[str, Any]]:
    placeholders = ", ".join("?" for _ in codes)
    query = """
        SELECT code, strftime(trade_date, '%%Y%%m%%d') AS trade_date,
               open, high, low, close, volume, amount, source
        FROM read_parquet(?, union_by_name=true, hive_partitioning=true)
        WHERE code IN (%s)
          AND trade_date BETWEEN CAST(? AS DATE) AND CAST(? AS DATE)
    """ % placeholders
    with duckdb.connect() as db:
        rows = db.execute(query, [glob_path, *codes, "%s-%s-%s" % (start[:4], start[4:6], start[6:]),
                                  "%s-%s-%s" % (end[:4], end[4:6], end[6:])]).fetchall()
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for code, day, opn, high, low, close, volume, amount, source in rows:
        result[(str(code), str(day))] = {
            "open": opn, "high": high, "low": low, "close": close,
            "volume": volume, "amount": amount, "source": source,
        }
    return result


def _bar_issues(bar: DailyBar) -> list[str]:
    raw = bar.raw
    issues: list[str] = []
    try:
        values = {key: float(raw[key]) for key in ("open", "high", "low", "close")}
        if not all(math.isfinite(value) for value in values.values()):
            issues.append("non_finite_ohlc")
        if min(values.values()) <= 0:
            issues.append("non_positive_ohlc")
        if values["high"] < max(values["open"], values["low"], values["close"]):
            issues.append("high_relationship")
        if values["low"] > min(values["open"], values["high"], values["close"]):
            issues.append("low_relationship")
    except (KeyError, TypeError, ValueError):
        issues.append("non_numeric_ohlc")
    for key in ("volume", "amount"):
        try:
            value = float(raw[key])
            if not math.isfinite(value):
                issues.append("non_finite_%s" % key)
            elif value < 0:
                issues.append("negative_%s" % key)
        except (KeyError, TypeError, ValueError):
            issues.append("non_numeric_%s" % key)
    if bar.trade_date[-2:] and datetime.strptime(bar.trade_date, "%Y%m%d").weekday() >= 5:
        issues.append("weekend_trade_date")
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only BigQMT missing daily candidate validator")
    parser.add_argument("--start", default="20260820")
    parser.add_argument("--end", default="20260911")
    parser.add_argument("--codes", default="")
    parser.add_argument("--lake-root", type=Path, default=Path(r"C:\BigQMT\research\quant_data_lake"))
    args = parser.parse_args()
    extra = [code.strip().upper() for code in args.codes.split(",") if code.strip()]
    codes = list(dict.fromkeys([*DEFAULT_A_SHARE_CODES, *load_pool(ROOT), *extra]))
    config = load_gateway(ROOT, "simulation")
    client = ReadOnlyBigQmtClient(RedisRespClient(**dict(config["redis"])), str(config["account_id"]),
                                  float(config.get("rpc_timeout_seconds", 12)))
    qmt: dict[tuple[str, str], DailyBar] = {}
    errors: dict[str, str] = {}
    issues: list[dict[str, str]] = []
    common_rows: dict[tuple[str, str], dict[str, Any]] = {}
    for code in codes:
        try:
            bars = normalize_daily_bars(client.market_data_ex(
                [code], ["time", "open", "high", "low", "close", "volume", "amount"],
                "1d", args.start, args.end, -1, "none", subscribe=False,
            ), code)
            for bar in bars:
                if args.start <= bar.trade_date <= args.end:
                    qmt[(code, bar.trade_date)] = bar
                    for rule in _bar_issues(bar):
                        issues.append({"code": code, "trade_date": bar.trade_date, "rule": rule})
        except Exception as exc:
            errors[code] = "%s: %s" % (type(exc).__name__, exc)
    lake_glob = str(args.lake_root / "bronze" / "bars_raw" / "year=2026" / "*.parquet")
    try:
        lake = _lake_rows(lake_glob, codes, args.start, args.end)
    except Exception as exc:
        lake = {}
        errors["lake"] = "%s: %s" % (type(exc).__name__, exc)
    ratios: dict[str, dict[str, Any]] = {}
    price_mismatch = 0
    for key, bar in qmt.items():
        if key not in lake:
            continue
        common_rows[key] = lake[key]
        old = lake[key]
        for field in ("open", "high", "low", "close"):
            try:
                if abs(float(bar.raw[field]) - float(old[field])) > 1e-6:
                    price_mismatch += 1
                    issues.append({"code": key[0], "trade_date": key[1], "rule": "ohlc_mismatch_%s" % field})
            except (KeyError, TypeError, ValueError):
                issues.append({"code": key[0], "trade_date": key[1], "rule": "lake_missing_%s" % field})
        item = ratios.setdefault(key[0], {"volume_ratios": [], "amount_ratios": [], "common_rows": 0})
        item["common_rows"] += 1
        try:
            if old.get("volume") not in (None, 0, ""):
                item["volume_ratios"].append(float(bar.raw["volume"]) / float(old["volume"]))
        except (KeyError, TypeError, ValueError, ZeroDivisionError):
            pass
        try:
            if old.get("amount") not in (None, 0, ""):
                item["amount_ratios"].append(float(bar.raw["amount"]) / float(old["amount"]))
        except (KeyError, TypeError, ValueError, ZeroDivisionError):
            pass
    missing = sorted(set(qmt) - set(lake))
    ratio_summary = {}
    for code, item in ratios.items():
        ratio_summary[code] = {
            "common_rows": item["common_rows"],
            "volume_ratio_median": statistics.median(item["volume_ratios"]) if item["volume_ratios"] else None,
            "amount_ratio_median": statistics.median(item["amount_ratios"]) if item["amount_ratios"] else None,
            "volume_ratio_max_deviation": max((abs(value - 1) for value in item["volume_ratios"]), default=None),
            "amount_ratio_max_deviation_from_1000": max((abs(value - 1000) for value in item["amount_ratios"]), default=None),
        }
    report = {
        "schema_version": 1, "kind": "bigqmt_missing_daily_candidate_validation",
        "created_at": datetime.now(SHANGHAI).isoformat(), "mode": "READ_ONLY_NO_IMPORT",
        "account_id": str(config["account_id"]),
        "source": "BigQMT get_market_data_ex dividend_type=none subscribe=false",
        "lake_root": str(args.lake_root), "lake_reader": "duckdb union_by_name=true",
        "business_key": ["code", "trade_date", "period=1d", "adjustment_mode=none"],
        "range": {"start": args.start, "end": args.end}, "codes": codes,
        "summary": {"qmt_rows": len(qmt), "lake_rows": len(lake), "common_rows": len(common_rows),
                    "missing_candidate_rows": len(missing), "price_mismatch_count": price_mismatch,
                    "quality_issue_count": len(issues), "rpc_or_lake_errors": len(errors)},
        "unit_evidence": ratio_summary,
        "missing_candidate_keys": [{"code": code, "trade_date": day, "period": "1d", "adjustment_mode": "none"}
                                   for code, day in missing],
        "quality_issues": issues, "errors": errors,
        "cleaning": {"raw_candidate_rows_numeric": len(qmt) - len(issues), "forward_fill": False,
                      "ohlc_clip": False, "amount_conversion": "BigQMT already yuan; no conversion",
                      "volume_conversion": "BigQMT measured lots; no conversion"},
        "adjustment_gate": {"raw_input": "none_only", "pit_status": "NOT_DERIVED",
                             "factor_source": "shared_lake_canonical_chain_required",
                             "status": "PENDING_PIT_FACTOR_VALIDATION"},
        "release_status": "CANDIDATE_ONLY" if not errors and not issues else "BLOCKED",
        "overlay_created": False, "global_latest_updated": False,
        "next_gate": "derive/verify canonical PIT factor chain before any overlay publication",
    }
    destination = ROOT / "runtime_data" / "evidence" / "simulation" / "bigqmt_missing_key_scans"
    destination.mkdir(parents=True, exist_ok=True)
    path = destination / ("validated_missing_daily_%s.json" % datetime.now(SHANGHAI).strftime("%Y%m%d_%H%M%S"))
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": report["release_status"], "evidence": str(path), "summary": report["summary"],
                      "overlay_created": False, "global_latest_updated": False}, ensure_ascii=False, indent=2))
    return 0 if report["release_status"] == "CANDIDATE_ONLY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
