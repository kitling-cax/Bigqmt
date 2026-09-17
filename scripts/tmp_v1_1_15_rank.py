"""Read-only current-rank probe for v1.1.15 U25 universe.

Prints the full momentum-score ranking of the 25-ETF (no-alcohol) universe
using the strategy's exact scoring path (front adjustment, 25-day weighted
log-regression), plus SMA4 eligibility.  No orders, no trades.
"""
from __future__ import annotations

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
    MOMENTUM_MAX,
    MOMENTUM_MIN,
    UNIVERSE_PTRADE,
    legacy_weighted_momentum,
    ptrade_to_qmt,
)


def _fetch(client, code, start, end, dividend_type):
    response = client.market_data_ex(
        [code], ["close", "preClose", "suspendFlag", "time"],
        "1d", start, end, -1, dividend_type,
    )
    return normalize_daily_bars(response, code)


def _positive(bars):
    return [float(bar.close) for bar in sorted(bars, key=lambda b: b.trade_date)
            if bar.close is not None and bar.close > 0]


def main() -> int:
    config = load_gateway(ROOT, "simulation")
    client = ReadOnlyBigQmtClient(
        redis=RedisRespClient(**dict(config["redis"])),
        account_id=str(config["account_id"]),
        timeout_seconds=float(config.get("rpc_timeout_seconds", 12)),
    )
    end = datetime.now().strftime("%Y%m%d")
    start = "20150101"
    rows = {}
    errors = []
    for ptrade_code in sorted(UNIVERSE_PTRADE):
        qmt_code = ptrade_to_qmt(ptrade_code)
        try:
            client.download_history_data(qmt_code, "1d", start, end)
            closes = _positive(_fetch(client, qmt_code, start, end, "front"))
            window = closes[-25:]
            score_value = legacy_weighted_momentum(window)
            sma4_pass = None
            if len(window) >= 4:
                sma4_pass = window[-1] > (sum(window[-4:]) / 4.0)
            rows[ptrade_code] = {
                "code": ptrade_code,
                "qmt": qmt_code,
                "score": score_value,
                "sma4_pass": sma4_pass,
                "last_close": window[-1] if window else None,
                "bars": len(closes),
            }
        except Exception as exc:
            market[ptrade_code] = {"adjusted": []}
            rows[ptrade_code] = {
                "code": ptrade_code, "qmt": qmt_code, "score": None,
                "sma4_pass": None, "last_close": None, "bars": 0,
            }
            errors.append({"ptrade": ptrade_code, "qmt": qmt_code,
                           "type": type(exc).__name__, "message": str(exc)})

    valid = [r for r in rows.values() if r["score"] is not None
             and MOMENTUM_MIN <= r["score"] <= MOMENTUM_MAX]
    high = [r for r in rows.values() if r["score"] is not None and r["score"] > MOMENTUM_MAX]
    low = [r for r in rows.values() if r["score"] is not None and r["score"] < MOMENTUM_MIN]
    missing = [r for r in rows.values() if r["score"] is None]
    valid.sort(key=lambda r: r["score"], reverse=True)
    high.sort(key=lambda r: r["score"], reverse=True)
    low.sort(key=lambda r: r["score"])
    missing.sort(key=lambda r: r["code"])

    def fmt(r):
        sma = ("SMA4=PASS" if r["sma4_pass"] else "SMA4=FAIL") if r["sma4_pass"] is not None else "SMA4=NA"
        close = f"close={r['last_close']:.3f}" if r["last_close"] is not None else "close=NA"
        return f"{r['code']:<10} ({r['qmt']})  score={r['score']:.4f}  {sma}  {close}  bars={r['bars']}"

    lines = []
    lines.append("=== v1.1.15 U25 no-alcohol ETF momentum rank (as-of %s close) ===" % end)
    lines.append("---- in-range [%.2f, %.2f] (eligible, by score desc) ----" % (MOMENTUM_MIN, MOMENTUM_MAX))
    for i, r in enumerate(valid, 1):
        lines.append("  %2d. %s" % (i, fmt(r)))
    lines.append("---- score > %.2f (rejected: momentum too hot) ----" % MOMENTUM_MAX)
    for r in high:
        lines.append("       %s" % fmt(r))
    lines.append("---- score < %.2f (rejected: momentum too weak) ----" % MOMENTUM_MIN)
    for r in low:
        lines.append("       %s" % fmt(r))
    if missing:
        lines.append("---- no score (insufficient/invalid data) ----")
        for r in missing:
            lines.append("       %s" % fmt(r))
    if errors:
        lines.append("--- fetch errors ---")
        for e in errors:
            lines.append(json.dumps(e, ensure_ascii=False))

    print("\n".join(lines))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
