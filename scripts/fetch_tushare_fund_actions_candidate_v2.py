"""Fetch Tushare ETF/LOF dividend events as an isolated action candidate."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import tushare as ts


def _hash(row: dict[str, object]) -> str:
    payload = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def fetch_events(pro: object, codes: list[str]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for code in sorted({str(item).upper() for item in codes}):
        frame = pro.fund_div(ts_code=code)
        if frame is None or frame.empty:
            continue
        for item in frame.to_dict(orient="records"):
            ex_date = item.get("ex_date") or item.get("net_ex_date")
            if not ex_date or str(ex_date).lower() in {"nan", "none"}:
                continue
            row: dict[str, object] = {
                "code": code, "asset_class": "etf", "action_type": "cash_dividend",
                "ex_date": str(ex_date), "announcement_at": item.get("ann_date"),
                "available_at": None, "cash_per_share": item.get("div_cash"),
                "bonus_ratio": None, "transfer_ratio": None, "rights_ratio": None,
                "rights_price": None, "source": "tushare.fund_div",
                "source_endpoint": "fund_div", "unit_contract_version": "TUSHARE_FUND_DIV_CASH_PER_SHARE_CANDIDATE_V1",
                "available_at_status": "DATE_ONLY_CANDIDATE", "numeric_status": "CANDIDATE_UNVERIFIED",
                "record_date": item.get("record_date"), "pay_date": item.get("pay_date"),
                "raw_base_unit": item.get("base_unit"), "raw_div_cash": item.get("div_cash"),
            }
            row["evidence_hash"] = _hash({k: row[k] for k in row if k not in {"evidence_hash", "row_hash"}})
            row["row_hash"] = _hash(row)
            rows.append(row)
    return pd.DataFrame(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--codes", type=Path, required=True, help="JSON file containing qmt_codes")
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    token = os.environ.get("TUSHARE_TOKEN", "")
    if not token:
        raise SystemExit("TUSHARE_TOKEN is not configured")
    pool = json.loads(args.codes.read_text(encoding="utf-8"))
    frame = fetch_events(ts.pro_api(token), pool.get("qmt_codes", []))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    parquet = args.output.with_suffix(".parquet")
    manifest = args.output.with_suffix(".manifest.json")
    frame.to_parquet(parquet, index=False, engine="pyarrow", compression="zstd")
    result = {
        "schema_version": 2, "kind": "tushare_fund_corporate_actions_candidate",
        "created_at": datetime.now(timezone.utc).isoformat(), "mode": "READ_ONLY_ISOLATED_CANDIDATE",
        "source": "tushare.fund_div", "requested_codes": len(pool.get("qmt_codes", [])),
        "rows": int(len(frame)), "codes": int(frame["code"].nunique()) if not frame.empty else 0,
        "available_at_gate": "BLOCKED_DATE_ONLY", "numeric_factor_gate": "BLOCKED_UNVERIFIED",
        "global_publishable": False, "global_latest_updated": False, "target_parquet": str(parquet),
        "limitations": ["announcement and availability are date-only candidates", "cash-per-share unit and factor formula require independent reconciliation", "does not include split/merge events"]
    }
    manifest.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
