"""Read-only freshness evidence for selected v2 source candidates."""
from __future__ import annotations
import argparse, json, sys
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"src"))
from kitling_bigqmt.freshness_v2 import assess_source_freshness  # noqa: E402

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bigqmt", type=Path, default=Path(r"C:\BigQMT\research\quant_data_lake\v2\bronze\bars\_releases\unified_v2_bronze_20260912T141745Z"))
    parser.add_argument("--tushare", type=Path, default=Path(r"C:\BigQMT\research\kitling_AI量化_review\reports\data_audit\af2_exception_candidate_20260911T005454Z\tushare_repair_candidate.parquet"))
    parser.add_argument("--expected-last-trade-date", default="20260911")
    parser.add_argument("--output", type=Path, default=ROOT/"runtime_data/evidence/simulation/unified_lake_v2/source_freshness_20260912.json")
    args = parser.parse_args()
    big_files = sorted(args.bigqmt.rglob("*.parquet")) if args.bigqmt.is_dir() else [args.bigqmt]
    ts_files = sorted(args.tushare.rglob("*.parquet")) if args.tushare.is_dir() else [args.tushare]
    if not big_files or not ts_files:
        raise SystemExit("source candidate path has no parquet files")
    bf = pd.concat([pd.read_parquet(p) for p in big_files], ignore_index=True)
    tf = pd.concat([pd.read_parquet(p) for p in ts_files], ignore_index=True)
    tf = tf.rename(columns={"ts_code": "code"})
    assessment = assess_source_freshness({"bigqmt": bf, "tushare": tf}, args.expected_last_trade_date)
    result = {"schema_version": 2, "kind": "unified_v2_source_freshness_evidence", "created_at": datetime.now(timezone.utc).isoformat(), "mode": "READ_ONLY_NO_LAKE_WRITE", "inputs": {"bigqmt": str(args.bigqmt), "tushare": str(args.tushare)}, "assessment": assessment, "safety": {"lake_write": False, "global_latest_updated": False, "orders_enabled": False}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(args.output), **assessment, "safety": result["safety"]}, ensure_ascii=False, indent=2))
    return 0
if __name__=="__main__": raise SystemExit(main())
