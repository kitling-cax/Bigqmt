"""Compare QMT raw-price risk triggers with PTrade v1.1.15 log reasons."""

from __future__ import annotations

import argparse
import bisect
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from kitling_bigqmt.market_data import normalize_daily_bars  # noqa: E402
from kitling_bigqmt.readonly_rpc import ReadOnlyBigQmtClient  # noqa: E402
from kitling_bigqmt.redis_resp import RedisRespClient  # noqa: E402
from kitling_bigqmt.machine_config import load_gateway  # noqa: E402
from kitling_bigqmt.v1_1_15_reproduction import (  # noqa: E402
    FALLBACK_PTRADE,
    UNIVERSE_PTRADE,
    ptrade_to_qmt,
)
from replay_v1_1_15_ptrade_state import load_log  # noqa: E402


DEFAULT_STATE = ROOT / "runtime_data" / "evidence" / "simulation" / "ptrade_v1_1_15_state_replay_20260908_134253.json"
DEFAULT_LOG = Path(r"C:\BigQMT\research\PTtrade策略编辑器\ptrade策略项目\S10-D1_低频动量轮动_RC1-RC2\5日回测\持有5天v1.1.15_长期\持有5天v1.1.15_长期.txt")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--ptrade-log", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--history-start", default="20150101")
    parser.add_argument("--end", default=datetime.now().strftime("%Y%m%d"))
    parser.add_argument("--config", default=None)
    args = parser.parse_args()

    state = json.loads(args.state.read_text(encoding="utf-8"))
    log_rows = load_log(args.ptrade_log)
    config = load_gateway(ROOT, "simulation") if args.config is None else json.loads(Path(args.config).read_text(encoding="utf-8"))
    client = ReadOnlyBigQmtClient(RedisRespClient(**dict(config["redis"])), str(config["account_id"]),
                                  timeout_seconds=float(config.get("rpc_timeout_seconds", 12)))
    raw: dict[str, dict[str, float]] = {}
    errors = []
    for code in list(UNIVERSE_PTRADE) + [FALLBACK_PTRADE]:
        qmt_code = ptrade_to_qmt(code)
        try:
            client.download_history_data(qmt_code, "1d", args.history_start, args.end)
            bars = normalize_daily_bars(client.market_data_ex(
                [qmt_code], ["close", "time"], "1d", args.history_start, args.end, -1, "none"), qmt_code)
            raw[code] = {bar.trade_date: float(bar.close) for bar in bars
                         if bar.close is not None and bar.close > 0}
        except Exception as exc:
            errors.append({"code": code, "type": type(exc).__name__, "message": str(exc)})

    trade_days = sorted(state["daily_positions"])
    entry_days: dict[str, list[str]] = {}
    for event in state["entry_exit_events"]:
        if event["event"] == "ENTRY_OR_REENTRY":
            entry_days.setdefault(event["code"], []).append(event["day"])
    comparisons = []
    for row in log_rows:
        current = row["current"]
        if not current:
            continue
        pos_index = bisect.bisect_right(trade_days, row["day"]) - 1
        positions = state["daily_positions"][trade_days[pos_index]] if pos_index >= 0 else {}
        position = positions.get(current)
        if not position:
            continue
        days = entry_days.get(current, [])
        entry_index = bisect.bisect_right(days, row["day"]) - 1
        entry_day = days[entry_index] if entry_index >= 0 else row["day"]
        series = raw.get(current, {})
        all_dates = sorted(date for date in series if date <= row["day"])
        dates = [date for date in all_dates if entry_day <= date <= row["day"]]
        if not dates or not all_dates:
            continue
        close = series[dates[-1]]
        previous = series[all_dates[-2]] if len(all_dates) >= 2 else 0.0
        high = max(series[date] for date in dates)
        risk = None
        if previous > 0 and close / previous - 1.0 <= -0.04:
            risk = "DAILY_DROP"
        elif high > 0 and close / high - 1.0 <= -0.05:
            risk = "DRAWDOWN"
        elif position.get("avg_entry_cost", 0) > 0 and close / position["avg_entry_cost"] - 1.0 >= 0.12:
            risk = "TAKE_PROFIT"
        ptrade_risk = None
        reason = str(row["reason"])
        if reason.startswith("RISK_DAILY_DROP"):
            ptrade_risk = "DAILY_DROP"
        elif reason.startswith("RISK_DRAWDOWN"):
            ptrade_risk = "DRAWDOWN"
        elif reason.startswith("RISK_TAKE_PROFIT"):
            ptrade_risk = "TAKE_PROFIT"
        comparisons.append({"day": row["day"], "current": current, "entry_day": entry_day,
                            "qmt_risk": risk, "ptrade_risk": ptrade_risk,
                            "reason": row["reason"], "close": close,
                            "avg_entry_cost": position.get("avg_entry_cost")})

    comparable = [item for item in comparisons if item["ptrade_risk"] or item["qmt_risk"]]
    matches = sum(item["qmt_risk"] == item["ptrade_risk"] for item in comparable)
    artifact = {
        "schema_version": 1, "kind": "qmt_v1_1_15_risk_replay_parity",
        "created_at": datetime.now().astimezone().isoformat(), "orders_enabled": False,
        "state_replay": str(args.state), "ptrade_log": str(args.ptrade_log),
        "errors": errors, "comparable_days": len(comparable), "risk_matches": matches,
        "risk_mismatches": len(comparable) - matches,
        "first_mismatches": [item for item in comparable if item["qmt_risk"] != item["ptrade_risk"]][:25],
        "comparisons": comparisons,
    }
    output = ROOT / "runtime_data" / "evidence" / "simulation" / (
        "qmt_v1_1_15_risk_replay_parity_%s.json" % datetime.now().strftime("%Y%m%d_%H%M%S"))
    output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), "errors": errors, "comparable_days": len(comparable),
                      "risk_matches": matches, "risk_mismatches": len(comparable) - matches,
                      "first_mismatches": artifact["first_mismatches"][:3]}, ensure_ascii=False, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
