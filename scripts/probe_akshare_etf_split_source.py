"""Probe Eastmoney fund split/conversion history for QMT ETF events.

Bounded secondary read-only evidence. No credentials, lake, QMT, Redis, or
order state is written.
"""
from __future__ import annotations
import json, time
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runtime_data/evidence/simulation/bigqmt_missing_key_scans/akshare_etf_split_probe_20260912.json"
YEARS = ["2022", "2024", "2026"]

def main():
    pool=json.loads((ROOT/"config/v1_1_17_etf_pool.json").read_text(encoding="utf-8"))
    codes=list(dict.fromkeys(str(x) for x in pool.get("qmt_codes",[]) if x)); wanted={x.split('.')[0] for x in codes}
    result={"schema_version":1,"kind":"akshare_etf_split_source_probe","created_at":datetime.now(timezone.utc).isoformat(),"mode":"SECONDARY_READ_ONLY_NO_LAKE_WRITE","endpoint":"ak.fund_cf_em","years":YEARS,"codes":codes,"results":[],"safety":{"lake_write":False,"global_latest_updated":False,"qmt_write":False,"redis_write":False,"orders_enabled":False}}
    try:
        import akshare as ak
    except Exception as exc:
        result["status"]="ERROR_IMPORTING_AKSHARE"; result["error"]=f"{type(exc).__name__}: {exc}"
    else:
        hits=[]; errors=[]
        for year in YEARS:
            item={"year":year}
            try:
                frame=ak.fund_cf_em(year=year,page=-1)
                item["rows"]=int(len(frame)); item["columns"]=list(map(str,frame.columns))
                keep=frame[frame.iloc[:,1].astype(str).isin(wanted)] if len(frame.columns)>1 else pd.DataFrame()
                for row in keep.to_dict("records"):
                    hits.append({"year":year,"record":{str(k): (str(v) if not isinstance(v,(int,float)) else v) for k,v in row.items()}})
                item["matched_rows"]=int(len(keep)); item["status"]="OK"
            except Exception as exc:
                item["status"]="ERROR"; item["error_type"]=type(exc).__name__; item["error"]=str(exc)[:300]; errors.append(item)
            result["results"].append(item)
        result["matched"] = hits; result["status"]="PROBED"
    result["summary"]={"years_requested":len(YEARS),"successful_years":sum(x.get("status")=="OK" for x in result["results"]),"error_years":sum(x.get("status")=="ERROR" for x in result["results"]),"matched_rows":len(result.get("matched",[])),"matched_codes":len({str(x["record"].get("基金代码")) for x in result.get("matched",[])})}
    result["gates"]={"endpoint_readable":"PASSED" if result.get("status")=="PROBED" and not result["summary"]["error_years"] else "BLOCKED","etf_event_date_numeric_source":"PENDING_FIELD_MAPPING","pit_publishable":"BLOCKED"}
    OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"output":str(OUT),"status":result.get("status"),"summary":result["summary"],"gates":result["gates"],"safety":result["safety"]},ensure_ascii=False,indent=2)); return 0
if __name__=='__main__': raise SystemExit(main())
