"""Fetch a source-preserving Tushare listing-universe candidate.

This is deliberately a candidate builder, not a global Universe PIT publisher.
Tushare ``stock_basic``/``fund_basic`` are current snapshots; their listing and
delisting fields are useful interval evidence, but a snapshot alone does not
prove the historical ``available_at`` of each membership change.  Rows are
therefore written to an isolated staging directory with an explicit
``SNAPSHOT_ONLY`` availability status and can never update ``LATEST``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import tushare as ts


STOCK_FIELDS = "ts_code,symbol,name,exchange,list_status,list_date,delist_date"
FUND_FIELDS = "ts_code,name,market,fund_type,status,found_date,list_date,delist_date"


def _hash(row: dict[str, object]) -> str:
    payload = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _fetch_stock(pro: object) -> pd.DataFrame:
    frames = []
    for status in ("L", "D", "P"):
        frame = pro.stock_basic(exchange="", list_status=status, fields=STOCK_FIELDS)
        if frame is not None and not frame.empty:
            frame = frame.copy()
            frame["snapshot_list_status"] = status
            frames.append(frame)
    if not frames:
        return pd.DataFrame(columns=STOCK_FIELDS.split(",") + ["snapshot_list_status"])
    return pd.concat(frames, ignore_index=True).drop_duplicates("ts_code", keep="last")


def _fetch_fund(pro: object) -> pd.DataFrame:
    frames = []
    for status in ("L", "D", "I"):
        frame = pro.fund_basic(market="E", status=status, fields=FUND_FIELDS)
        if frame is not None and not frame.empty:
            frame = frame.copy()
            frame["snapshot_fund_status"] = status
            frames.append(frame)
    if not frames:
        return pd.DataFrame(columns=FUND_FIELDS.split(",") + ["snapshot_fund_status"])
    return pd.concat(frames, ignore_index=True).drop_duplicates("ts_code", keep="last")


def _rows(stock: pd.DataFrame, funds: pd.DataFrame, snapshot_at: str) -> tuple[pd.DataFrame, dict[str, int]]:
    output: list[dict[str, object]] = []
    quarantine = {"stock_missing_list_date": 0, "fund_missing_list_date": 0, "fund_rows": int(len(funds)), "stock_rows": int(len(stock))}
    for item in stock.to_dict(orient="records"):
        start = str(item.get("list_date") or "").strip()
        if not start or start.lower() in {"nan", "none"}:
            quarantine["stock_missing_list_date"] += 1
            continue
        end = str(item.get("delist_date") or "").strip()
        if end.lower() in {"nan", "none"}:
            end = None
        row = {"code": str(item["ts_code"]).upper(), "asset_class": "stock", "effective_from": start,
               "effective_to": end, "available_at": snapshot_at, "source": "tushare.stock_basic",
               "membership_status": "SNAPSHOT_INTERVAL_CANDIDATE", "availability_status": "SNAPSHOT_ONLY"}
        row["row_hash"] = _hash(row)
        output.append(row)
    for item in funds.to_dict(orient="records"):
        start = str(item.get("list_date") or "").strip()
        if not start or start.lower() in {"nan", "none"}:
            quarantine["fund_missing_list_date"] += 1
            continue
        end = str(item.get("delist_date") or "").strip()
        if end.lower() in {"nan", "none"}:
            end = None
        row = {"code": str(item["ts_code"]).upper(), "asset_class": "etf", "effective_from": start,
               "effective_to": end, "available_at": snapshot_at, "source": "tushare.fund_basic",
               "membership_status": "SNAPSHOT_INTERVAL_CANDIDATE", "availability_status": "SNAPSHOT_ONLY"}
        row["row_hash"] = _hash(row)
        output.append(row)
    frame = pd.DataFrame(output)
    return frame, quarantine


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--snapshot-at", default=None, help="timezone-aware fetch timestamp; defaults to now")
    args = parser.parse_args()
    token = os.environ.get("TUSHARE_TOKEN", "")
    if not token:
        raise SystemExit("TUSHARE_TOKEN is not configured")
    snapshot = args.snapshot_at or datetime.now(timezone.utc).isoformat()
    if pd.Timestamp(snapshot).tzinfo is None:
        raise SystemExit("--snapshot-at must include timezone")
    pro = ts.pro_api(token)
    stock, funds = _fetch_stock(pro), _fetch_fund(pro)
    frame, quarantine = _rows(stock, funds, pd.Timestamp(snapshot).isoformat())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    parquet = args.output.with_suffix(".parquet")
    manifest = args.output.with_suffix(".manifest.json")
    frame.to_parquet(parquet, index=False, engine="pyarrow", compression="zstd")
    result = {"schema_version": 2, "kind": "tushare_universe_pit_candidate", "created_at": datetime.now(timezone.utc).isoformat(),
              "mode": "READ_ONLY_ISOLATED_CANDIDATE", "source": "tushare", "source_snapshot_at": pd.Timestamp(snapshot).isoformat(),
              "rows": int(len(frame)), "codes": int(frame["code"].nunique()) if not frame.empty else 0,
              "asset_class_counts": frame["asset_class"].value_counts().to_dict() if not frame.empty else {},
              "quarantine": quarantine, "availability_policy": "SNAPSHOT_ONLY_NOT_HISTORICAL_PIT",
              "historical_usable": False, "global_publishable": False, "global_latest_updated": False,
              "target_parquet": str(parquet), "limitations": ["current Tushare snapshot is not historical membership evidence", "fund_basic list_date is missing for some exchange funds", "exact announcement/session available_at is not asserted"]}
    manifest.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
