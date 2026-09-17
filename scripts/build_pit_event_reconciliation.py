"""Build a row-level QMT PIT event reconciliation, without publishing factors."""
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_QMT = ROOT / "runtime_data/evidence/simulation/bigqmt_missing_key_scans/divid_factor_cache_probe_20260912_120237.json"
DEFAULT_ETF = ROOT / "runtime_data/evidence/simulation/bigqmt_missing_key_scans/akshare_etf_action_probe_20260912.json"
DEFAULT_ANN = ROOT / "runtime_data/evidence/simulation/bigqmt_missing_key_scans/akshare_etf_announcement_probe_20260912.json"
DEFAULT_STOCK = Path(r"C:\BigQMT\research\Alphaforge2\data\cache\pit_baseline\corporate_action_history_eastmoney.csv")
DEFAULT_TUSHARE_STOCK = ROOT / "runtime_data/evidence/simulation/bigqmt_missing_key_scans/tushare_stock_unmatched_probe_20260912.json"


def _day(value: Any) -> str:
    return str(value or "").replace("-", "")[:8]


def main() -> int:
    parser = argparse.ArgumentParser(description="Reconcile QMT PIT events with secondary ETF announcements")
    parser.add_argument("--qmt", type=Path, default=DEFAULT_QMT)
    parser.add_argument("--etf-actions", type=Path, default=DEFAULT_ETF)
    parser.add_argument("--announcements", type=Path, default=DEFAULT_ANN)
    parser.add_argument("--stock-actions", type=Path, default=DEFAULT_STOCK)
    parser.add_argument("--tushare-stock", type=Path, default=DEFAULT_TUSHARE_STOCK)
    args = parser.parse_args()
    qmt = json.loads(args.qmt.read_text(encoding="utf-8"))
    etf = json.loads(args.etf_actions.read_text(encoding="utf-8"))
    ann = json.loads(args.announcements.read_text(encoding="utf-8"))
    etf_dates = {str(x.get("code")): {_day(a.get("event_date")) for a in x.get("actions", [])} for x in etf.get("results", [])}
    ann_rows = {str(x.get("code")): x.get("announcements", []) for x in ann.get("results", [])}
    stock_dates: dict[str, set[str]] = {}
    stock_ann: dict[str, list[dict[str, str]]] = {}
    if args.stock_actions.exists():
        with args.stock_actions.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                code = str(row.get("ts_code") or "")
                ex = _day(row.get("ex_date"))
                if ex:
                    stock_dates.setdefault(code, set()).add(ex)
                stock_ann.setdefault(code, []).append({
                    "announcement_date": _day(row.get("ann_date")),
                    "announcement_id": "",
                    "title": "stock corporate_action_history",
                })
    tushare_dates: dict[str, set[str]] = {}
    tushare_rows: dict[str, list[dict[str, Any]]] = {}
    if args.tushare_stock.exists():
        ts_data = json.loads(args.tushare_stock.read_text(encoding="utf-8"))
        for item in ts_data.get("results", []):
            code = str(item.get("code") or "")
            for row in item.get("actions", []):
                ex = _day(row.get("ex_date"))
                if ex:
                    tushare_dates.setdefault(code, set()).add(ex)
                tushare_rows.setdefault(code, []).append(row)
    events: list[dict[str, Any]] = []
    for item in qmt.get("results", []):
        code = str(item.get("code"))
        for event_date, payload in (item.get("factors") or {}).items():
            event_day = _day(event_date)
            external_dates = etf_dates.get(code, set()) | stock_dates.get(code, set()) | tushare_dates.get(code, set())
            announcement_pool = ann_rows.get(code, []) + stock_ann.get(code, [])
            external_action_rows = [r for r in tushare_rows.get(code, []) if _day(r.get("ex_date")) == event_day]
            matching_announcements = [a for a in announcement_pool if _day(a.get("announcement_date")) <= event_day]
            # Preserve QMT payload without claiming its meaning.  The final
            # factor element is diagnostic only until an independent numeric
            # share/dividend value is available.
            values = next(iter(payload.values())) if isinstance(payload, dict) and payload else []
            events.append({
                "code": code,
                "qmt_event_date": event_day,
                "qmt_payload": values,
                "secondary_event_date_matches": sorted(external_dates & {event_day}),
                "event_date_match": event_day in external_dates,
                "tushare_action_rows": external_action_rows,
                "announcement_candidates": matching_announcements,
                "available_at_status": "DATE_ONLY_CANDIDATE" if matching_announcements else "MISSING",
                "numeric_factor_status": "UNVERIFIED_EXTERNAL_NUMERIC_VALUE",
            })
    matched = [x for x in events if x["event_date_match"]]
    result = {
        "schema_version": 1,
        "kind": "bigqmt_pit_event_reconciliation",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "mode": "READ_ONLY_DIAGNOSTIC_NO_FACTOR_PUBLISH_NO_LAKE_WRITE",
        "sources": {"qmt": str(args.qmt.resolve()), "etf_actions": str(args.etf_actions.resolve()), "announcements": str(args.announcements.resolve()), "stock_actions": str(args.stock_actions.resolve()), "tushare_stock": str(args.tushare_stock.resolve())},
        "summary": {
            "qmt_event_rows": len(events),
            "event_date_matches": len(matched),
            "event_date_mismatches": len(events) - len(matched),
            "events_with_announcement_candidate": sum(1 for x in events if x["announcement_candidates"]),
            "events_with_tushare_action_row": sum(1 for x in events if x["tushare_action_rows"]),
        },
        "events": events,
        "gates": {
            "event_date_reconciliation": "PASSED" if events and len(matched) == len(events) else "BLOCKED",
            "available_at_exact_timestamp": "BLOCKED_DATE_ONLY",
            "numeric_factor_reconciliation": "BLOCKED_NO_INDEPENDENT_NUMERIC_FACTOR",
            "silver_pit_publishable": "BLOCKED",
        },
        "safety": {"lake_write": False, "global_latest_updated": False, "orders_enabled": False},
        "next_action": "Obtain independent ETF share/dividend numeric fields and timestamp semantics; stock event dates are now cross-checked with Tushare, but QMT numeric factor mapping remains unverified.",
    }
    output = ROOT / "runtime_data/evidence/simulation/bigqmt_missing_key_scans/pit_event_reconciliation_20260912.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), "summary": result["summary"], "gates": result["gates"], "safety": result["safety"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
