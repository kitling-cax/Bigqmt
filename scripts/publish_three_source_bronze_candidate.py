"""Publish a source-preserving, isolated v2 Bronze candidate for all three sources."""
from __future__ import annotations
import argparse, json, sys
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'src'))
from kitling_bigqmt.lake_ingest_v2 import APPROVAL_TOKEN, normalize_bigqmt, normalize_miniqmt, normalize_tushare, publish_bronze_candidate, validate_bronze  # noqa: E402

def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument('--miniqmt',type=Path,nargs='+',required=True); ap.add_argument('--bigqmt',type=Path,required=True); ap.add_argument('--tushare-stock',type=Path,required=True); ap.add_argument('--tushare-fund',type=Path,required=True); ap.add_argument('--lake-root',type=Path,default=Path(r'C:\BigQMT\research\quant_data_lake')); ap.add_argument('--release-id',required=True); ap.add_argument('--approve-publish',action='store_true'); args=ap.parse_args()
    pool=json.loads((ROOT/'config'/'v1_1_17_etf_pool.json').read_text(encoding='utf-8')); etfs={str(x).upper() for x in pool.get('qmt_codes',[])}
    m=normalize_miniqmt(pd.concat([pd.read_csv(p) for p in args.miniqmt],ignore_index=True),'miniqmt_embedded_20260912_u25','lots_measured','cny_measured',etfs)
    bf=list(args.bigqmt.rglob('*.parquet')); b=normalize_bigqmt(pd.concat([pd.read_parquet(p) for p in bf],ignore_index=True),'bigqmt_candidate_20260912_145717',etfs)
    ts=normalize_tushare(pd.read_parquet(args.tushare_stock),'tushare_repair_candidate_20260911T005454Z',etfs)
    tf=normalize_tushare(pd.read_parquet(args.tushare_fund),'tushare_fund_daily_20260912',etfs)
    frames=[m,b,ts,tf]; checks={str(src):validate_bronze(g) for src,g in pd.concat(frames,ignore_index=True).groupby('source')}
    if args.approve_publish: result=publish_bronze_candidate(frames,args.release_id,args.lake_root,APPROVAL_TOKEN)
    else: result={'status':'READY_FOR_EXPLICIT_THREE_SOURCE_BRONZE_PUBLISH','release_id':args.release_id,'checks_by_source':checks,'rows':sum(len(x) for x in frames),'global_latest_updated':False,'orders_enabled':False,'broker_calls':False}
    print(json.dumps(result,ensure_ascii=False,indent=2)); return 0
if __name__=='__main__': raise SystemExit(main())
