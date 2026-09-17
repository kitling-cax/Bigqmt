"""Probe QMT daily history needed by the frozen PTrade v1.1.15 baseline.

This script only downloads/populates QMT's local history cache and reads it
through the read-only RPC allowlist.  It never calls an order method.  The
result is an evidence artifact, not a signal or execution result.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kitling_bigqmt.market_data import bars_to_dict, normalize_daily_bars  # noqa: E402
from kitling_bigqmt.readonly_rpc import ReadOnlyBigQmtClient  # noqa: E402
from kitling_bigqmt.redis_resp import RedisRespClient  # noqa: E402
from kitling_bigqmt.machine_config import load_gateway  # noqa: E402


def ptrade_to_qmt(code: str) -> str:
    suffix = ".SH" if code.endswith(".SS") else ".SZ"
    return code[:-3] + suffix


def _summary(bars):
    usable = [bar for bar in bars if bar.close is not None and bar.close > 0]
    return {
        "row_count": len(bars),
        "usable_close_count": len(usable),
        "first_date": bars[0].trade_date if bars else None,
        "last_date": bars[-1].trade_date if bars else None,
        "first_rows": bars_to_dict(bars[:3]),
        "last_rows": bars_to_dict(bars[-3:]),
    }


def _compare(raw, adjusted):
    raw_by_date = {bar.trade_date: bar.close for bar in raw}
    adj_by_date = {bar.trade_date: bar.close for bar in adjusted}
    common = sorted(set(raw_by_date).intersection(adj_by_date))
    diffs = [date for date in common
             if raw_by_date[date] is not None and adj_by_date[date] is not None
             and abs(float(raw_by_date[date]) - float(adj_by_date[date])) > 1e-9]
    return {
        "common_dates": len(common),
        "different_close_dates": len(diffs),
        "first_difference_date": diffs[0] if diffs else None,
        "last_difference_date": diffs[-1] if diffs else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--codes", nargs="*", help="QMT codes; defaults to two representative ETFs")
    parser.add_argument("--all", action="store_true", help="probe every U25 code plus fallback")
    parser.add_argument("--start", default="20180101")
    parser.add_argument("--end", default=datetime.now().strftime("%Y%m%d"))
    parser.add_argument("--config", default=None)
    args = parser.parse_args()

    manifest = json.loads((ROOT / "strategy_baselines" / "s10_d1_v1_1_15_ptrade.json").read_text(encoding="utf-8"))
    universe = [ptrade_to_qmt(code) for code in manifest["universe_ptrade"]]
    universe.append(ptrade_to_qmt(manifest["fallback_ptrade"]))
    codes = universe if args.all else (args.codes or ["511010.SH", ptrade_to_qmt(manifest["universe_ptrade"][0])])

    config = load_gateway(ROOT, "simulation") if args.config is None else json.loads(Path(args.config).read_text(encoding="utf-8"))
    client = ReadOnlyBigQmtClient(
        redis=RedisRespClient(**dict(config["redis"])),
        account_id=str(config["account_id"]),
        timeout_seconds=float(config.get("rpc_timeout_seconds", 12)),
    )
    artifact = {
        "schema_version": 1,
        "kind": "qmt_v1_1_15_market_data_probe",
        "created_at": datetime.now().astimezone().isoformat(),
        "environment": config.get("environment", "simulation"),
        "account_id": str(config["account_id"]),
        "source_manifest": str(ROOT / "strategy_baselines" / "s10_d1_v1_1_15_ptrade.json"),
        "source_sha256": manifest["source"]["sha256"],
        "start": args.start,
        "end": args.end,
        "orders_enabled": False,
        "codes": {},
    }

    for code in codes:
        entry = {"download": None, "dividend_types": {}, "errors": []}
        try:
            entry["download"] = client.download_history_data(code, "1d", args.start, args.end)
            series = {}
            for dividend_type in ("none", "front", "back"):
                response = client.market_data_ex(
                    [code], ["close", "preClose", "suspendFlag", "time"],
                    "1d", args.start, args.end, -1, dividend_type,
                )
                bars = normalize_daily_bars(response, code)
                series[dividend_type] = bars
                entry["dividend_types"][dividend_type] = _summary(bars)
            raw = series["none"]
            for dividend_type in ("front", "back"):
                entry["dividend_types"][dividend_type]["vs_none"] = _compare(raw, series[dividend_type])
        except Exception as exc:  # evidence must show the exact blocked code
            entry["errors"].append({"type": type(exc).__name__, "message": str(exc)})
        artifact["codes"][code] = entry

    evidence_dir = ROOT / "runtime_data" / "evidence" / "simulation"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = evidence_dir / ("qmt_v1_1_15_market_data_probe_%s.json" % stamp)
    output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), "codes": list(artifact["codes"]), "errors": {
        code: value["errors"] for code, value in artifact["codes"].items() if value["errors"]
    }}, ensure_ascii=False, indent=2))
    return 0 if not any(value["errors"] for value in artifact["codes"].values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
