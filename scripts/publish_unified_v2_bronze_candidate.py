"""Build/publish an isolated, source-preserving v2 Bronze candidate."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from kitling_bigqmt.lake_ingest_v2 import (APPROVAL_TOKEN, normalize_bigqmt, normalize_tushare,
                                            publish_bronze_candidate, validate_bronze)  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish unified lake v2 Bronze candidate")
    parser.add_argument("--bigqmt", type=Path, default=Path(r"C:\BigQMT\research\quant_data_lake\bronze\_bigqmt_raw_releases\bigqmt_candidate_20260912_145717\daily"))
    parser.add_argument("--tushare", type=Path, default=Path(r"C:\BigQMT\research\kitling_AI量化_review\reports\data_audit\af2_exception_candidate_20260911T005454Z\tushare_repair_candidate.parquet"))
    parser.add_argument("--lake-root", type=Path, default=Path(r"C:\BigQMT\research\quant_data_lake"))
    parser.add_argument("--etf-pool", type=Path, default=ROOT / "config" / "v1_1_17_etf_pool.json")
    parser.add_argument("--release-id", default=None)
    parser.add_argument("--approve-publish", action="store_true")
    args = parser.parse_args()
    pool = json.loads(args.etf_pool.read_text(encoding="utf-8")) if args.etf_pool.exists() else {}
    etf_codes = {str(item).upper() for item in pool.get("qmt_codes", [])}
    big_files = sorted(args.bigqmt.rglob("*.parquet")) if args.bigqmt.is_dir() else [args.bigqmt]
    tushare_files = sorted(args.tushare.rglob("*.parquet")) if args.tushare.is_dir() else [args.tushare]
    big = normalize_bigqmt(pd.concat([pd.read_parquet(path) for path in big_files], ignore_index=True), "bigqmt_candidate_20260912_145717", etf_codes)
    ts = normalize_tushare(pd.concat([pd.read_parquet(path) for path in tushare_files], ignore_index=True), "tushare_repair_candidate_20260911T005454Z", etf_codes)
    checks = {"bigqmt": validate_bronze(big), "tushare": validate_bronze(ts)}
    release_id = args.release_id or ("unified_v2_bronze_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    if not args.approve_publish:
        result = {"status": "READY_FOR_EXPLICIT_UNIFIED_V2_BRONZE_PUBLISH", "release_id": release_id,
                  "checks": checks, "rows": len(big) + len(ts), "global_latest_updated": False,
                  "orders_enabled": False, "broker_calls": False}
    else:
        result = publish_bronze_candidate([big, ts], release_id, args.lake_root, APPROVAL_TOKEN)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
