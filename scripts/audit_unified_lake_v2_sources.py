"""Create a read-only source baseline before unified-lake v2 ingestion.

The audit intentionally inventories source facts without selecting a winner or
writing a Parquet release.  A missing MiniQMT path is reported as an explicit
blocker rather than silently substituted with another provider.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def files_at(path: Path) -> list[Path]:
    if path.is_file() and path.suffix == ".parquet":
        return [path]
    if path.is_dir():
        return sorted(path.rglob("*.parquet"))
    return []


def profile(name: str, path: Path, code_column: str, date_column: str,
            ohlc_columns: tuple[str, str, str, str]) -> dict[str, Any]:
    paths = files_at(path)
    if not paths:
        return {"source": name, "status": "UNAVAILABLE_OR_UNLOCATED", "path": str(path), "files": 0}
    frames = [pd.read_parquet(item) for item in paths]
    frame = pd.concat(frames, ignore_index=True)
    missing = [item for item in (code_column, date_column, *ohlc_columns) if item not in frame.columns]
    result: dict[str, Any] = {
        "source": name, "status": "SOURCE_BASELINE_READ_ONLY",
        "path": str(path), "files": len(paths), "rows": len(frame),
        "columns": list(frame.columns), "missing_required_profile_columns": missing,
    }
    if missing or frame.empty:
        result["quality"] = "BLOCKED_SCHEMA_OR_EMPTY"
        return result
    dates = pd.to_datetime(frame[date_column].astype(str), errors="coerce")
    numeric = frame.loc[:, list(ohlc_columns)].apply(pd.to_numeric, errors="coerce")
    ohlc_ok = bool((numeric > 0).all().all() and
                   (numeric[ohlc_columns[1]] >= numeric[[ohlc_columns[0], ohlc_columns[2], ohlc_columns[3]]].max(axis=1)).all() and
                   (numeric[ohlc_columns[2]] <= numeric[[ohlc_columns[0], ohlc_columns[1], ohlc_columns[3]]].min(axis=1)).all())
    result.update({
        "codes": int(frame[code_column].astype(str).nunique()),
        "min_trade_date": dates.min().strftime("%Y%m%d") if dates.notna().any() else None,
        "max_trade_date": dates.max().strftime("%Y%m%d") if dates.notna().any() else None,
        "duplicate_business_keys": int(frame[[code_column, date_column]].duplicated().sum()),
        "ohlc_valid": ohlc_ok,
        "quality": "PROFILE_VALIDATION_PASSED" if ohlc_ok and not frame[[code_column, date_column]].duplicated().any() else "CANDIDATE_OR_CONFLICT_REVIEW_REQUIRED",
    })
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only unified lake v2 source baseline")
    parser.add_argument("--bigqmt", type=Path, default=Path(r"C:\BigQMT\research\quant_data_lake\bronze\_bigqmt_raw_releases\bigqmt_candidate_20260912_145717\daily"))
    parser.add_argument("--tushare", type=Path, default=Path(r"C:\BigQMT\research\kitling_AI量化_review\reports\data_audit\af2_exception_candidate_20260911T005454Z\tushare_repair_candidate.parquet"))
    parser.add_argument("--miniqmt", type=Path, default=Path(r"C:\BigQMT\research\miniqmt_data"))
    args = parser.parse_args()
    results = [
        profile("bigqmt", args.bigqmt, "code", "trade_date", ("open", "high", "low", "close")),
        profile("tushare", args.tushare, "ts_code", "trade_date", ("new_open", "new_high", "new_low", "new_close")),
        profile("miniqmt", args.miniqmt, "code", "trade_date", ("open", "high", "low", "close")),
    ]
    report = {
        "schema_version": 1,
        "kind": "unified_lake_v2_source_baseline",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "mode": "READ_ONLY_NO_LAKE_WRITE",
        "sources": results,
        "gates": {
            "bigqmt_baseline": results[0]["status"],
            "tushare_baseline": results[1]["status"],
            "miniqmt_baseline": results[2]["status"],
            "ingestion_allowed": "BLOCKED_UNTIL_MINIQMT_LOCATION_AND_SOURCE_UNIT_MEASUREMENTS_ARE_RECORDED",
        },
        "safety": {"lake_write": False, "global_latest_updated": False, "orders_enabled": False, "broker_calls": False},
    }
    destination = ROOT / "runtime_data" / "evidence" / "simulation" / "unified_lake_v2"
    destination.mkdir(parents=True, exist_ok=True)
    output = destination / ("source_baseline_%s.json" % datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), "sources": results, "gates": report["gates"], "safety": report["safety"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
