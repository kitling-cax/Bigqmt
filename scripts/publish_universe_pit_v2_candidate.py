"""Publish a forward-only Universe PIT candidate from an explicit pool."""
from __future__ import annotations
import argparse, json, sys
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"src"))
from kitling_bigqmt.universe_pit_v2 import build_membership_rows, publish_universe_candidate  # noqa: E402
def main() -> int:
    p=argparse.ArgumentParser(); p.add_argument("--pool",type=Path,default=ROOT/"config/v1_1_17_etf_pool.json"); p.add_argument("--lake-root",type=Path,default=Path(r"C:\BigQMT\research\quant_data_lake")); p.add_argument("--effective-from",default="20260912"); p.add_argument("--available-at",default="2026-09-12T09:30:00+08:00"); p.add_argument("--release-id",default=None); p.add_argument("--approve-publish",action="store_true"); a=p.parse_args(); pool=json.loads(a.pool.read_text(encoding="utf-8")); rid=a.release_id or "unified_v2_universe_"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"); frame=build_membership_rows(pool.get("qmt_codes",[]),"etf",a.effective_from,a.available_at,"v1_1_17_etf_pool_config",rid); result=publish_universe_candidate(frame,rid,a.lake_root) if a.approve_publish else {"status":"READY_FOR_EXPLICIT_UNIVERSE_PUBLISH","release_id":rid,"rows":len(frame),"codes":int(frame.code.nunique()),"global_latest_updated":False,"global_publishable":False}; print(json.dumps(result,ensure_ascii=False,indent=2)); return 0
if __name__=="__main__": raise SystemExit(main())
