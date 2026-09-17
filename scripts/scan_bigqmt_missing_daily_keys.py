"""Read-only BigQMT-versus-shared-lake daily business-key scanner.

This script deliberately produces an evidence report only.  It never creates
an overlay, writes Parquet/DuckDB/QuestDB, calls QMT downloads, or changes a
LATEST pointer.
"""

from __future__ import annotations

import argparse
import json
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


def _ohlcv_violations(bar: DailyBar) -> list[str]:
    raw = bar.raw
    try:
        values = {key: float(raw.get(key)) for key in ("open", "high", "low", "close")}
    except (TypeError, ValueError):
        return ["non_numeric_ohlc"]
    issues: list[str] = []
    if min(values.values()) <= 0:
        issues.append("non_positive_ohlc")
    if values["high"] < max(values["open"], values["low"], values["close"]):
        issues.append("high_relationship")
    if values["low"] > min(values["open"], values["high"], values["close"]):
        issues.append("low_relationship")
    for key in ("volume", "amount"):
        try:
            if float(raw.get(key)) < 0:
                issues.append("negative_%s" % key)
        except (TypeError, ValueError):
            issues.append("non_numeric_%s" % key)
    return issues


def _lake_keys(glob_path: str, codes: list[str], start: str, end: str) -> list[dict[str, Any]]:
    placeholders = ", ".join("?" for _ in codes)
    query = """
        SELECT code, strftime(trade_date, '%%Y%%m%%d') AS trade_date,
               COUNT(*) AS row_count, list(DISTINCT source) AS sources
        FROM read_parquet(?, union_by_name=true, hive_partitioning=true)
        WHERE code IN (%s)
          AND trade_date BETWEEN CAST(? AS DATE) AND CAST(? AS DATE)
        GROUP BY code, trade_date
        ORDER BY code, trade_date
    """ % placeholders
    with duckdb.connect() as db:
        rows = db.execute(query, [glob_path, *codes, "%s-%s-%s" % (start[:4], start[4:6], start[6:]),
                                  "%s-%s-%s" % (end[:4], end[4:6], end[6:])]).fetchall()
    return [{"code": str(code), "trade_date": str(day), "row_count": int(count), "sources": list(sources or [])}
            for code, day, count, sources in rows]


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only BigQMT missing daily-key scanner")
    parser.add_argument("--start", default="20260820")
    parser.add_argument("--end", default="20260911")
    parser.add_argument("--codes", default="", help="comma-separated extra or replacement codes")
    parser.add_argument("--include-v1-1-17-pool", action="store_true", default=True)
    parser.add_argument("--lake-root", type=Path, default=Path(r"C:\BigQMT\research\quant_data_lake"))
    args = parser.parse_args()
    extra = [code.strip().upper() for code in args.codes.split(",") if code.strip()]
    codes = list(dict.fromkeys([*DEFAULT_A_SHARE_CODES, *(load_pool(ROOT) if args.include_v1_1_17_pool else ()), *extra]))
    config = load_gateway(ROOT, "simulation")
    client = ReadOnlyBigQmtClient(RedisRespClient(**dict(config["redis"])), str(config["account_id"]),
                                  float(config.get("rpc_timeout_seconds", 12)))
    qmt_rows: dict[tuple[str, str], DailyBar] = {}
    qmt_errors: dict[str, str] = {}
    quality_violations: list[dict[str, str]] = []
    for code in codes:
        try:
            bars = normalize_daily_bars(client.market_data_ex(
                [code], ["time", "open", "high", "low", "close", "volume", "amount"],
                "1d", args.start, args.end, -1, "none", subscribe=False,
            ), code)
            for bar in bars:
                if not (args.start <= bar.trade_date <= args.end):
                    continue
                key = (code, bar.trade_date)
                if key in qmt_rows:
                    quality_violations.append({"code": code, "trade_date": bar.trade_date, "rule": "duplicate_qmt_key"})
                    continue
                qmt_rows[key] = bar
                for rule in _ohlcv_violations(bar):
                    quality_violations.append({"code": code, "trade_date": bar.trade_date, "rule": rule})
        except Exception as exc:  # report, never silently replace a source
            qmt_errors[code] = "%s: %s" % (type(exc).__name__, exc)
    lake_glob = str(args.lake_root / "bronze" / "bars_raw" / "year=2026" / "*.parquet")
    lake_rows = _lake_keys(lake_glob, codes, args.start, args.end)
    lake_index = {(row["code"], row["trade_date"]): row for row in lake_rows}
    qmt_keys = set(qmt_rows)
    lake_keys = set(lake_index)
    missing = sorted(qmt_keys - lake_keys)
    common = sorted(qmt_keys & lake_keys)
    duplicate_lake = [row for row in lake_rows if row["row_count"] != 1]
    per_code = []
    for code in codes:
        code_qmt = sum(key[0] == code for key in qmt_keys)
        code_common = sum(key[0] == code for key in common)
        code_missing = sum(key[0] == code for key in missing)
        per_code.append({"code": code, "qmt_rows": code_qmt, "lake_rows": sum(row["code"] == code for row in lake_rows),
                         "common_keys": code_common, "missing_keys": code_missing,
                         "qmt_error": qmt_errors.get(code)})
    report = {
        "schema_version": 1,
        "kind": "bigqmt_missing_daily_business_key_scan",
        "created_at": datetime.now(SHANGHAI).isoformat(),
        "mode": "READ_ONLY_NO_IMPORT",
        "orders_enabled": False, "broker_call_made": False, "download_called": False,
        "account_id": str(config["account_id"]), "source": "bigqmt get_market_data_ex dividend_type=none subscribe=false",
        "lake_root": str(args.lake_root), "lake_glob": lake_glob, "lake_reader": "duckdb union_by_name=true",
        "business_key": ["code", "trade_date", "period=1d", "adjustment_mode=none"],
        "range": {"start": args.start, "end": args.end}, "codes": codes,
        "summary": {"qmt_keys": len(qmt_keys), "lake_keys": len(lake_keys), "common_keys": len(common),
                    "missing_candidate_keys": len(missing), "lake_duplicate_keys": len(duplicate_lake),
                    "qmt_quality_violations": len(quality_violations), "qmt_errors": len(qmt_errors)},
        "per_code": per_code,
        "missing_candidate_keys": [{"code": code, "trade_date": day, "period": "1d", "adjustment_mode": "none"}
                                   for code, day in missing],
        "lake_duplicate_keys": duplicate_lake,
        "qmt_quality_violations": quality_violations,
        "qmt_errors": qmt_errors,
        "release_status": "NOT_CREATED",
        "global_latest_updated": False,
        "next_gate": "unit-and-adjustment validation before any candidate overlay is created",
    }
    destination = ROOT / "runtime_data" / "evidence" / "simulation" / "bigqmt_missing_key_scans"
    destination.mkdir(parents=True, exist_ok=True)
    path = destination / ("missing_daily_keys_%s.json" % datetime.now(SHANGHAI).strftime("%Y%m%d_%H%M%S"))
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "CANDIDATE_ONLY", "evidence": str(path), "summary": report["summary"],
                      "release_status": "NOT_CREATED", "global_latest_updated": False}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
