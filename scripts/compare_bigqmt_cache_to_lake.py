"""Read-only comparison of BigQMT cached daily bars against lake bronze bars."""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import duckdb

ROOT = Path(__file__).resolve().parents[1]
LAKE_ROOT = Path(r"C:/BigQMT/research/quant_data_lake")
sys.path.insert(0, str(ROOT / "src"))
from kitling_bigqmt.readonly_rpc import ReadOnlyBigQmtClient  # noqa: E402
from kitling_bigqmt.redis_resp import RedisRespClient  # noqa: E402
from kitling_bigqmt.machine_config import load_gateway  # noqa: E402


def _codes() -> list[str]:
    pool = json.loads((ROOT / "config" / "v1_1_17_etf_pool.json").read_text(encoding="utf-8"))
    return list(dict.fromkeys([
        "600519.SH", "000001.SZ", "300750.SZ", "688981.SH", "600000.SH", "000333.SZ",
        *[str(item) for item in pool.get("qmt_codes", []) if item],
    ]))


def _day(value: Any) -> str:
    number = float(value)
    if number > 10_000_000_000:
        number /= 1000.0
    return datetime.fromtimestamp(number, tz=timezone(timedelta(hours=8))).strftime("%Y%m%d")


def _qmt_rows(response: dict[str, Any], code: str) -> list[dict[str, Any]]:
    frame = (response.get("data") or {}).get(code, {})
    records = frame.get("records", frame) if isinstance(frame, dict) else []
    if isinstance(records, dict):
        lengths = [len(value) for value in records.values() if isinstance(value, list)]
        if not lengths or len(set(lengths)) != 1:
            return []
        return [{column: records[column][index] for column in records} for index in range(lengths[0])]
    if isinstance(records, list):
        return [dict(item) for item in records if isinstance(item, dict)]
    return []


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def run(start: str, end: str) -> dict[str, Any]:
    cfg = load_gateway(ROOT, "simulation")
    redis_cfg = cfg["redis"]
    client = ReadOnlyBigQmtClient(
        RedisRespClient(redis_cfg["host"], redis_cfg["port"], redis_cfg["db"], timeout=5),
        cfg["account_id"], timeout_seconds=float(cfg.get("rpc_timeout_seconds", 12)),
    )
    codes = _codes()
    qmt: dict[tuple[str, str], dict[str, float]] = {}
    errors: dict[str, str] = {}
    for code in codes:
        try:
            response = client.market_data_ex(
                [code], ["time", "open", "high", "low", "close", "volume", "amount"],
                "1d", start, end, -1, "none", False,
            )
            for row in _qmt_rows(response, code):
                day = _day(row.get("time"))
                values = {field: _float(row.get(field)) for field in ("open", "high", "low", "close", "volume", "amount")}
                if day and all(value is not None for value in values.values()):
                    qmt[(code, day)] = values  # type: ignore[assignment]
        except Exception as exc:
            errors[code] = f"{type(exc).__name__}: {exc}"

    lake_path = str(LAKE_ROOT / "bronze" / "bars_raw" / "year=*" / "*.parquet")
    con = duckdb.connect()
    try:
        lake_rows = con.execute(
            """
            select code, strftime(cast(trade_date as date), '%Y%m%d') as trade_day,
                   open, high, low, close, volume, amount, adj_factor
            from read_parquet(?, union_by_name=true, hive_partitioning=true)
            where code in (select unnest(?::varchar[]))
              and cast(trade_date as date) between ?::date and ?::date
            """,
            [lake_path, codes, f"{start[:4]}-{start[4:6]}-{start[6:]}", f"{end[:4]}-{end[4:6]}-{end[6:]}"]
        ).fetchall()
    finally:
        con.close()
    lake: dict[tuple[str, str], dict[str, float]] = {}
    for row in lake_rows:
        code, day = str(row[0]), str(row[1])
        values = {field: _float(row[index]) for index, field in enumerate(("open", "high", "low", "close", "volume", "amount"), 2)}
        values["adj_factor"] = _float(row[8])
        if all(values[field] is not None for field in ("open", "high", "low", "close", "volume", "amount")):
            lake[(code, day)] = values  # type: ignore[assignment]

    common = sorted(set(qmt) & set(lake))
    qmt_only = sorted(set(qmt) - set(lake))
    lake_only = sorted(set(lake) - set(qmt))
    price_mismatches = []
    normalized_price_mismatches = []
    price_mismatch_keys: set[tuple[str, str]] = set()
    normalized_price_mismatch_keys: set[tuple[str, str]] = set()
    lake_price_modes = Counter()
    close_offsets: dict[str, list[float]] = {}
    volume_ratios: list[float] = []
    amount_ratios: list[float] = []
    for key in common:
        left, right = qmt[key], lake[key]
        factor = right.get("adj_factor")
        normalized_right = dict(right)
        factor_applied = False
        if factor is not None and factor > 0 and left["close"]:
            stored_ratio = right["close"] / left["close"]
            factor_applied = abs(stored_ratio - factor) <= 1e-5
            if factor_applied:
                lake_price_modes["close_ratio_matches_adj_factor"] += 1
            elif abs(stored_ratio - 1.0) <= 1e-5:
                lake_price_modes["close_ratio_raw_like"] += 1
            else:
                lake_price_modes["close_ratio_other"] += 1
        elif factor is None:
            lake_price_modes["factor_null"] += 1
        else:
            lake_price_modes["close_ratio_other"] += 1
        if factor_applied:
            for field in ("open", "high", "low", "close"):
                normalized_right[field] = right[field] / factor
        for field in ("open", "high", "low", "close"):
            if abs(left[field] - right[field]) > 1e-6:
                price_mismatches.append({"code": key[0], "trade_date": key[1], "field": field, "qmt": left[field], "lake": right[field]})
                price_mismatch_keys.add(key)
                if field == "close":
                    close_offsets.setdefault(key[0], []).append(left["close"] - right["close"])
            if abs(left[field] - normalized_right[field]) > 1e-6:
                normalized_price_mismatches.append({"code": key[0], "trade_date": key[1], "field": field, "qmt": left[field], "lake_unadjusted": normalized_right[field], "adj_factor": factor})
                normalized_price_mismatch_keys.add(key)
        if right["volume"]:
            volume_ratios.append(left["volume"] / right["volume"])
        if right["amount"]:
            amount_ratios.append(left["amount"] / right["amount"])

    per_code = []
    for code in codes:
        qmt_keys = {key for key in qmt if key[0] == code}
        lake_keys = {key for key in lake if key[0] == code}
        common_keys = qmt_keys & lake_keys
        only_keys = qmt_keys - lake_keys
        lake_days = sorted(key[1] for key in lake_keys)
        before_lake_start = sum(1 for _, day in only_keys if lake_days and day < lake_days[0])
        after_lake_end = sum(1 for _, day in only_keys if lake_days and day > lake_days[-1])
        inside_lake_range = len(only_keys) - before_lake_start - after_lake_end
        per_code.append({
            "code": code,
            "qmt_rows": len(qmt_keys), "lake_rows": len(lake_keys), "common_rows": len(common_keys),
            "qmt_only_rows": len(only_keys), "lake_only_rows": len(lake_keys - qmt_keys),
            "qmt_only_breakdown": {"before_lake_start": before_lake_start, "after_lake_end": after_lake_end, "inside_lake_range": inside_lake_range},
            "qmt_range": [min((key[1] for key in qmt_keys), default=None), max((key[1] for key in qmt_keys), default=None)],
            "lake_range": [min((key[1] for key in lake_keys), default=None), max((key[1] for key in lake_keys), default=None)],
        })
    qmt_only_breakdown = {
        "before_lake_start": sum(item["qmt_only_breakdown"]["before_lake_start"] for item in per_code),
        "after_lake_end": sum(item["qmt_only_breakdown"]["after_lake_end"] for item in per_code),
        "inside_lake_range": sum(item["qmt_only_breakdown"]["inside_lake_range"] for item in per_code),
    }
    result = {
        "schema_version": 1,
        "kind": "bigqmt_cache_vs_lake_bronze_daily_comparison",
        "created_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "mode": "READ_ONLY_NO_IMPORT",
        "account_id": str(cfg["account_id"]),
        "qmt_source": "get_market_data_ex dividend_type=none subscribe=false",
        "lake_source": str(LAKE_ROOT / "bronze/bars_raw/year=*/*.parquet"),
        "business_key": ["code", "trade_date", "period=1d", "adjustment_mode=none"],
        "range": {"start": start, "end": end},
        "summary": {
            "codes": len(codes), "qmt_rows": len(qmt), "lake_rows": len(lake), "common_rows": len(common),
            "qmt_only_rows": len(qmt_only), "lake_only_rows": len(lake_only),
            "qmt_only_breakdown": qmt_only_breakdown,
            "price_mismatch_count": len(price_mismatches),
            "price_mismatch_key_count": len(price_mismatch_keys),
            "price_mismatch_by_code": dict(Counter(code for code, _ in price_mismatch_keys)),
            "price_mismatch_date_range_by_code": {
                code: [min(day for item_code, day in price_mismatch_keys if item_code == code), max(day for item_code, day in price_mismatch_keys if item_code == code)]
                for code in sorted({item_code for item_code, _ in price_mismatch_keys})
            },
            "normalized_price_mismatch_count": len(normalized_price_mismatches),
            "normalized_price_mismatch_key_count": len(normalized_price_mismatch_keys),
            "lake_adj_factor_nonnull_common_rows": sum(1 for key in common if lake[key].get("adj_factor") is not None),
            "lake_adj_factor_not_one_common_rows": sum(1 for key in common if lake[key].get("adj_factor") not in (None, 1.0)),
            "lake_price_mode_counts": dict(lake_price_modes),
            "close_offset_median_by_code": {
                code: statistics.median(values) for code, values in sorted(close_offsets.items()) if values
            },
            "rpc_errors": len(errors),
            "volume_ratio_median_qmt_over_lake": statistics.median(volume_ratios) if volume_ratios else None,
            "amount_ratio_median_qmt_over_lake": statistics.median(amount_ratios) if amount_ratios else None,
        },
        "unit_interpretation": {
            "qmt_volume": "lots",
            "qmt_amount": "yuan",
            "lake_bronze_volume": "lots",
            "lake_bronze_amount": "historical thousand-yuan scale; multiply by 1000 for yuan comparison",
        },
        "per_code": per_code,
        "price_mismatches": price_mismatches[:200],
        "normalized_price_mismatches": normalized_price_mismatches[:200],
        "qmt_only_sample": [{"code": code, "trade_date": day} for code, day in qmt_only[:200]],
        "lake_only_sample": [{"code": code, "trade_date": day} for code, day in lake_only[:200]],
        "errors": errors,
        "lake_write": False,
        "global_latest_updated": False,
    }
    result["status"] = "PASSED" if not errors and not normalized_price_mismatches else "BLOCKED"
    result["release_gate"] = "BLOCKED_RAW_PRICE_SCHEMA_MIX" if price_mismatches and not normalized_price_mismatches else ("PASSED" if result["status"] == "PASSED" else "BLOCKED")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="20200101")
    parser.add_argument("--end", default="20260911")
    args = parser.parse_args()
    result = run(args.start, args.end)
    evidence_dir = ROOT / "runtime_data" / "evidence" / "simulation" / "bigqmt_missing_key_scans"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    path = evidence_dir / f"cache_vs_lake_daily_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    result["evidence"] = str(path)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
