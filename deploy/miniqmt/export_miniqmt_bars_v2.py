"""Run inside QMT's embedded Python to export MiniQMT raw bars to F staging.

Python 3.6-compatible.  It only calls xtdata market-data APIs; it never
imports xttrader and has no order/cancel capability.  The host-side importer
must receive a separately measured unit contract before ingestion.
"""
from __future__ import print_function
import argparse, csv, json, os, sys
from datetime import datetime

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--codes-file", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--period", default="1d", choices=("1d", "1m", "5m"))
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--client-path", default=None)
    args = parser.parse_args()
    if args.client_path and args.client_path not in sys.path:
        sys.path.insert(0, args.client_path)
    from xtquant import xtdata
    codes = [line.strip().upper() for line in open(args.codes_file, "r") if line.strip()]
    fields = ["open", "high", "low", "close", "volume", "amount"]
    payload = xtdata.get_market_data_ex(fields, codes, args.period, args.start, args.end, -1, "none", False)
    rows = []
    for code in codes:
        frame = payload.get(code)
        if frame is None or len(frame) == 0:
            continue
        for index, values in frame.iterrows():
            raw_index = str(index)
            digits = "".join(ch for ch in raw_index if ch.isdigit())
            # QMT commonly returns YYYYMMDDHHMMSS for intraday and YYYYMMDD
            # for daily; normalize the business date to exactly YYYYMMDD.
            day = digits[:8] if len(digits) >= 8 else raw_index[:10].replace("-", "")
            rows.append({"code": code, "trade_date": day, "bar_time": raw_index, "frequency": args.period,
                         "open": values.get("open"), "high": values.get("high"), "low": values.get("low"),
                         "close": values.get("close"), "volume": values.get("volume"), "amount": values.get("amount")})
    output = os.path.abspath(args.output); parent = os.path.dirname(output)
    if not os.path.isdir(parent): os.makedirs(parent)
    with open(output, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["code", "trade_date", "bar_time", "frequency", "open", "high", "low", "close", "volume", "amount"])
        writer.writeheader(); writer.writerows(rows)
    manifest = {"schema_version": 1, "kind": "miniqmt_raw_export", "created_at": datetime.now().isoformat(),
                "source": "miniqmt_xtdata", "period": args.period, "codes": len(codes), "rows": len(rows),
                "dividend_type": "none", "unit_status": "MEASURE_BEFORE_HOST_IMPORT", "orders_enabled": False}
    with open(output + ".manifest.json", "w") as handle: json.dump(manifest, handle, ensure_ascii=False, indent=2)
    print(json.dumps(manifest, ensure_ascii=False)); return 0

if __name__ == "__main__": raise SystemExit(main())
