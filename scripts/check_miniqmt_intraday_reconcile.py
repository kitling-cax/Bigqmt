"""Read-only reconciliation of MiniQMT intraday sums against daily bars."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--daily", type=Path, required=True)
    parser.add_argument("--minute", type=Path, required=True)
    parser.add_argument("--five-minute", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    daily = pd.read_csv(args.daily); minute = pd.read_csv(args.minute); five = pd.read_csv(args.five_minute)
    rows = []
    for code in sorted(set(daily.code.astype(str))):
        d = daily[daily.code.astype(str) == code]
        result = {"code": code, "daily_rows": int(len(d)), "intraday": {}}
        for name, frame in (("1m", minute), ("5m", five)):
            x = frame[frame.code.astype(str) == code]
            result["intraday"][name] = {
                "rows": int(len(x)),
                "volume_sum": float(pd.to_numeric(x.volume, errors="coerce").sum()),
                "amount_sum": float(pd.to_numeric(x.amount, errors="coerce").sum()),
                "volume_delta": float(pd.to_numeric(x.volume, errors="coerce").sum() - pd.to_numeric(d.volume, errors="coerce").sum()),
                "amount_delta": float(pd.to_numeric(x.amount, errors="coerce").sum() - pd.to_numeric(d.amount, errors="coerce").sum()),
            }
        rows.append(result)
    result = {
        "schema_version": 1, "kind": "miniqmt_intraday_daily_reconciliation",
        "created_at": datetime.now(timezone.utc).isoformat(), "rows": rows,
        "status": "PASSED" if all(abs(v["amount_delta"]) < 1000 and abs(v["volume_delta"]) < 1 for r in rows for v in r["intraday"].values()) else "ATTENTION",
        "lake_write": False, "global_latest_updated": False, "orders_enabled": False, "broker_calls": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False)); return 0 if result["status"] == "PASSED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
