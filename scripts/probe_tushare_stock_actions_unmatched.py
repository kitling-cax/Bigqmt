"""Probe Tushare stock dividend actions for QMT PIT event mismatches.

Evidence-only: credentials are read from the environment and never persisted;
no lake, QMT, Redis, or order state is changed.
"""
from __future__ import annotations

import json, os, time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runtime_data/evidence/simulation/bigqmt_missing_key_scans/tushare_stock_unmatched_probe_20260912.json"
FIELDS = "ts_code,ann_date,imp_anndate,div_proc,record_date,ex_date,pay_date,div_listdate,stk_div,stk_bo_rate,stk_div_rate,cash_div,cash_div_tax"

def main() -> int:
    codes = ["600519.SH", "300750.SZ"]
    result = {
        "schema_version": 1, "kind": "tushare_stock_unmatched_action_probe",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "mode": "SECONDARY_READ_ONLY_NO_LAKE_WRITE", "codes": codes,
        "token_present": bool(os.environ.get("TUSHARE_TOKEN")), "token_recorded": False,
        "results": [], "safety": {"lake_write": False, "global_latest_updated": False, "qmt_write": False, "redis_write": False, "orders_enabled": False},
    }
    token = os.environ.get("TUSHARE_TOKEN", "")
    if not token:
        result["status"] = "BLOCKED_NO_TUSHARE_TOKEN"
    else:
        try:
            import tushare as ts
            pro = ts.pro_api(token)
        except Exception as exc:
            result["status"] = "ERROR_IMPORTING_TUSHARE"; result["error"] = f"{type(exc).__name__}: {exc}"
        else:
            for code in codes:
                item = {"code": code}
                try:
                    frame = pro.dividend(ts_code=code, fields=FIELDS)
                    keep = [x for x in FIELDS.split(",") if x in frame.columns]
                    item["rows"] = int(len(frame)); item["columns"] = keep
                    item["actions"] = frame[keep].fillna("").astype(str).to_dict("records")
                    item["status"] = "OK"
                except Exception as exc:
                    item["status"] = "ERROR"; item["error_type"] = type(exc).__name__; item["error"] = str(exc)[:300]
                result["results"].append(item); time.sleep(0.2)
            result["status"] = "PROBED"
    ok = [x for x in result["results"] if x.get("status") == "OK"]
    result["summary"] = {"requested_codes": len(codes), "successful_codes": len(ok), "error_codes": sum(x.get("status") == "ERROR" for x in result["results"]), "action_rows": sum(int(x.get("rows", 0)) for x in ok)}
    result["gates"] = {"endpoint_readable": "PASSED" if result.get("status") == "PROBED" and not result["summary"]["error_codes"] else "BLOCKED", "numeric_factor_reconciliation": "PENDING_QMT_PAYLOAD_MAPPING", "pit_publishable": "BLOCKED"}
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(OUT), "status": result.get("status"), "summary": result["summary"], "gates": result["gates"], "safety": result["safety"]}, ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
