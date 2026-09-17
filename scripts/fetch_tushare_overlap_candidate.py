"""Fetch a bounded Tushare daily overlap candidate without lake writes."""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import tushare as ts


def read_token(env_file: Path) -> str:
    values = {}
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8", errors="ignore").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1); values[k.strip()] = v.strip().strip('"').strip("'")
    return os.environ.get("TUSHARE_TOKEN") or os.environ.get("TUSHARE_TOKEN_BACKUP") or values.get("TUSHARE_TOKEN") or values.get("TUSHARE_TOKEN_BACKUP", "")


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--codes-file", type=Path, required=True); parser.add_argument("--start", default="20260901"); parser.add_argument("--end", default="20260911"); parser.add_argument("--output", type=Path, required=True); parser.add_argument("--env-file", type=Path, default=Path(r"C:\BigQMT\research\Alphaforge2\.env"))
    args = parser.parse_args(); token = read_token(args.env_file)
    if not token: raise RuntimeError("Tushare token not configured")
    codes = [line.strip().upper() for line in args.codes_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    pro = ts.pro_api(token)
    proxy = os.environ.get("TUSHARE_PROXY_URL")
    if proxy: pro._DataApi__http_url = proxy
    frame = pro.daily(ts_code=",".join(codes), start_date=args.start, end_date=args.end)
    if frame is None: frame = pd.DataFrame()
    frame = frame.rename(columns={"vol": "new_volume_lots", "amount": "new_amount_thousand_yuan", "open": "new_open", "high": "new_high", "low": "new_low", "close": "new_close"})
    keep = ["ts_code", "trade_date", "new_open", "new_high", "new_low", "new_close", "new_volume_lots", "new_amount_thousand_yuan"]
    for col in keep:
        if col not in frame.columns: frame[col] = pd.Series(dtype="float64")
    frame = frame[keep].sort_values(["ts_code", "trade_date"]) if not frame.empty else pd.DataFrame(columns=keep)
    args.output.parent.mkdir(parents=True, exist_ok=True); frame.to_parquet(args.output, index=False)
    manifest = {"schema_version": 1, "kind": "tushare_overlap_candidate", "created_at": datetime.now(timezone.utc).isoformat(), "codes_requested": len(codes), "rows": len(frame), "min_trade_date": str(frame.trade_date.min()) if len(frame) else None, "max_trade_date": str(frame.trade_date.max()) if len(frame) else None, "volume_unit": "lots", "amount_unit": "thousand_cny", "credentials_persisted": False, "lake_write": False, "global_latest_updated": False, "orders_enabled": False, "broker_calls": False}
    (args.output.with_suffix(args.output.suffix + ".manifest.json")).write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"); print(json.dumps(manifest, ensure_ascii=False)); return 0


if __name__ == "__main__": raise SystemExit(main())
