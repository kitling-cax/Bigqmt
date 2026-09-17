"""Generate a read-only QMT v1.1.15 close-signal sequence.

The script uses QMT ``none`` for raw risk prices and a selectable QMT
adjustment mode (default ``front``) for signal prices.  Since QMT has not yet
been proven equivalent to PTrade ``dypre``, the artifact is explicitly marked
as a probe.  Virtual fills use the next session's raw close only to advance the
target state; they are not execution or performance results.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kitling_bigqmt.market_data import normalize_daily_bars  # noqa: E402
from kitling_bigqmt.readonly_rpc import ReadOnlyBigQmtClient  # noqa: E402
from kitling_bigqmt.redis_resp import RedisRespClient  # noqa: E402
from kitling_bigqmt.machine_config import load_gateway  # noqa: E402
from kitling_bigqmt.v1_1_15_reproduction import (  # noqa: E402
    FALLBACK_PTRADE,
    UNIVERSE_PTRADE,
    advance_freezes,
    close_signal,
    new_state,
    ptrade_to_qmt,
    virtual_fill,
)


def _fetch(client, code, start, end, dividend_type):
    response = client.market_data_ex(
        [code], ["close", "preClose", "suspendFlag", "time"],
        "1d", start, end, -1, dividend_type,
    )
    return normalize_daily_bars(response, code)


def _positive_series(bars):
    return {bar.trade_date: float(bar.close) for bar in bars if bar.close is not None and bar.close > 0}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--adjustment", choices=("front", "back", "none"), default="front")
    parser.add_argument("--start", default="20180101", help="first signal date")
    parser.add_argument("--history-start", default="20150101", help="warm-up history start")
    parser.add_argument("--end", default=datetime.now().strftime("%Y%m%d"))
    parser.add_argument("--config", default=None)
    args = parser.parse_args()

    manifest_path = ROOT / "strategy_baselines" / "s10_d1_v1_1_15_ptrade.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    config = load_gateway(ROOT, "simulation") if args.config is None else json.loads(Path(args.config).read_text(encoding="utf-8"))
    client = ReadOnlyBigQmtClient(
        redis=RedisRespClient(**dict(config["redis"])),
        account_id=str(config["account_id"]),
        timeout_seconds=float(config.get("rpc_timeout_seconds", 12)),
    )

    all_ptrade = list(UNIVERSE_PTRADE) + [FALLBACK_PTRADE]
    adjusted: dict[str, dict[str, float]] = {}
    raw: dict[str, dict[str, float]] = {}
    errors = []
    for ptrade_code in all_ptrade:
        qmt_code = ptrade_to_qmt(ptrade_code)
        try:
            # History should have been populated by the preceding probe, but
            # keep this idempotent so a fresh QMT cache is safe.
            client.download_history_data(qmt_code, "1d", args.history_start, args.end)
            adjusted[ptrade_code] = _positive_series(_fetch(client, qmt_code, args.history_start, args.end, args.adjustment))
            raw[ptrade_code] = _positive_series(_fetch(client, qmt_code, args.history_start, args.end, "none"))
        except Exception as exc:
            errors.append({"ptrade_code": ptrade_code, "qmt_code": qmt_code,
                           "type": type(exc).__name__, "message": str(exc)})

    dates = sorted({day for series in adjusted.values() for day in series if args.start <= day <= args.end})
    state = new_state("RC1_QMT_PROBE")
    signals = []
    virtual_fills = []
    for day in dates:
        # A PTrade close signal on D executes from 09:31 on D+1.  This
        # transition is deliberately virtual and records its approximation.
        if state.get("pending_target"):
            target = state["pending_target"]
            fill_price = raw.get(target, {}).get(day)
            if fill_price is not None:
                fill = virtual_fill(state, day, fill_price)
                if fill:
                    virtual_fills.append(fill)
        advance_freezes(state)
        market = {}
        for code in all_ptrade:
            market[code] = {
                "adjusted": [value for date, value in adjusted.get(code, {}).items() if date <= day],
                "raw": [value for date, value in raw.get(code, {}).items() if date <= day],
            }
        result = close_signal(state, market, day, min_hold_days=5)
        if result["changed"] or result["reason"] not in ("NO_SWITCH", "MIN_HOLD_5", "PENDING_TARGET"):
            top = sorted(result["scores"].items(), key=lambda item: item[1], reverse=True)[:5]
            signals.append({
                "day": day, "current": result["current"], "desired": result["desired"],
                "reason": result["reason"], "risk": result["risk"], "best": result["best"],
                "top_scores": [{"security": code, "score": score} for code, score in top],
            })

    artifact = {
        "schema_version": 1,
        "kind": "qmt_v1_1_15_signal_probe",
        "status": "QMT_ADJUSTMENT_UNVERIFIED_AGAINST_PTRade_DYPRE",
        "created_at": datetime.now().astimezone().isoformat(),
        "environment": config.get("environment", "simulation"),
        "account_id": str(config["account_id"]),
        "source_manifest": str(manifest_path),
        "source_sha256": manifest["source"]["sha256"],
        "adjustment_mode": args.adjustment,
        "raw_mode": "none",
        "start": args.start, "history_start": args.history_start, "end": args.end,
        "orders_enabled": False,
        "approximation": "virtual next-session fill at raw close; no order/fill/performance claim",
        "errors": errors,
        "coverage": {"security_count": len(adjusted), "date_count": len(dates),
                     "first_date": dates[0] if dates else None, "last_date": dates[-1] if dates else None},
        "signal_count": len(signals), "virtual_fill_count": len(virtual_fills),
        "signals": signals, "virtual_fills": virtual_fills,
    }
    evidence_dir = ROOT / "runtime_data" / "evidence" / "simulation"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = evidence_dir / ("qmt_v1_1_15_signal_probe_%s.json" % stamp)
    output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), "status": artifact["status"],
                      "coverage": artifact["coverage"], "signal_count": len(signals),
                      "virtual_fill_count": len(virtual_fills), "errors": errors},
                     ensure_ascii=False, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
