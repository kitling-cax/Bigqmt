"""Reconcile v2 Bronze source facts into an isolated Silver Raw candidate."""
from __future__ import annotations
import argparse, json, sys
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from kitling_bigqmt.silver_canonical_v2 import build_candidate, publish_candidate  # noqa: E402

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--bronze-release", type=Path, default=Path(r"C:\BigQMT\research\quant_data_lake\v2\bronze\bars\_releases\unified_v2_bronze_20260912T141745Z"))
    p.add_argument("--lake-root", type=Path, default=Path(r"C:\BigQMT\research\quant_data_lake"))
    p.add_argument("--release-id", default=None)
    p.add_argument("--approve-publish", action="store_true")
    args = p.parse_args()
    files = sorted(args.bronze_release.rglob("*.parquet"))
    if not files: raise SystemExit("no Bronze parquet files")
    frame, checks = build_candidate(pd.concat([pd.read_parquet(path) for path in files], ignore_index=True), args.bronze_release.name)
    release_id = args.release_id or "unified_v2_silver_raw_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if args.approve_publish:
        result = publish_candidate(frame, checks, release_id, args.lake_root)
    else:
        result = {"status": "READY_FOR_EXPLICIT_SILVER_RAW_PUBLISH", "release_id": release_id, **checks,
                  "global_latest_updated": False, "pit_ready": False}
    print(json.dumps(result, ensure_ascii=False, indent=2)); return 0
if __name__ == "__main__": raise SystemExit(main())
