"""Audit whether existing PIT/corporate-action evidence can cover a BigQMT release.

This is an evidence-only audit.  It never derives factors from prices and never
writes the shared lake.
"""
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ACTIONS = Path(r"C:\BigQMT\research\Alphaforge2\data\cache\pit_baseline\corporate_action_history_eastmoney.csv")
DEFAULT_FACTORS = ROOT / "runtime_data/evidence/simulation/bigqmt_missing_key_scans/divid_factor_cache_probe_20260912_120237.json"
DEFAULT_ETF_ACTIONS = ROOT / "runtime_data/evidence/simulation/bigqmt_missing_key_scans/akshare_etf_action_probe_20260912.json"


def _norm_day(value: Any) -> str:
    return str(value or "").replace("-", "")[:8]


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit BigQMT PIT source coverage without publishing")
    parser.add_argument("release_dir", nargs="?", type=Path, default=ROOT / "runtime_data/candidates/bigqmt_candidate_20260912_145717")
    parser.add_argument("--actions", type=Path, default=DEFAULT_ACTIONS)
    parser.add_argument("--factors", type=Path, default=DEFAULT_FACTORS)
    parser.add_argument("--etf-actions", type=Path, default=DEFAULT_ETF_ACTIONS)
    args = parser.parse_args()

    release = args.release_dir.resolve()
    candidate = json.loads((release / "manifest.json").read_text(encoding="utf-8"))
    factor_probe = json.loads(args.factors.read_text(encoding="utf-8"))
    codes = [str(code) for code in candidate.get("codes", [])]
    candidate_max: dict[str, str] = {}
    candidate_rows: dict[str, int] = {}
    # The manifest does not repeat per-code ranges, so read the compact parquet
    # through pandas only for the two audit columns.
    import pandas as pd
    frame = pd.read_parquet(release / "daily_raw_overlay.parquet", columns=["code", "trade_date"])
    for code, group in frame.groupby("code"):
        candidate_rows[str(code)] = int(len(group))
        candidate_max[str(code)] = max(_norm_day(x) for x in group["trade_date"])

    actions: dict[str, list[dict[str, str]]] = {}
    if args.actions.exists():
        with args.actions.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                code = str(row.get("ts_code") or "")
                actions.setdefault(code, []).append({
                    "ann_date": _norm_day(row.get("ann_date")),
                    "available_at": str(row.get("available_at") or ""),
                    "ex_date": _norm_day(row.get("ex_date")),
                    "source_version": str(row.get("source_version") or ""),
                })
    etf_actions: dict[str, set[str]] = {}
    if args.etf_actions.exists():
        etf_probe = json.loads(args.etf_actions.read_text(encoding="utf-8"))
        for item in etf_probe.get("results", []):
            etf_actions[str(item.get("code"))] = {
                _norm_day(action.get("event_date")) for action in item.get("actions", []) if _norm_day(action.get("event_date"))
            }

    by_code: dict[str, Any] = {}
    for item in factor_probe.get("results", []):
        code = str(item.get("code"))
        if code not in codes:
            continue
        qmt_days = sorted(_norm_day(day) for day in (item.get("factors") or {}).keys())
        action_rows = actions.get(code, [])
        ex_days = {row["ex_date"] for row in action_rows if row["ex_date"]}
        ann_days = {row["ann_date"] for row in action_rows if row["ann_date"]}
        exact_ex = sorted(set(qmt_days) & ex_days)
        ann_match = sorted(set(qmt_days) & ann_days)
        unmatched = sorted(set(qmt_days) - ex_days - ann_days)
        is_etf_like = code[:3] in {"159", "160", "161", "162", "501", "512", "513", "515", "518", "563"}
        etf_event_days = sorted(etf_actions.get(code, set()))
        etf_matches = sorted(set(qmt_days) & set(etf_event_days))
        etf_unmatched = sorted(set(qmt_days) - set(etf_event_days))
        etf_classification = "ETF_REQUIRES_ETF_ACTION_SOURCE" if not etf_event_days else (
            "ETF_EVENT_DATES_MATCHED" if not etf_unmatched else "ETF_EVENT_DATES_PARTIAL"
        )
        by_code[code] = {
            "candidate_rows": candidate_rows.get(code, 0),
            "candidate_max_trade_date": candidate_max.get(code),
            "qmt_factor_event_days": len(qmt_days),
            "qmt_factor_event_days_sample": qmt_days,
            "corporate_action_rows": len(action_rows),
            "corporate_action_latest_ex_date": max((row["ex_date"] for row in action_rows if row["ex_date"]), default=None),
            "exact_ex_date_matches": exact_ex,
            "announcement_date_matches": ann_match,
            "unmatched_qmt_event_days": unmatched,
            "etf_action_event_days": etf_event_days,
            "etf_qmt_event_days_matched": etf_matches,
            "etf_qmt_event_days_unmatched": etf_unmatched,
            "action_source_available": bool(action_rows),
            "classification": etf_classification if is_etf_like else ("STOCK_CHAIN_PARTIAL" if unmatched else "STOCK_CHAIN_EVENT_MATCHED"),
        }

    missing_code_entries = [code for code in codes if code not in by_code]
    stock_partial = [code for code, row in by_code.items() if row["classification"] == "STOCK_CHAIN_PARTIAL"]
    etf_missing = [code for code, row in by_code.items() if row["classification"] == "ETF_REQUIRES_ETF_ACTION_SOURCE"]
    etf_partial = [code for code, row in by_code.items() if row["classification"] == "ETF_EVENT_DATES_PARTIAL"]
    etf_matched = [code for code, row in by_code.items() if row["classification"] == "ETF_EVENT_DATES_MATCHED"]
    result = {
        "schema_version": 1,
        "kind": "bigqmt_pit_source_coverage_audit",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "mode": "READ_ONLY_NO_LAKE_WRITE_NO_FACTOR_INFERENCE",
        "release_id": candidate.get("release_id"),
        "release_dir": str(release),
        "sources": {"qmt_factor_probe": str(args.factors.resolve()), "corporate_actions": str(args.actions.resolve())},
        "summary": {
            "candidate_codes": len(codes),
            "candidate_daily_rows": int(len(frame)),
            "codes_with_factor_probe": len(by_code),
            "codes_without_factor_probe": len(missing_code_entries),
            "stock_chain_partial_codes": len(stock_partial),
            "etf_codes_requiring_etf_action_source": len(etf_missing),
            "etf_event_dates_matched_codes": len(etf_matched),
            "etf_event_dates_partial_codes": len(etf_partial),
        },
        "by_code": by_code,
        "missing_factor_probe_codes": missing_code_entries,
        "gates": {
            "qmt_factor_payload_readable": "PASSED" if not missing_code_entries else "BLOCKED",
            "stock_event_chain_complete": "BLOCKED" if stock_partial else "PASSED",
            "etf_action_event_date_reconciliation": "BLOCKED" if etf_partial else ("PASSED" if etf_matched else "NOT_APPLICABLE"),
            "etf_action_chain_available": "BLOCKED" if etf_missing or etf_partial else ("PARTIAL_NUMERIC_FIELDS" if etf_matched else "NOT_APPLICABLE"),
            "pit_publishable": "BLOCKED_CANONICAL_FACTOR_AND_AVAILABLE_AT_UNVERIFIED",
        },
        "safety": {"lake_write": False, "global_latest_updated": False, "orders_enabled": False},
        "next_action": "Acquire or refresh canonical stock/ETF corporate-action data with announcement availability timestamps; do not infer PIT factors from QMT adjusted prices.",
    }
    output = ROOT / "runtime_data/evidence/simulation/bigqmt_missing_key_scans/pit_source_coverage_20260912.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), "summary": result["summary"], "gates": result["gates"], "safety": result["safety"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
