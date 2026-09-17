"""Classify existing lake price conflicts against QMT adjustment modes.

Read-only diagnostic.  It never overwrites the lake.  Rows that exactly match
QMT front/back prices are eligible for a future metadata reclassification;
unmatched rows remain quarantined and require independent reconciliation.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import duckdb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from kitling_bigqmt.readonly_rpc import ReadOnlyBigQmtClient  # noqa: E402
from kitling_bigqmt.redis_resp import RedisRespClient  # noqa: E402
from kitling_bigqmt.machine_config import load_gateway  # noqa: E402
from verify_qmt_history_cache import _rows  # noqa: E402

SHANGHAI = timezone(timedelta(hours=8))
MODES = ("none", "front", "back")
FIELDS = ["time", "open", "high", "low", "close", "volume", "amount"]
DEFAULT_CODES = ("000001.SZ", "000333.SZ", "300750.SZ", "600000.SH", "600519.SH",
                 "159941.SZ", "160723.SZ", "161127.SZ", "162411.SZ", "162415.SZ", "162719.SZ")


def _lake_rows(root: Path, codes: list[str], start: str, end: str) -> dict[tuple[str, str], dict[str, Any]]:
    path = str(root / "bronze" / "bars_raw" / "year=*" / "*.parquet")
    placeholders = ",".join("?" for _ in codes)
    query = ("select code,strftime(cast(trade_date as date),'%%Y%%m%%d'),open,high,low,close,volume,amount,adj_factor,source "
             "from read_parquet(?,union_by_name=true,hive_partitioning=true) where code in (%s) "
             "and cast(trade_date as date) between ?::date and ?::date") % placeholders
    with duckdb.connect() as db:
        rows = db.execute(query, [path, *codes, f"{start[:4]}-{start[4:6]}-{start[6:]}",
                                  f"{end[:4]}-{end[4:6]}-{end[6:]}"]).fetchall()
    return {(str(row[0]), str(row[1])): {"open": float(row[2]), "high": float(row[3]), "low": float(row[4]),
             "close": float(row[5]), "volume": float(row[6]), "amount": float(row[7]),
             "adj_factor": row[8], "source": row[9]} for row in rows}


def _qmt_by_mode(client: ReadOnlyBigQmtClient, code: str, start: str, end: str) -> dict[str, dict[str, dict[str, float]]]:
    result: dict[str, dict[str, dict[str, float]]] = {}
    for mode in MODES:
        rows = _rows(client.market_data_ex([code], FIELDS, "1d", start, end, -1, mode, False), code)
        result[mode] = {}
        for row in rows:
            try:
                day = str(row.get("stime") or "")[:8]
                if len(day) != 8:
                    day = datetime.fromtimestamp(float(row["time"]) / 1000, tz=SHANGHAI).strftime("%Y%m%d")
                result[mode][day] = {field: float(row[field]) for field in ("open", "high", "low", "close")}
            except (KeyError, TypeError, ValueError):
                continue
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="20200101")
    parser.add_argument("--end", default="20260911")
    parser.add_argument("--lake-root", type=Path, default=Path(r"C:\BigQMT\research\quant_data_lake"))
    args = parser.parse_args()
    cfg = load_gateway(ROOT, "simulation")
    rc = cfg["redis"]
    client = ReadOnlyBigQmtClient(RedisRespClient(rc["host"], rc["port"], rc["db"], timeout=8), str(cfg["account_id"]), 12)
    codes = list(DEFAULT_CODES)
    lake = _lake_rows(args.lake_root, codes, args.start, args.end)
    qmt: dict[str, dict[str, dict[str, dict[str, float]]]] = {}
    errors: list[dict[str, Any]] = []
    for code in codes:
        try:
            qmt[code] = _qmt_by_mode(client, code, args.start, args.end)
        except Exception as exc:
            errors.append({"code": code, "error": "%s: %s" % (type(exc).__name__, exc)})
    counts = Counter()
    rows: list[dict[str, Any]] = []
    front_reclassification: list[dict[str, Any]] = []
    unmatched_quarantine: list[dict[str, Any]] = []
    for (code, day), lake_row in sorted(lake.items()):
        modes = []
        for mode in MODES:
            candidate = qmt.get(code, {}).get(mode, {}).get(day)
            if candidate and all(abs(candidate[field] - lake_row[field]) <= 1e-6 for field in ("open", "high", "low", "close")):
                modes.append(mode)
        classification = "MATCH_QMT_NONE" if modes == ["none"] else (
            "MATCH_QMT_FRONT" if modes == ["front"] else (
            "MATCH_QMT_BACK" if modes == ["back"] else (
            "MATCH_MULTIPLE_MODES" if modes else "UNMATCHED_PRICE")))
        counts[classification] += 1
        rows.append({"code": code, "trade_date": day, "lake_source": lake_row["source"],
                     "lake_adj_factor": lake_row["adj_factor"], "matching_modes": modes,
                     "classification": classification})
        if classification == "MATCH_QMT_FRONT":
            front_reclassification.append({"code": code, "trade_date": day, "period": "1d",
                                            "adjustment_mode": "front", "open": lake_row["open"],
                                            "high": lake_row["high"], "low": lake_row["low"],
                                            "close": lake_row["close"], "volume_lots": lake_row["volume"],
                                            "amount_yuan": lake_row["amount"], "source": lake_row["source"],
                                            "repair_status": "CANDIDATE_RECLASSIFICATION_ONLY"})
        elif classification == "UNMATCHED_PRICE":
            unmatched_quarantine.append({"code": code, "trade_date": day, "period": "1d",
                                         "lake_source": lake_row["source"], "lake_adj_factor": lake_row["adj_factor"],
                                         "lake_ohlc": {field: lake_row[field] for field in ("open", "high", "low", "close")},
                                         "qmt_raw_ohlc": qmt.get(code, {}).get("none", {}).get(day),
                                         "repair_status": "QUARANTINE_NEEDS_INDEPENDENT_RECONCILIATION"})
    result = {
        "schema_version": 1, "kind": "lake_price_schema_conflict_classification",
        "created_at": datetime.now(SHANGHAI).isoformat(), "mode": "READ_ONLY_NO_REPAIR_NO_IMPORT",
        "account_id": str(cfg["account_id"]), "range": {"start": args.start, "end": args.end}, "codes": codes,
        "summary": {"lake_rows_checked": len(rows), "classification_counts": dict(counts), "errors": len(errors)},
        "rows": rows, "errors": errors,
        "front_reclassification_candidates": front_reclassification,
        "unmatched_quarantine_candidates": unmatched_quarantine,
        "next_action": "Reclassify exact front/back matches into separated adjusted layer; quarantine unmatched rows; no overwrite",
        "lake_write": False, "global_latest_updated": False,
    }
    destination = ROOT / "runtime_data" / "evidence" / "simulation" / "bigqmt_missing_key_scans"
    destination.mkdir(parents=True, exist_ok=True)
    path = destination / ("lake_price_schema_conflicts_%s.json" % datetime.now(SHANGHAI).strftime("%Y%m%d_%H%M%S"))
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    result["evidence"] = str(path)
    print(json.dumps({"summary": result["summary"], "evidence": str(path), "lake_write": False,
                      "global_latest_updated": False}, ensure_ascii=False, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
