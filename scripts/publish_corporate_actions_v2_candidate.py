"""Publish reconciled corporate-action facts to an isolated v2 Bronze release."""
from __future__ import annotations
import argparse, json, sys
from datetime import datetime, timezone
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "src"))
from kitling_bigqmt.corporate_actions_v2 import build_action_rows, publish_action_candidate  # noqa: E402

def main() -> int:
    p = argparse.ArgumentParser(); p.add_argument("--evidence", type=Path, default=ROOT / "runtime_data/evidence/simulation/bigqmt_missing_key_scans/pit_event_reconciliation_20260912.json"); p.add_argument("--etf-pool", type=Path, default=ROOT / "config/v1_1_17_etf_pool.json"); p.add_argument("--lake-root", type=Path, default=Path(r"C:\BigQMT\research\quant_data_lake")); p.add_argument("--release-id", default=None); p.add_argument("--approve-publish", action="store_true"); args=p.parse_args()
    evidence=json.loads(args.evidence.read_text(encoding="utf-8")); pool=json.loads(args.etf_pool.read_text(encoding="utf-8")); codes={str(x).upper() for x in pool.get("qmt_codes", [])}; rid=args.release_id or "unified_v2_actions_"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"); rows=build_action_rows(evidence,codes,rid)
    result=publish_action_candidate(rows,rid,args.lake_root) if args.approve_publish else {"status":"READY_FOR_EXPLICIT_CORPORATE_ACTION_PUBLISH","release_id":rid,"rows":len(rows),"event_dates_verified":sum(x["date_status"]=="VERIFIED_EVENT_DATE" for x in rows),"global_latest_updated":False,"orders_enabled":False}
    print(json.dumps(result,ensure_ascii=False,indent=2)); return 0
if __name__=="__main__": raise SystemExit(main())
