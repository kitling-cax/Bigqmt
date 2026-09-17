"""Probe AkShare/Sina ETF distribution dates for secondary PIT reconciliation."""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def _symbol(code: str) -> str:
    return ("sh" if code.endswith(".SH") else "sz") + code.split(".")[0]


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe AkShare ETF dividend dates without publishing")
    parser.add_argument("--delay", type=float, default=0.15)
    args = parser.parse_args()
    pool = json.loads((ROOT / "config/v1_1_17_etf_pool.json").read_text(encoding="utf-8"))
    codes = list(dict.fromkeys(str(x) for x in pool.get("qmt_codes", []) if x))
    result: dict[str, Any] = {
        "schema_version": 1,
        "kind": "akshare_etf_action_source_probe",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "mode": "SECONDARY_READ_ONLY_NO_LAKE_WRITE",
        "endpoint": "ak.fund_etf_dividend_sina",
        "codes": codes,
        "results": [],
        "safety": {"lake_write": False, "global_latest_updated": False, "qmt_write": False, "redis_write": False, "orders_enabled": False},
    }
    try:
        import akshare as ak
    except Exception as exc:
        result["status"] = "ERROR_IMPORTING_AKSHARE"
        result["error"] = f"{type(exc).__name__}: {exc}"
    else:
        for code in codes:
            item: dict[str, Any] = {"code": code, "symbol": _symbol(code)}
            try:
                frame = ak.fund_etf_dividend_sina(item["symbol"])
                item["rows"] = int(len(frame))
                item["columns"] = [str(x) for x in frame.columns]
                # The endpoint currently returns Chinese headers; retain only
                # the date and per-unit distribution values by column position.
                records = []
                for row in frame.itertuples(index=False, name=None):
                    records.append({"event_date": str(row[0])[:10], "per_div": str(row[1]) if len(row) > 1 else ""})
                item["actions"] = records
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
        "etf_action_coverage": "PARTIAL" if nonempty and len(nonempty) < len(codes) else ("PASSED" if len(nonempty) == len(codes) else "BLOCKED_EMPTY"),
        "pit_publishable": "PENDING_QMT_EVENT_RECONCILIATION_AND_AVAILABLE_AT",
    }
    output = ROOT / "runtime_data/evidence/simulation/bigqmt_missing_key_scans/akshare_etf_action_probe_20260912.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), "status": result["status"], "summary": result["summary"], "gates": result["gates"], "safety": result["safety"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
