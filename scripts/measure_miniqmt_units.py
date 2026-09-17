"""Measure MiniQMT volume scale from amount/close/volume ratios (read-only)."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--input", type=Path, required=True); parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(); frame = pd.read_csv(args.input)
    rows = []
    for code, group in frame.groupby("code"):
        x = group.iloc[0]; close = float(x["close"]); volume = float(x["volume"]); amount = float(x["amount"])
        implied_shares = amount / close if close else 0.0; ratio = implied_shares / volume if volume else None
        rows.append({"code": str(code), "sample_date": str(x["trade_date"]), "close": close, "volume": volume, "amount": amount, "implied_shares": implied_shares, "shares_to_volume_ratio": ratio})
    result = {"schema_version": 1, "kind": "miniqmt_unit_measurement", "created_at": datetime.now(timezone.utc).isoformat(), "rows": rows, "conclusion": "lots_supported" if rows and all(r["shares_to_volume_ratio"] is not None and 90 <= r["shares_to_volume_ratio"] <= 110 for r in rows) else "UNVERIFIED", "orders_enabled": False, "broker_calls": False, "lake_write": False, "global_latest_updated": False}
    args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"); print(json.dumps(result, ensure_ascii=False)); return 0 if result["conclusion"] == "lots_supported" else 2


if __name__ == "__main__": raise SystemExit(main())
