"""Reconcile QMT dividend payload fields against independent evidence.

QMT's documented payload order is [cash dividend, bonus shares, transfer
shares, rights ratio, rights price, reform flag, cumulative factor]. The
comparison is conservative: only source values explicitly present and numeric
are compared; the cumulative factor itself is never inferred or recomputed.
"""
from __future__ import annotations
import csv, json, math
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QMT = ROOT / "runtime_data/evidence/simulation/bigqmt_missing_key_scans/divid_factor_cache_probe_20260912_120237.json"
STOCK = Path(r"C:\BigQMT\research\Alphaforge2\data\cache\pit_baseline\corporate_action_history_eastmoney.csv")
TS = ROOT / "runtime_data/evidence/simulation/bigqmt_missing_key_scans/tushare_stock_unmatched_probe_20260912.json"
ETF = ROOT / "runtime_data/evidence/simulation/bigqmt_missing_key_scans/akshare_etf_action_probe_20260912.json"
OUT = ROOT / "runtime_data/evidence/simulation/bigqmt_missing_key_scans/pit_numeric_field_reconciliation_20260912.json"

def day(v): return str(v or "").replace("-", "")[:8]
def num(v):
    try:
        x = float(v); return x if math.isfinite(x) else None
    except (TypeError, ValueError): return None
def close(a,b): return a is not None and b is not None and abs(a-b) <= max(1e-6, 1e-6*max(abs(a),abs(b)))

def main():
    q = json.loads(QMT.read_text(encoding="utf-8"))
    bykey = {}
    if STOCK.exists():
        for r in csv.DictReader(STOCK.open("r", encoding="utf-8-sig", newline="")):
            bykey.setdefault((str(r.get("ts_code") or ""), day(r.get("ex_date"))), []).append({"source":"alphaforge2_eastmoney", **r})
    if TS.exists():
        for item in json.loads(TS.read_text(encoding="utf-8")).get("results", []):
            for r in item.get("actions", []):
                bykey.setdefault((str(item.get("code") or ""), day(r.get("ex_date"))), []).append({"source":"tushare_dividend", **r})
    events=[]
    for item in q.get("results", []):
        code=str(item.get("code") or "")
        for date,payload in (item.get("factors") or {}).items():
            vals=next(iter(payload.values())) if isinstance(payload,dict) and payload else []
            rows=bykey.get((code,day(date)),[])
            comparisons=[]
            for row in rows:
                ext=[num(row.get("cash_div")), num(row.get("stk_div") or row.get("share_div")), num(row.get("stk_div")), num(row.get("stk_bo_rate")), num(row.get("issue_price"))]
                # Tushare's cash_div/stk_div match the documented QMT positions
                # in observed stock responses; Eastmoney cache uses cash_div/share_div.
                pairs=[]
                for qi,ei in ((0,0),(2,1)):
                    qv=num(vals[qi]) if len(vals)>qi else None; ev=num(ext[ei]) if len(ext)>ei else None
                    if ev is not None:
                        relation = "EXACT" if close(qv, ev) else ("EXTERNAL_10X_QMT" if close(ev, None if qv is None else qv * 10.0) else ("QMT_10X_EXTERNAL" if close(qv, ev * 10.0) else "MISMATCH"))
                        pairs.append({"qmt_index":qi,"external_field":("cash_div" if qi==0 else "share_div_or_stk_div"),"qmt_value":qv,"external_value":ev,"match":relation=="EXACT","unit_relation":relation})
                comparisons.append({"source":row["source"],"pairs":pairs})
            usable=[c for c in comparisons if c["pairs"]]
            rels = [p["unit_relation"] for c in usable for p in c["pairs"]]
            source_exact = [c for c in usable if c["pairs"] and all(p["unit_relation"] == "EXACT" for p in c["pairs"])]
            numeric_status = ("VERIFIED_EXACT" if usable and rels and all(r == "EXACT" for r in rels) else
                              "VERIFIED_EXACT_WITH_SOURCE_CONFLICT" if source_exact else
                              "MIXED_CASH_UNIT_SCALE_10" if usable and "EXTERNAL_10X_QMT" in rels and all(r in {"EXACT", "EXTERNAL_10X_QMT"} for r in rels) else
                              "NO_INDEPENDENT_NUMERIC_ROW" if not usable else "MISMATCH_OR_PARTIAL")
            events.append({"code":code,"event_date":day(date),"qmt_payload":vals,"comparisons":comparisons,"numeric_status":numeric_status,"cumulative_factor_status":"UNVERIFIED_FORMULA_AND_CHAIN"})
    result={"schema_version":1,"kind":"bigqmt_pit_numeric_field_reconciliation","created_at":datetime.now(timezone.utc).isoformat(),"mode":"READ_ONLY_DIAGNOSTIC_NO_LAKE_WRITE","sources":{"qmt":str(QMT.resolve()),"stock_actions":str(STOCK.resolve()),"tushare_stock":str(TS.resolve())},"summary":{"qmt_events":len(events),"numeric_verified_exact":sum(e["numeric_status"]=="VERIFIED_EXACT" for e in events),"numeric_verified_exact_with_source_conflict":sum(e["numeric_status"]=="VERIFIED_EXACT_WITH_SOURCE_CONFLICT" for e in events),"mixed_cash_unit_scale_10":sum(e["numeric_status"]=="MIXED_CASH_UNIT_SCALE_10" for e in events),"no_independent_numeric_row":sum(e["numeric_status"]=="NO_INDEPENDENT_NUMERIC_ROW" for e in events),"mismatch_or_partial":sum(e["numeric_status"]=="MISMATCH_OR_PARTIAL" for e in events)},"events":events,"gates":{"cash_share_fields":"PARTIAL_EXACT_PLUS_UNIT_DIFFERENCE_REQUIRES_EXPLICIT_SOURCE_UNIT_CONTRACT" if events else "BLOCKED","cumulative_factor":"BLOCKED_FORMULA_NOT_INDEPENDENTLY_REBUILT","etf_numeric_coverage":"BLOCKED","silver_pit_publishable":"BLOCKED"},"safety":{"lake_write":False,"global_latest_updated":False,"orders_enabled":False},"next_action":"Document source units per endpoint/code, normalize only under an explicit contract, resolve source conflicts, complete independent ETF cash/share action values and canonical available_at/session mapping; then rebuild cumulative factors from raw bars."}
    OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"output":str(OUT),"summary":result["summary"],"gates":result["gates"],"safety":result["safety"]},ensure_ascii=False,indent=2)); return 0
if __name__=='__main__': raise SystemExit(main())
