"""Probe Tushare ETF/LOF distribution actions for PIT cross-validation.

The probe is bounded and evidence-only.  It never writes credentials, QMT,
Redis, or the shared lake; Tushare is treated as a secondary reconciliation
source, not as a trading or primary-history source.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
FIELDS = "ts_code,ann_date,imp_anndate,base_date,div_proc,record_date,ex_date,pay_date,earpay_date,net_ex_date,div_cash,base_unit,ear_distr,ear_amount,account_date,base_year"


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe Tushare ETF actions without publishing")
    parser.add_argument("--delay", type=float, default=0.15)
    args = parser.parse_args()
    pool = json.loads((ROOT / "config/v1_1_17_etf_pool.json").read_text(encoding="utf-8"))
    codes = list(dict.fromkeys(str(x) for x in pool.get("qmt_codes", []) if x))
    token = os.environ.get("TUSHARE_TOKEN", "")
    result: dict[str, Any] = {
        "schema_version": 1,
        "kind": "tushare_etf_action_source_probe",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "mode": "SECONDARY_READ_ONLY_NO_LAKE_WRITE",
        "codes": codes,
        "token_present": bool(token),
        "token_recorded": False,
        "endpoint": "fund_div",
        "results": [],
        "summary": {},
        "safety": {"lake_write": False, "global_latest_updated": False, "qmt_write": False, "redis_write": False, "orders_enabled": False},
    }
    if not token:
        result["status"] = "BLOCKED_NO_TUSHARE_TOKEN"
    else:
        try:
            import tushare as ts
            pro = ts.pro_api(token)
        except Exception as exc:
            result["status"] = "ERROR_IMPORTING_TUSHARE"
            result["error"] = f"{type(exc).__name__}: {exc}"
        else:
            for code in codes:
                item: dict[str, Any] = {"code": code}
                try:
                    frame = pro.fund_div(ts_code=code, fields=FIELDS)
                    item["rows"] = int(len(frame))
                    item["columns"] = [str(x) for x in frame.columns]
                    # Keep only action dates and numeric distribution fields;
                    # no account or credential data is persisted.
                    keep = [x for x in ("ann_date", "imp_anndate", "base_date", "record_date", "ex_date", "pay_date", "net_ex_date", "div_cash", "base_unit", "ear_distr", "ear_amount") if x in frame.columns]
                    item["actions"] = frame[keep].fillna("").astype(str).to_dict("records")
                    item["status"] = "OK"
                except Exception as exc:
                    item["status"] = "ERROR"
                    item["error_type"] = type(exc).__name__
                    item["error"] = str(exc)[:300]
                result["results"].append(item)
                if args.delay > 0:
                    time.sleep(args.delay)
            result["status"] = "PROBED"
    ok = [x for x in result["results"] if x.get("status") == "OK"]
    nonempty = [x for x in ok if int(x.get("rows", 0)) > 0]
    result["summary"] = {
        "requested_codes": len(codes),
        "successful_codes": len(ok),
        "error_codes": sum(1 for x in result["results"] if x.get("status") == "ERROR"),
        "codes_with_actions": len(nonempty),
        "action_rows": sum(int(x.get("rows", 0)) for x in nonempty),
    }
    result["gates"] = {
        "endpoint_readable": "PASSED" if result["status"] == "PROBED" and not result["summary"]["error_codes"] else "BLOCKED",
        "etf_action_coverage": "PASSED" if len(nonempty) == len(codes) else "BLOCKED_PARTIAL_OR_EMPTY",
        "pit_publishable": "PENDING_CROSS_SOURCE_RECONCILIATION",
    }
    result["next_action"] = "Reconcile Tushare action dates/amounts with QMT factor events; require complete ETF coverage and available_at mapping before Silver PIT."
    output = ROOT / "runtime_data/evidence/simulation/bigqmt_missing_key_scans/tushare_etf_action_probe_20260912.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), "status": result["status"], "summary": result["summary"], "gates": result["gates"], "safety": result["safety"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
