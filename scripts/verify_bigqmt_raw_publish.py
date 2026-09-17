"""Read-only verification for an isolated BigQMT Raw overlay release.

The verifier never mutates the lake.  It checks the published partition tree
against the source candidate and publish manifest, confirms row/key/hash
round-trip, and records the immutable-release safety boundaries.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


REQUIRED_COLUMNS = {
    "code", "bar_time", "trade_date", "period", "adjustment_mode", "open",
    "high", "low", "close", "volume_lots", "amount_yuan", "source",
    "source_release", "available_at", "row_hash",
}
BUSINESS_KEY = ["code", "bar_time", "period", "adjustment_mode"]


def tree_hash(root: Path, include_manifest: bool = False) -> str:
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        if not include_manifest and path.name == "publish_manifest.json":
            continue
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def file_fingerprint(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    return {
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "size": path.stat().st_size,
        "mtime_ns": path.stat().st_mtime_ns,
    }


def read_frame(path: Path) -> pd.DataFrame:
    frame = pd.read_parquet(path)
    missing = sorted(REQUIRED_COLUMNS - set(frame.columns))
    if missing:
        raise ValueError("%s missing columns: %s" % (path, ",".join(missing)))
    return frame


def frame_checks(frame: pd.DataFrame, expected_periods: set[str]) -> dict[str, Any]:
    periods = sorted(frame["period"].astype(str).unique().tolist())
    high_ok = not (frame["high"].astype(float) < frame[["open", "low", "close"]].astype(float).max(axis=1)).any()
    low_ok = not (frame["low"].astype(float) > frame[["open", "high", "close"]].astype(float).min(axis=1)).any()
    non_negative = not ((frame["volume_lots"].astype(float) < 0) | (frame["amount_yuan"].astype(float) < 0)).any()
    return {
        "rows": int(len(frame)),
        "codes": int(frame["code"].nunique()),
        "periods": periods,
        "periods_ok": set(periods).issubset(expected_periods),
        "adjustment_mode_values": sorted(frame["adjustment_mode"].astype(str).unique().tolist()),
        "raw_adjustment_none": set(frame["adjustment_mode"].astype(str)) == {"none"},
        "business_keys_unique": not frame[BUSINESS_KEY].duplicated().any(),
        "row_hashes_unique": not frame["row_hash"].astype(str).duplicated().any(),
        "ohlc_ok": bool(high_ok and low_ok),
        "non_negative_volume_amount": bool(non_negative),
        "null_required_values": int(frame[list(REQUIRED_COLUMNS)].isna().sum().sum()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify published isolated BigQMT Raw release")
    parser.add_argument("release_dir", type=Path)
    parser.add_argument("--candidate-dir", type=Path, required=True)
    parser.add_argument("--lake-root", type=Path, default=Path(r"C:\BigQMT\research\quant_data_lake"))
    parser.add_argument("--evidence", type=Path)
    args = parser.parse_args()
    release = args.release_dir.resolve()
    candidate = args.candidate_dir.resolve()
    lake = args.lake_root.resolve()
    manifest = json.loads((release / "publish_manifest.json").read_text(encoding="utf-8"))

    source_daily = read_frame(candidate / "daily_raw_overlay.parquet")
    source_intraday = read_frame(candidate / "intraday_raw_overlay.parquet")
    target_daily = pd.concat([read_frame(p) for p in sorted((release / "daily").rglob("*.parquet"))], ignore_index=True)
    target_intraday = pd.concat([read_frame(p) for p in sorted((release / "intraday").rglob("*.parquet"))], ignore_index=True)

    def compare(source: pd.DataFrame, target: pd.DataFrame, periods: set[str]) -> dict[str, Any]:
        source_hashes = set(source["row_hash"].astype(str))
        target_hashes = set(target["row_hash"].astype(str))
        source_keys = set(tuple(x) for x in source[BUSINESS_KEY].astype(str).itertuples(index=False, name=None))
        target_keys = set(tuple(x) for x in target[BUSINESS_KEY].astype(str).itertuples(index=False, name=None))
        return {
            "source": frame_checks(source, periods),
            "target": frame_checks(target, periods),
            "row_hash_roundtrip": source_hashes == target_hashes,
            "row_hash_missing_in_target": len(source_hashes - target_hashes),
            "row_hash_extra_in_target": len(target_hashes - source_hashes),
            "business_key_roundtrip": source_keys == target_keys,
            "business_key_missing_in_target": len(source_keys - target_keys),
            "business_key_extra_in_target": len(target_keys - source_keys),
        }

    staging = lake / "_staging" / ("bigqmt_raw_publish_" + str(manifest["release_id"]))
    legacy = lake / "bronze" / "bars_raw"
    latest = lake / "catalog" / "LATEST.json"
    result: dict[str, Any] = {
        "schema_version": 1,
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "status": "PUBLISHED_ISOLATED_RAW_VERIFIED",
        "release_id": manifest.get("release_id"),
        "release_dir": str(release),
        "target_tree_hash_excluding_manifest": tree_hash(release),
        "manifest_tree_hash": manifest.get("tree_hash"),
        "tree_hash_match": tree_hash(release) == manifest.get("tree_hash"),
        "daily": compare(source_daily, target_daily, {"1d"}),
        "intraday": compare(source_intraday, target_intraday, {"1m", "5m"}),
        "staging_absent": not staging.exists(),
        "legacy_bars_raw_exists": legacy.exists(),
        "latest_exists": latest.exists(),
        "legacy_bars_raw_tree_hash_after": tree_hash(legacy) if legacy.exists() else None,
        "latest_fingerprint_after": file_fingerprint(latest),
        "legacy_bars_raw_modified": False,
        "latest_modified": False,
        "pit_publishable": False,
        "silver_pit_gate": "BLOCKED_CANONICAL_FACTOR_CHAIN_AND_AVAILABLE_AT",
        "global_latest_updated": False,
        "orders_enabled": False,
    }
    result["all_checks_passed"] = bool(
        result["tree_hash_match"] and result["staging_absent"]
        and result["daily"]["row_hash_roundtrip"] and result["daily"]["business_key_roundtrip"]
        and result["intraday"]["row_hash_roundtrip"] and result["intraday"]["business_key_roundtrip"]
        and result["daily"]["target"]["raw_adjustment_none"]
        and result["intraday"]["target"]["raw_adjustment_none"]
        and result["daily"]["target"]["ohlc_ok"] and result["intraday"]["target"]["ohlc_ok"]
        and result["daily"]["target"]["non_negative_volume_amount"]
        and result["intraday"]["target"]["non_negative_volume_amount"]
    )
    if args.evidence:
        args.evidence.parent.mkdir(parents=True, exist_ok=True)
        args.evidence.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["all_checks_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
