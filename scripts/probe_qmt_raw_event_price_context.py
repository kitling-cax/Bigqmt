"""Report whether local BigQMT Raw candidates contain bars around PIT events."""
from __future__ import annotations
import json
from pathlib import Path
import duckdb
ROOT=Path(__file__).resolve().parents[1]
REL=ROOT/"runtime_data/candidates/bigqmt_candidate_20260912_145717"
Q=ROOT/"runtime_data/evidence/simulation/bigqmt_missing_key_scans/divid_factor_cache_probe_20260912_120237.json"
OUT=ROOT/"runtime_data/evidence/simulation/bigqmt_missing_key_scans/qmt_raw_event_price_context_20260912.json"
def main():
    events=[]; q=json.loads(Q.read_text(encoding='utf-8'))
    for i in q.get('results',[]):
        for dt in (i.get('factors') or {}): events.append((str(i.get('code')),str(dt).replace('-','')[:8]))
    with duckdb.connect() as db:
        rows=db.execute("select code, strftime(cast(trade_date as date),'%Y%m%d') as day, close, open, high, low from read_parquet(?) where period='1d'",[str(REL/'daily_raw_overlay.parquet')]).fetchall()
    by={(str(a),str(b)):{'close':c,'open':o,'high':h,'low':l} for a,b,c,o,h,l in rows}
    out=[]
    for code,day in events:
        # Find previous available candidate bar; candidate is missing-only, so absence
        # is expected when the lake already contains the prior date.
        prior=sorted((d for (c,d) in by if c==code and d<day), reverse=True)
        out.append({'code':code,'event_date':day,'event_bar':by.get((code,day)),'previous_candidate_day':prior[0] if prior else None,'previous_candidate_bar':by.get((code,prior[0])) if prior else None,'context_status':'COMPLETE_CANDIDATE_ONLY' if by.get((code,day)) and prior else 'INCOMPLETE_CANDIDATE_ONLY'})
    result={'schema_version':1,'kind':'qmt_raw_event_price_context','mode':'READ_ONLY_DIAGNOSTIC_NO_LAKE_WRITE','release_dir':str(REL.resolve()),'summary':{'events':len(out),'complete_candidate_only':sum(x['context_status']=='COMPLETE_CANDIDATE_ONLY' for x in out),'incomplete_candidate_only':sum(x['context_status']!='COMPLETE_CANDIDATE_ONLY' for x in out)},'events':out,'safety':{'lake_write':False,'global_latest_updated':False,'orders_enabled':False},'next_action':'Use QMT full raw cache plus canonical action fields for a formula-based factor rebuild; missing-only overlay alone is not sufficient.'}
    OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8'); print(json.dumps({'output':str(OUT),'summary':result['summary'],'safety':result['safety']},ensure_ascii=False,indent=2)); return 0
if __name__=='__main__': raise SystemExit(main())
