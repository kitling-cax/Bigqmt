"""Probe ETF announcement dates/IDs for PIT availability evidence."""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe ETF announcements without publishing")
    parser.add_argument("--delay", type=float, default=0.15)
    args = parser.parse_args()
    pool = json.loads((ROOT / "config/v1_1_17_etf_pool.json").read_text(encoding="utf-8"))
    codes = list(dict.fromkeys(str(x) for x in pool.get("qmt_codes", []) if x))
    result: dict[str, Any] = {
        "schema_version": 1,
        "kind": "akshare_etf_announcement_source_probe",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "mode": "SECONDARY_READ_ONLY_NO_LAKE_WRITE",
        "endpoint": "ak.fund_announcement_dividend_em",
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
            item: dict[str, Any] = {"code": code, "symbol": code.split(".")[0]}
            try:
                frame = ak.fund_announcement_dividend_em(item["symbol"])
                item["rows"] = int(len(frame))
                records = []
                for row in frame.itertuples(index=False, name=None):
                    vals = list(row)
                    records.append({"announcement_date": str(vals[3])[:10] if len(vals) > 3 else "", "announcement_id": str(vals[4]) if len(vals) > 4 else "", "title": str(vals[1])[:240] if len(vals) > 1 else ""})
                item["announcements"] = records
                item["status"] = "OK"
            except Exception as exc:
                # AkShare currently raises Length mismatch when Eastmoney
                # returns a valid empty payload.  Treat that case as EMPTY,
                # not as an API failure, while preserving real errors.
                if isinstance(exc, ValueError) and "Length mismatch" in str(exc):
                    item["rows"] = 0
                    item["announcements"] = []
                    item["status"] = "EMPTY"
                else:
                    item["status"] = "ERROR"
                    item["error_type"] = type(exc).__name__
                    item["error"] = str(exc)[:300]
            result["results"].append(item)
            if args.delay > 0:
                time.sleep(args.delay)
        result["status"] = "PROBED"
    ok = [x for x in result["results"] if x.get("status") in {"OK", "EMPTY"}]
    nonempty = [x for x in ok if int(x.get("rows", 0)) > 0]
    result["summary"] = {
        "requested_codes": len(codes),
        "successful_codes": len(ok),
        "error_codes": sum(1 for x in result["results"] if x.get("status") == "ERROR"),
        "codes_with_announcements": len(nonempty),
        "announcement_rows": sum(int(x.get("rows", 0)) for x in nonempty),
    }
    result["gates"] = {
        "endpoint_readable": "PASSED" if result["status"] == "PROBED" and not result["summary"]["error_codes"] else "BLOCKED",
        "announcement_coverage": "PARTIAL" if nonempty and len(nonempty) < len(codes) else ("PASSED" if len(nonempty) == len(codes) else "BLOCKED_EMPTY"),
        "pit_available_at_ready": "PENDING_DATE_ONLY_TO_SESSION_MAPPING_AND_FACTOR_RECONCILIATION",
    }
    output = ROOT / "runtime_data/evidence/simulation/bigqmt_missing_key_scans/akshare_etf_announcement_probe_20260912.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), "status": result["status"], "summary": result["summary"], "gates": result["gates"], "safety": result["safety"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
