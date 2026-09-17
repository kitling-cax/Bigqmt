"""Build a local-only dry-run layout for a BigQMT raw overlay.

The output is deliberately below this project's ``runtime_data``.  It is a
publish rehearsal, not a data-lake publisher: no shared-lake file, DuckDB
catalog, ``LATEST``, Redis key, QMT state, or broker is touched.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.dataset as ds
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    "code", "bar_time", "trade_date", "period", "adjustment_mode", "open", "high", "low", "close",
    "volume_lots", "amount_yuan", "source", "source_release", "available_at", "row_hash",
]


def _latest_release() -> Path:
    candidates = ROOT / "runtime_data" / "candidates"
    dirs = sorted((p for p in candidates.glob("bigqmt_candidate_*") if p.is_dir()), key=lambda p: p.name)
    if not dirs:
        raise FileNotFoundError("no local BigQMT candidate release found")
    return dirs[-1]


def _read(path: Path) -> pd.DataFrame:
    frame = pd.read_parquet(path)
    missing = sorted(set(REQUIRED) - set(frame.columns))
    if missing:
        raise ValueError(f"{path.name} missing columns: {','.join(missing)}")
    frame = frame[REQUIRED].copy()
    frame["bar_time"] = pd.to_datetime(frame["bar_time"], utc=True)
    frame["available_at"] = pd.to_datetime(frame["available_at"], utc=True)
    return frame


def _hash_file_tree(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _write_partitioned(frame: pd.DataFrame, destination: Path, partition_cols: list[str]) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    working = frame.copy()
    working["year"] = pd.to_datetime(working["trade_date"].astype(str), format="%Y%m%d").dt.year.astype("int16")
    if "month" in partition_cols:
        working["month"] = pd.to_datetime(working["trade_date"].astype(str), format="%Y%m%d").dt.month.astype("int8")
    table = pa.Table.from_pandas(working, preserve_index=False)
    ds.write_dataset(
        table,
        base_dir=str(destination),
        format="parquet",
        partitioning=partition_cols,
        partitioning_flavor="hive",
        existing_data_behavior="error",
        file_options=ds.ParquetFileFormat().make_write_options(compression="zstd"),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a local-only BigQMT raw overlay dry run")
    parser.add_argument("release_dir", nargs="?", type=Path, help="candidate release; defaults to newest local release")
    args = parser.parse_args()
    release = (args.release_dir or _latest_release()).resolve()
    manifest = json.loads((release / "manifest.json").read_text(encoding="utf-8"))
    readiness = json.loads((release / "import_readiness.json").read_text(encoding="utf-8"))
    if readiness.get("raw_bronze_import_ready") is not True:
        raise SystemExit("candidate is not raw-bronze ready; dry-run layout refused")

    daily = _read(release / "daily_raw_overlay.parquet")
    intraday = _read(release / "intraday_raw_overlay.parquet")
    if set(daily["period"].astype(str)) != {"1d"}:
        raise SystemExit("daily candidate contains a non-1d period")
    if not set(intraday["period"].astype(str)).issubset({"1m", "5m"}):
        raise SystemExit("intraday candidate contains an unsupported period")

    output = ROOT / "runtime_data" / "publish_dryrun" / str(manifest["release_id"])
    if output.exists():
        existing_manifest = output / "dryrun_publish_manifest.json"
        if existing_manifest.exists():
            existing = json.loads(existing_manifest.read_text(encoding="utf-8"))
            if existing.get("release_id") == manifest.get("release_id") and existing.get("mode") == "LOCAL_PUBLISH_REHEARSAL_NO_LAKE_WRITE":
                print(json.dumps({"output_dir": str(output), "reused": True, "tables": existing.get("tables", {}), "safety": existing.get("safety", {})}, ensure_ascii=False, indent=2))
                return 0
        raise SystemExit(f"dry-run output already exists with a different manifest: {output}")
    _write_partitioned(daily, output / "daily", ["year", "period"])
    _write_partitioned(intraday, output / "intraday", ["year", "month", "period"])
    tree_hash = _hash_file_tree(output)
    result: dict[str, Any] = {
        "schema_version": 1,
        "kind": "bigqmt_raw_overlay_publish_dryrun",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "mode": "LOCAL_PUBLISH_REHEARSAL_NO_LAKE_WRITE",
        "release_id": manifest["release_id"],
        "source_release_dir": str(release),
        "output_dir": str(output),
        "tables": {
            "daily": {"path": "daily", "rows": len(daily), "partitioning": ["year", "period"], "periods": sorted(daily["period"].unique().tolist())},
            "intraday": {"path": "intraday", "rows": len(intraday), "partitioning": ["year", "month", "period"], "periods": sorted(intraday["period"].unique().tolist())},
        },
        "checks": {
            "canonical_columns": True,
            "daily_period_is_1d": True,
            "intraday_periods_supported": True,
            "output_tree_hash": tree_hash,
        },
        "safety": {
            "lake_write": False,
            "global_latest_updated": False,
            "redis_write": False,
            "broker_call": False,
            "orders_enabled": False,
        },
        "next_action": "Review local layout and isolated schema; only an explicitly approved publisher may target the shared lake.",
    }
    (output / "dryrun_publish_manifest.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output_dir": str(output), "tables": result["tables"], "safety": result["safety"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
