"""Reconcile QMT ETF/LOF split payloads with Eastmoney split history.

QMT events commonly occur on the first trading day after the fund's split
conversion date. We preserve both dates and use the documented payload
relationship: ``bonus_shares ~= split_ratio - 1``. Cumulative factors are
reported as diagnostic approximations only and are never published.
"""
from __future__ import annotations
import json, math
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
QMT=ROOT/"runtime_data/evidence/simulation/bigqmt_missing_key_scans/divid_factor_cache_probe_20260912_120237.json"
SPLIT=ROOT/"runtime_data/evidence/simulation/bigqmt_missing_key_scans/akshare_etf_split_probe_20260912.json"
OUT=ROOT/"runtime_data/evidence/simulation/bigqmt_missing_key_scans/etf_split_field_reconciliation_20260912.json"
def day(v): return str(v or '').replace('-','')[:8]
def n(v):
    try: return float(v)
    except (TypeError,ValueError): return None
def close(a,b,tol=1e-5): return a is not None and b is not None and abs(a-b)<=tol*max(1.0,abs(a),abs(b))
def main():
    q=json.loads(QMT.read_text(encoding='utf-8')); s=json.loads(SPLIT.read_text(encoding='utf-8'))
    bycode={}
    for x in s.get('matched',[]):
        r=x.get('record',{}); bycode.setdefault(str(r.get('基金代码') or ''),[]).append({"split_date":day(r.get('拆分折算日')),"split_type":r.get('拆分类型'),"split_ratio":n(r.get('拆分折算')),"year":x.get('year')})
    rows=[]
    for item in q.get('results',[]):
        code=str(item.get('code') or '')
        if code.split('.')[0] not in bycode: continue
        for dt,payload in (item.get('factors') or {}).items():
            ev=day(dt); vals=next(iter(payload.values())) if isinstance(payload,dict) and payload else []
            candidates=[x for x in bycode[code.split('.')[0]] if x['split_date'] < ev]
            # Match the nearest preceding split record; date-only relation is
            # retained and not converted into an exact available_at timestamp.
            sp=sorted(candidates,key=lambda x:x['split_date'])[-1] if candidates else None
            q_bonus=n(vals[1]) if len(vals)>1 else None; q_factor=n(vals[6]) if len(vals)>6 else None
            ratio=sp.get('split_ratio') if sp else None
            rows.append({"code":code,"qmt_event_date":ev,"qmt_payload":vals,"split_record":sp,"date_relation":"PRECEDING_SPLIT_DATE" if sp else "MISSING","bonus_shares_relation":"MATCH" if sp and close(q_bonus,ratio-1.0) else "MISMATCH_OR_UNAVAILABLE","qmt_bonus_shares":q_bonus,"external_split_ratio":ratio,"qmt_cumulative_factor":q_factor,"cumulative_factor_diagnostic":"CLOSE_TO_SPLIT_RATIO" if sp and close(q_factor,ratio,0.01) else "NOT_USED_FOR_PUBLISH"})
    result={"schema_version":1,"kind":"bigqmt_etf_split_field_reconciliation","created_at":datetime.now(timezone.utc).isoformat(),"mode":"READ_ONLY_DIAGNOSTIC_NO_LAKE_WRITE","sources":{"qmt":str(QMT.resolve()),"eastmoney_split_via_akshare":str(SPLIT.resolve())},"summary":{"qmt_etf_event_rows":len(rows),"preceding_split_date_rows":sum(r['date_relation']=='PRECEDING_SPLIT_DATE' for r in rows),"bonus_shares_matches":sum(r['bonus_shares_relation']=='MATCH' for r in rows),"cumulative_factor_close_diagnostic":sum(r['cumulative_factor_diagnostic']=='CLOSE_TO_SPLIT_RATIO' for r in rows)},"rows":rows,"gates":{"etf_split_ratio_fields":"PASSED_DATE_AND_BONUS_RATIO" if rows and all(r['bonus_shares_relation']=='MATCH' for r in rows) else "BLOCKED_PARTIAL","etf_cash_dividend_fields":"NOT_APPLICABLE_FOR_THESE_SPLIT_EVENTS","available_at_exact_timestamp":"BLOCKED_DATE_ONLY","cumulative_factor_publishable":"BLOCKED_REQUIRES_RAW_PRICE_REBUILD","silver_pit_publishable":"BLOCKED"},"safety":{"lake_write":False,"global_latest_updated":False,"orders_enabled":False},"next_action":"Use split records as independent event evidence; map announcement/session availability and rebuild cumulative factors from raw bars before Silver PIT."}
    OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({"output":str(OUT),"summary":result['summary'],"gates":result['gates'],"safety":result['safety']},ensure_ascii=False,indent=2)); return 0
if __name__=='__main__': raise SystemExit(main())
