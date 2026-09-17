"""Read-only import-readiness gate for a local BigQMT candidate package."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import duckdb

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = {"code", "bar_time", "trade_date", "period", "adjustment_mode", "open", "high", "low", "close",
            "volume_lots", "amount_yuan", "source", "source_release", "available_at", "row_hash"}


def _lake_keys(lake_root: Path, rows: list[tuple[str, str]]) -> set[tuple[str, str]]:
    if not rows:
        return set()
    codes = sorted({code for code, _ in rows})
    start = min(day for _, day in rows)
    end = max(day for _, day in rows)
    placeholders = ",".join("?" for _ in codes)
    path = str(lake_root / "bronze" / "bars_raw" / "year=*" / "*.parquet")
    query = ("select code, strftime(cast(trade_date as date),'%%Y%%m%%d') "
             "from read_parquet(?, union_by_name=true, hive_partitioning=true) "
             "where code in (%s) and cast(trade_date as date) between ?::date and ?::date "
             "and open is not null and high is not null and low is not null and close is not null "
             "and volume is not null and amount is not null") % placeholders
    with duckdb.connect() as db:
        data = db.execute(query, [path, *codes, f"{start[:4]}-{start[4:6]}-{start[6:]}",
                                  f"{end[:4]}-{end[4:6]}-{end[6:]}"]).fetchall()
    return {(str(code), str(day)) for code, day in data}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("release_dir", type=Path)
    parser.add_argument("--lake-root", type=Path, default=Path(r"C:\BigQMT\research\quant_data_lake"))
    args = parser.parse_args()
    manifest_path = args.release_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    errors: list[str] = []
    checks: dict[str, Any] = {}
    all_rows: list[dict[str, Any]] = []
    for filename in ("daily_raw_overlay.parquet", "intraday_raw_overlay.parquet"):
        path = args.release_dir / filename
        with duckdb.connect() as db:
            columns = {str(row[0]) for row in db.execute("describe select * from read_parquet(?)", [str(path)]).fetchall()}
            count = int(db.execute("select count(*) from read_parquet(?)", [str(path)]).fetchone()[0])
            rows = db.execute("select * from read_parquet(?)", [str(path)]).fetchdf().to_dict("records")
        missing = sorted(REQUIRED - columns)
        if missing:
            errors.append("%s missing columns: %s" % (filename, ",".join(missing)))
        if count != int(manifest["files"]["daily_raw_overlay" if filename.startswith("daily") else "intraday_raw_overlay"]["rows"]):
            errors.append("%s row count differs from manifest" % filename)
        all_rows.extend(rows)
        checks[filename] = {"columns": sorted(columns), "rows": count}

    keys = [(str(row["code"]), str(row["trade_date"]).replace("-", "")[:8]) for row in all_rows]
    daily_rows = [row for row in all_rows if str(row.get("period")) == "1d"]
    daily_key_pairs = [(str(row["code"]), str(row["trade_date"]).replace("-", "")[:8]) for row in daily_rows]
    checks["unique_business_rows"] = len({(str(row["code"]), str(row["bar_time"]), str(row["period"]), str(row["adjustment_mode"])) for row in all_rows}) == len(all_rows)
    checks["unique_row_hashes"] = len({str(row["row_hash"]) for row in all_rows}) == len(all_rows)
    checks["daily_candidate_only"] = True
    lake_keys = _lake_keys(args.lake_root, daily_key_pairs)
    conflicts = sorted(set(daily_key_pairs) & lake_keys)
    checks["daily_lake_conflicts"] = len(conflicts)
    if conflicts:
        errors.append("daily candidate conflicts with %d lake keys" % len(conflicts))
    for row in all_rows:
        try:
            values = [float(row[field]) for field in ("open", "high", "low", "close")]
            if min(values) <= 0 or values[1] < max(values[0], values[2], values[3]) or values[2] > min(values[0], values[1], values[3]):
                errors.append("invalid OHLC: %s" % row.get("code"))
            if float(row["volume_lots"]) < 0 or float(row["amount_yuan"]) < 0:
                errors.append("negative volume/amount: %s" % row.get("code"))
        except (TypeError, ValueError, KeyError):
            errors.append("non-numeric row: %s" % row.get("code"))
    result = {
        "schema_version": 1, "kind": "bigqmt_candidate_import_readiness_gate",
        "release_id": manifest.get("release_id"), "mode": "READ_ONLY_NO_IMPORT",
        "checks": checks, "error_count": len(errors), "errors": errors,
        "raw_bronze_import_ready": not errors,
        "silver_pit_import_ready": False,
        "silver_pit_block_reason": "canonical PIT factor chain and available_at validation still pending",
        "lake_write": False, "global_latest_updated": False,
    }
    output = args.release_dir / "import_readiness.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["raw_bronze_import_ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
