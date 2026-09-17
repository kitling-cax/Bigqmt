"""Create a read-only BigQMT raw-bronze import plan.

This command deliberately stops before publishing.  It validates the latest
candidate package, records the canonical-to-lake field mapping, and makes the
schema boundary explicit: the existing ``bronze/bars_raw`` table is a legacy
daily table and must not receive rows that would silently lose ``period``,
``adjustment_mode``, units, or source-release provenance.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = {
    "code", "bar_time", "trade_date", "period", "adjustment_mode", "open", "high", "low", "close",
    "volume_lots", "amount_yuan", "source", "source_release", "available_at", "row_hash",
}


def _latest_release() -> Path:
    candidates = ROOT / "runtime_data" / "candidates"
    dirs = sorted((p for p in candidates.glob("bigqmt_candidate_*") if p.is_dir()), key=lambda p: p.name)
    if not dirs:
        raise FileNotFoundError("no local BigQMT candidate release found")
    return dirs[-1]


def _describe_parquet(path: Path) -> tuple[set[str], int, list[dict[str, Any]]]:
    with duckdb.connect() as db:
        columns = {str(row[0]) for row in db.execute("describe select * from read_parquet(?)", [str(path)]).fetchall()}
        count = int(db.execute("select count(*) from read_parquet(?)", [str(path)]).fetchone()[0])
        rows = db.execute(
            "select period, min(trade_date), max(trade_date), count(*) "
            "from read_parquet(?) group by period order by period", [str(path)]
        ).fetchall()
    ranges = [
        {"period": str(period), "min_trade_date": str(min_day), "max_trade_date": str(max_day), "rows": int(count)}
        for period, min_day, max_day, count in rows
    ]
    return columns, count, ranges


def _describe_legacy_bronze(lake_root: Path) -> dict[str, Any]:
    base = lake_root / "bronze" / "bars_raw"
    path = base / "year=*" / "*.parquet"
    if not base.exists():
        return {"available": False, "columns": [], "reason": "legacy bars_raw path is absent"}
    try:
        with duckdb.connect() as db:
            columns = [str(row[0]) for row in db.execute(
                "describe select * from read_parquet(?, union_by_name=true, hive_partitioning=true)", [str(path)]
            ).fetchall()]
        return {"available": True, "columns": sorted(set(columns))}
    except Exception as exc:  # pragma: no cover - defensive evidence path
        return {"available": False, "columns": [], "reason": f"{type(exc).__name__}: {exc}"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan, but do not execute, a BigQMT raw-bronze import")
    parser.add_argument("release_dir", nargs="?", type=Path, help="candidate release; defaults to newest local release")
    parser.add_argument("--lake-root", type=Path, default=Path(r"C:\BigQMT\research\quant_data_lake"))
    args = parser.parse_args()

    release = (args.release_dir or _latest_release()).resolve()
    manifest = json.loads((release / "manifest.json").read_text(encoding="utf-8"))
    readiness_path = release / "import_readiness.json"
    readiness = json.loads(readiness_path.read_text(encoding="utf-8")) if readiness_path.exists() else {}
    files: dict[str, Any] = {}
    errors: list[str] = []
    for name in ("daily_raw_overlay.parquet", "intraday_raw_overlay.parquet"):
        path = release / name
        if not path.exists():
            errors.append(f"missing candidate file: {name}")
            continue
        columns, count, ranges = _describe_parquet(path)
        missing = sorted(REQUIRED - columns)
        if missing:
            errors.append(f"{name} missing columns: {','.join(missing)}")
        files[name] = {"rows": count, "columns": sorted(columns), "ranges": ranges}

    legacy = _describe_legacy_bronze(args.lake_root)
    legacy_columns = set(legacy.get("columns", []))
    # This is intentionally an isolated target schema.  Direct append to the
    # legacy table would drop fields and mix historical price conventions.
    canonical_mapping = {
        "code": "code",
        "bar_time": "bar_time",
        "trade_date": "trade_date",
        "period": "period",
        "adjustment_mode": "adjustment_mode",
        "open": "open",
        "high": "high",
        "low": "low",
        "close": "close",
        "volume_lots": "volume_lots",
        "amount_yuan": "amount_yuan",
        "source": "source",
        "source_release": "source_release",
        "available_at": "available_at",
        "row_hash": "row_hash",
    }
    result = {
        "schema_version": 1,
        "kind": "bigqmt_raw_bronze_import_plan",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "mode": "READ_ONLY_NO_IMPORT",
        "release_id": manifest.get("release_id"),
        "release_dir": str(release),
        "files": files,
        "legacy_bars_raw": legacy,
        "target_layout": {
            "daily": {
                "logical_table": "bronze/bigqmt_raw_overlay",
                "partition": ["year", "period"],
                "business_key": ["code", "bar_time", "period", "adjustment_mode"],
                "units": {"volume_lots": "hands/lots", "amount_yuan": "CNY"},
                "mapping": canonical_mapping,
            },
            "intraday": {
                "logical_table": "bronze/bigqmt_intraday_raw_overlay",
                "partition": ["year", "month", "period"],
                "business_key": ["code", "bar_time", "period", "adjustment_mode"],
                "units": {"volume_lots": "hands/lots", "amount_yuan": "CNY"},
                "mapping": canonical_mapping,
            },
        },
        "gates": {
            "candidate_manifest": "PASSED" if manifest.get("mode") == "LOCAL_CANDIDATE_ONLY_NO_LAKE_WRITE" else "BLOCKED",
            "candidate_readiness": "PASSED" if readiness.get("raw_bronze_import_ready") is True else "BLOCKED",
            "canonical_schema_mapping": "PASSED" if not errors else "BLOCKED",
            "legacy_direct_append": "BLOCKED_REQUIRES_ISOLATED_SCHEMA" if legacy_columns else "NOT_APPLICABLE",
            "publish_approval": "PENDING_EXPLICIT_REVIEW",
        },
        "safety": {
            "lake_write": False,
            "global_latest_updated": False,
            "redis_write": False,
            "broker_call": False,
            "orders_enabled": False,
        },
        "errors": errors,
        "next_action": "Review this plan, then separately implement and approve an isolated publisher; do not append directly to legacy bronze/bars_raw.",
    }
    output = release / "raw_bronze_import_plan.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"release_id": result["release_id"], "output": str(output), "gates": result["gates"], "safety": result["safety"]}, ensure_ascii=False, indent=2))
    return 0 if not errors and result["gates"]["candidate_readiness"] == "PASSED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
