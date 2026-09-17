"""Evaluate (without writing data) whether the current v2 inputs can build PIT."""
from __future__ import annotations
import json, sys
import argparse
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"src"))
from kitling_bigqmt.pit_gate_v2 import evaluate_pit_inputs  # noqa: E402

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-manifest", type=Path, default=Path(r"C:\BigQMT\research\quant_data_lake\v2\silver\raw_canonical\_releases\unified_v2_silver_raw_20260912T142500Z\manifest.json"))
    parser.add_argument("--actions-manifest", type=Path, default=Path(r"C:\BigQMT\research\quant_data_lake\v2\bronze\corporate_actions\_releases\unified_v2_actions_20260912T143500Z\manifest.json"))
    parser.add_argument("--universe-status", default="BLOCKED_FORWARD_ONLY_NOT_HISTORICAL")
    parser.add_argument("--freshness-status", default="BLOCKED_TUSHARE_STALE")
    parser.add_argument("--universe-release", default="unified_v2_universe_20260912T144500Z")
    parser.add_argument("--freshness-evidence", default="source_freshness_20260912.json")
    parser.add_argument("--output", type=Path, default=ROOT/"runtime_data/evidence/simulation/unified_lake_v2/pit_v2_gate_20260912.json")
    args = parser.parse_args()
    raw = json.loads(args.raw_manifest.read_text(encoding="utf-8"))
    actions = json.loads(args.actions_manifest.read_text(encoding="utf-8"))
    result={"schema_version":2,"kind":"unified_v2_pit_gate_evidence","created_at":datetime.now(timezone.utc).isoformat(),"mode":"READ_ONLY_NO_PIT_WRITE","inputs":{"raw":str(args.raw_manifest),"actions":str(args.actions_manifest),"universe":args.universe_release,"freshness":args.freshness_evidence},"decision":evaluate_pit_inputs(raw, actions, args.universe_status, args.freshness_status),"safety":{"lake_write":False,"global_latest_updated":False,"orders_enabled":False}}
    args.output.parent.mkdir(parents=True,exist_ok=True); args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8"); print(json.dumps({"output":str(args.output),**result["decision"],"safety":result["safety"]},ensure_ascii=False,indent=2)); return 0
if __name__=="__main__": raise SystemExit(main())
