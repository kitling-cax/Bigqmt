"""Fetch Tushare fund_daily ETF bars for a bounded overlap candidate."""
from __future__ import annotations
import argparse, json, os
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
import tushare as ts

def token_from(path: Path) -> str:
    vals={}
    if path.exists():
        for line in path.read_text(encoding='utf-8', errors='ignore').splitlines():
            if '=' in line and not line.lstrip().startswith('#'):
                k,v=line.split('=',1); vals[k.strip()]=v.strip().strip('"').strip("'")
    return os.environ.get('TUSHARE_TOKEN') or os.environ.get('TUSHARE_TOKEN_BACKUP') or vals.get('TUSHARE_TOKEN') or vals.get('TUSHARE_TOKEN_BACKUP','')

def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument('--codes-file',type=Path,required=True); ap.add_argument('--start',default='20260901'); ap.add_argument('--end',default='20260911'); ap.add_argument('--output',type=Path,required=True); ap.add_argument('--env-file',type=Path,default=Path(r'C:\BigQMT\research\Alphaforge2\.env')); args=ap.parse_args()
    token=token_from(args.env_file)
    if not token: raise RuntimeError('Tushare token not configured')
    pro=ts.pro_api(token); rows=[]; errors=[]
    for code in [x.strip().upper() for x in args.codes_file.read_text(encoding='utf-8').splitlines() if x.strip()]:
        try:
            d=pro.fund_daily(ts_code=code,start_date=args.start,end_date=args.end)
            if d is not None and not d.empty:
                d=d.rename(columns={'vol':'new_volume_lots','amount':'new_amount_thousand_yuan','open':'new_open','high':'new_high','low':'new_low','close':'new_close'})
                rows.append(d[['ts_code','trade_date','new_open','new_high','new_low','new_close','new_volume_lots','new_amount_thousand_yuan']])
        except Exception as exc: errors.append({'code':code,'error':f'{type(exc).__name__}: {exc}'})
    frame=pd.concat(rows,ignore_index=True) if rows else pd.DataFrame(columns=['ts_code','trade_date','new_open','new_high','new_low','new_close','new_volume_lots','new_amount_thousand_yuan'])
    frame=frame.sort_values(['ts_code','trade_date']) if not frame.empty else frame
    args.output.parent.mkdir(parents=True,exist_ok=True); frame.to_parquet(args.output,index=False)
    manifest={'schema_version':1,'kind':'tushare_fund_daily_overlap_candidate','created_at':datetime.now(timezone.utc).isoformat(),'codes_requested':len([x for x in args.codes_file.read_text(encoding='utf-8').splitlines() if x.strip()]),'codes_returned':int(frame.ts_code.nunique()) if len(frame) else 0,'rows':len(frame),'min_trade_date':str(frame.trade_date.min()) if len(frame) else None,'max_trade_date':str(frame.trade_date.max()) if len(frame) else None,'errors':errors,'volume_unit':'lots','amount_unit':'thousand_cny','credentials_persisted':False,'lake_write':False,'global_latest_updated':False,'orders_enabled':False,'broker_calls':False}
    (args.output.with_suffix(args.output.suffix+'.manifest.json')).write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8'); print(json.dumps(manifest,ensure_ascii=False)); return 0 if not errors else 2
if __name__=='__main__': raise SystemExit(main())
