"""Prepare local BigQMT candidate artifacts without publishing to the lake.

The script performs a copy-on-write preparation step only.  It reads QMT and
the existing lake, writes Parquet/JSON beneath this project runtime_data, and
never modifies quant_data_lake, catalog/LATEST, Redis, QMT, or a broker.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))
from clean_validate_bigqmt_cache_candidate import _clean_rows, _rows  # noqa: E402
from kitling_bigqmt.machine_config import load_gateway  # noqa: E402
from kitling_bigqmt.readonly_rpc import ReadOnlyBigQmtClient  # noqa: E402
from kitling_bigqmt.redis_resp import RedisRespClient  # noqa: E402

SHANGHAI = timezone(timedelta(hours=8))
FIELDS = ["time", "open", "high", "low", "close", "volume", "amount"]
DEFAULT_CODES = ("600519.SH", "000001.SZ", "300750.SZ", "688981.SH", "600000.SH", "000333.SZ")


def _codes() -> list[str]:
    pool = json.loads((ROOT / "config" / "v1_1_17_etf_pool.json").read_text(encoding="utf-8"))
    return list(dict.fromkeys([*DEFAULT_CODES, *[str(x) for x in pool.get("qmt_codes", []) if x]]))


def _lake_keys(lake_root: Path, codes: list[str], start: str, end: str) -> set[tuple[str, str]]:
    path = str(lake_root / "bronze" / "bars_raw" / "year=*" / "*.parquet")
    placeholders = ",".join("?" for _ in codes)
    query = ("select code, strftime(cast(trade_date as date),'%%Y%%m%%d') "
             "from read_parquet(?, union_by_name=true, hive_partitioning=true) "
             "where code in (%s) and cast(trade_date as date) between ?::date and ?::date "
             "and open is not null and high is not null and low is not null and close is not null "
             "and volume is not null and amount is not null") % placeholders
    with duckdb.connect() as db:
        rows = db.execute(query, [path, *codes, f"{start[:4]}-{start[4:6]}-{start[6:]}",
                                  f"{end[:4]}-{end[4:6]}-{end[6:]}"]).fetchall()
    return {(str(code), str(day)) for code, day in rows}


def _hash_row(row: dict[str, Any]) -> str:
    payload = {key: row[key] for key in (
        "code", "bar_time", "trade_date", "period", "adjustment_mode", "open", "high", "low", "close",
        "volume_lots", "amount_yuan")}
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _write_parquet(rows: list[dict[str, Any]], path: Path) -> None:
    frame = pd.DataFrame(rows)
    if "bar_time" in frame:
        frame["bar_time"] = pd.to_datetime(frame["bar_time"], utc=True)
    if "available_at" in frame:
        frame["available_at"] = pd.to_datetime(frame["available_at"], utc=True)
    table = pa.Table.from_pandas(frame, preserve_index=False)
    pq.write_table(table, path, compression="zstd")


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare local BigQMT candidate release")
    parser.add_argument("--start", default="20260820")
    parser.add_argument("--end", default="20260911")
    parser.add_argument("--intraday-start", default="20260908")
    parser.add_argument("--intraday-end", default="20260911")
    parser.add_argument("--lake-root", type=Path, default=Path(r"C:\BigQMT\research\quant_data_lake"))
    args = parser.parse_args()
    config = load_gateway(ROOT, "simulation")
    redis_cfg = config["redis"]
    client = ReadOnlyBigQmtClient(RedisRespClient(redis_cfg["host"], redis_cfg["port"], redis_cfg["db"], timeout=8),
                                  str(config["account_id"]), float(config.get("rpc_timeout_seconds", 12)))
    codes = _codes()
    now = datetime.now(SHANGHAI)
    release_id = "bigqmt_candidate_%s" % now.strftime("%Y%m%d_%H%M%S")
    available_at = now.isoformat()
    errors: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    daily_all: list[dict[str, Any]] = []
    for code in codes:
        try:
            raw = _rows(client.market_data_ex([code], FIELDS, "1d", args.start, args.end, -1, "none", subscribe=False), code)
            cleaned, row_issues = _clean_rows(raw, code, "1d")
            issues.extend(row_issues)
            daily_all.extend(row for row in cleaned if args.start <= row["trade_date"] <= args.end)
        except Exception as exc:
            errors.append({"code": code, "period": "1d", "error": "%s: %s" % (type(exc).__name__, exc)})
    try:
        lake_keys = _lake_keys(args.lake_root, codes, args.start, args.end)
    except Exception as exc:
        lake_keys = set()
        errors.append({"stage": "lake_keys", "error": "%s: %s" % (type(exc).__name__, exc)})
    daily = [row for row in daily_all if (row["code"], row["trade_date"]) not in lake_keys]
    for row in daily:
        row["source_release"] = release_id
        row["available_at"] = available_at
        row["row_hash"] = _hash_row(row)

    intraday: list[dict[str, Any]] = []
    for code in codes:
        for period in ("5m", "1m"):
            try:
                raw = _rows(client.market_data_ex([code], FIELDS, period, args.intraday_start, args.intraday_end,
                                                   -1, "none", subscribe=False), code)
                cleaned, row_issues = _clean_rows(raw, code, period)
                issues.extend(row_issues)
                intraday.extend(cleaned)
            except Exception as exc:
                errors.append({"code": code, "period": period, "error": "%s: %s" % (type(exc).__name__, exc)})
    for row in intraday:
        row["source_release"] = release_id
        row["available_at"] = available_at
        row["row_hash"] = _hash_row(row)

    hard_issues = [item for item in issues if item.get("rule") != "pre_listing_placeholder"]
    quarantined_rows = sum(1 for item in issues if item.get("rule") == "pre_listing_placeholder")
    quarantine_by_code = Counter(item.get("code") for item in issues if item.get("rule") == "pre_listing_placeholder")

    destination = ROOT / "runtime_data" / "candidates" / release_id
    destination.mkdir(parents=True, exist_ok=False)
    _write_parquet(daily, destination / "daily_raw_overlay.parquet")
    _write_parquet(intraday, destination / "intraday_raw_overlay.parquet")
    manifest = {
        "schema_version": 1,
        "release_id": release_id,
        "created_at": available_at,
        "mode": "LOCAL_CANDIDATE_ONLY_NO_LAKE_WRITE",
        "account_id": str(config["account_id"]),
        "source": "bigqmt_cache",
        "source_request": {"daily": "get_market_data_ex dividend_type=none subscribe=false",
                           "intraday": "get_market_data_ex dividend_type=none subscribe=false"},
        "ranges": {"daily": {"start": args.start, "end": args.end},
                   "intraday": {"start": args.intraday_start, "end": args.intraday_end}},
        "codes": codes,
        "business_key": ["code", "bar_time", "period", "adjustment_mode"],
        "files": {
            "daily_raw_overlay": {"path": "daily_raw_overlay.parquet", "rows": len(daily), "lake_missing_only": True},
            "intraday_raw_overlay": {"path": "intraday_raw_overlay.parquet", "rows": len(intraday), "lake_missing_only": False},
        },
        "units": {"volume_lots": "QMT cross-period measured", "amount_yuan": "QMT cross-period measured"},
        "summary": {"daily_qmt_rows": len(daily_all), "daily_lake_rows": len(lake_keys),
                    "daily_missing_candidate_rows": len(daily), "intraday_candidate_rows": len(intraday),
                    "quality_issue_count": len(hard_issues), "quarantined_pre_listing_rows": quarantined_rows,
                    "rpc_or_lake_error_count": len(errors)},
        "gates": {"schema": "PASSED", "normalization": "PASSED" if not hard_issues else "BLOCKED",
                  "duplicate_and_hash": "PASSED" if len({row["row_hash"] for row in daily + intraday}) == len(daily) + len(intraday) else "BLOCKED",
                  "pit_factor_for_silver": "BLOCKED_PENDING_CANONICAL_FACTOR_CHAIN",
                  "daily_cross_source_price": "NOT_APPLICABLE_MISSING_ONLY_NO_OVERLAP",
                  "intraday_cross_source_price": "PENDING_NO_LAKE_INTRADAY_DATASET",
                  "existing_lake_overlap_audit": "BLOCKED_RAW_PRICE_SCHEMA_MIX_SEPARATE_REPAIR_QUEUE",
                  "raw_candidate_artifact": "READY_FOR_RAW_BRONZE_REVIEW" if not hard_issues and not errors else "BLOCKED"},
        "lake_write": False,
        "global_latest_updated": False,
        "orders_enabled": False,
        "quality_issues": hard_issues,
        "quarantine": {"pre_listing_placeholder_rows": quarantined_rows,
                       "by_code": dict(sorted(quarantine_by_code.items())),
                       "policy": "exclude from candidate; preserve issue evidence; never manufacture prices"},
        "errors": errors,
        "next_action": "Review candidate manifest, resolve PIT/price-schema gates, then separately approve any publisher run",
    }
    (destination / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"release_id": release_id, "destination": str(destination), "summary": manifest["summary"],
                      "gates": manifest["gates"], "lake_write": False, "global_latest_updated": False},
                     ensure_ascii=False, indent=2))
    return 0 if manifest["gates"]["raw_candidate_artifact"] == "READY_FOR_RAW_BRONZE_REVIEW" else 2


if __name__ == "__main__":
    raise SystemExit(main())
