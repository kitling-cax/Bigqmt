"""Rehearse one v1.1.15 simulation rotation without touching the broker.

Reads real sleeve facts from the local runtime state and replays the
production planning code for the sell leg and the follow-on buy leg.  It
never submits an order, never claims an execution attempt, and never writes
to the runtime state; the only output is a JSON report plus evidence.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kitling_bigqmt.machine_config import load_gateway  # noqa: E402
from kitling_bigqmt.readonly_rpc import ReadOnlyBigQmtClient  # noqa: E402
from kitling_bigqmt.redis_resp import RedisRespClient  # noqa: E402
from kitling_bigqmt.simulation_execution import ACCOUNT_ID, STRATEGY_ID  # noqa: E402
from kitling_bigqmt.sleeve_accounting import SleeveAccounting  # noqa: E402
from kitling_bigqmt.state_store import RuntimeStateStore  # noqa: E402
from kitling_bigqmt.switch_rehearsal import rehearse_switch  # noqa: E402

SHANGHAI = ZoneInfo("Asia/Shanghai")


def _parse_calendar(value: str) -> list[str]:
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--signal-day", required=True, help="completed-close day, YYYYMMDD")
    parser.add_argument("--trade-day", required=True, help="session that would execute, YYYYMMDD")
    parser.add_argument("--desired", required=True, help="target QMT code from that close signal")
    parser.add_argument("--live", action="store_true", help="read calendar and quotes from the running bridge (read-only)")
    parser.add_argument("--calendar", default="", help="comma-separated trading days when --live is not used")
    parser.add_argument("--sell-price", type=float, default=0.0, help="override quote for the held code")
    parser.add_argument("--buy-price", type=float, default=0.0, help="override quote for the target code")
    parser.add_argument("--at-time", default="09:36", help="intraday clock inside the bounded window")
    parser.add_argument(
        "--assume-trade-day-is-trading", action="store_true",
        help="QMT publishes the exchange calendar only up to today, so a pre-open rehearsal "
             "must state that the projected session is a trading day; the report records it",
    )
    parser.add_argument("--json-out", type=Path, default=None)
    parser.add_argument("--no-write", action="store_true", help="print only; write no evidence file")
    args = parser.parse_args()

    config = load_gateway(ROOT, "simulation")
    if config.get("environment") != "simulation" or str(config.get("account_id")) != ACCOUNT_ID:
        raise SystemExit("blocked: simulation account binding mismatch")
    store = RuntimeStateStore(Path(config["state_db"]), Path(config["audit_dir"]))
    accounting = SleeveAccounting(store)
    owned = accounting.position_quantities(STRATEGY_ID)
    fills = accounting.fill_records(STRATEGY_ID)

    ticks: dict[str, dict[str, float]] = {}
    calendar = _parse_calendar(args.calendar)
    if args.live:
        redis = RedisRespClient(**dict(config["redis"]))
        client = ReadOnlyBigQmtClient(redis, ACCOUNT_ID, float(config.get("rpc_timeout_seconds", 12)))
        codes = sorted(set(owned) | ({args.desired} if args.desired else set()))
        reply = client.full_tick(codes) if codes else {"data": {}}
        ticks = dict(reply.get("data") or {})
        calendar_reply = client.trading_dates("SH", "20260101", args.trade_day, -1)
        calendar = [str(day) for day in (calendar_reply.get("data") or [])]
    for code, price in ((next(iter(owned), ""), args.sell_price), (args.desired, args.buy_price)):
        code = str(code or "")
        if code and float(price) > 0:
            row = dict(ticks.get(code) or {})
            row["lastPrice"] = float(price)
            ticks[code] = row

    missing = [code for code in sorted(set(owned) | ({args.desired} if args.desired else set()))
               if not ticks.get(code)]
    if missing:
        raise SystemExit("no quote for %s; pass --live or --sell-price/--buy-price" % ",".join(missing))
    if not calendar:
        raise SystemExit("no trading calendar; pass --live or --calendar")

    calendar_source = "QMT" if args.live else "operator"
    projected = [str(day) for day in calendar]
    absent = [day for day in (args.signal_day, args.trade_day) if day not in projected]
    if absent and not args.assume_trade_day_is_trading:
        raise SystemExit(
            "calendar is missing %s (QMT only publishes up to today); "
            "pass --assume-trade-day-is-trading to rehearse a projected session" % ",".join(absent)
        )
    calendar = sorted(set(projected) | {args.signal_day, args.trade_day})

    prices = {code: float((ticks.get(code) or {}).get("lastPrice") or 0) for code in owned}
    sleeve = accounting.summary(STRATEGY_ID, prices)
    registry = json.loads((ROOT / "config" / "strategy_registry.json").read_text(encoding="utf-8"))
    registered = next((item for item in registry.get("strategies", []) if item.get("strategy_id") == STRATEGY_ID), None)
    if not registered:
        raise SystemExit("blocked: v1.1.15 strategy is not registered")

    report = rehearse_switch(
        sleeve_summary=sleeve,
        attributable_fills=fills,
        ticks=ticks,
        signal_day=args.signal_day,
        trade_day=args.trade_day,
        trading_days=calendar,
        activation_signal_not_before=str(registered["activation_policy"]["activation_signal_not_before"]),
        desired_qmt=args.desired,
        at_time=args.at_time,
        assume_trade_day_is_trading=args.assume_trade_day_is_trading,
    )
    report["sleeve"] = sleeve
    report["rehearsed_with"] = {
        "live_quotes": bool(args.live), "calendar_days": len(calendar), "calendar_source": calendar_source,
        "assumed_calendar_days": absent,
    }
    if not args.no_write:
        target = args.json_out or (
            ROOT / "runtime_data" / "evidence" / "simulation" / "switch_rehearsals"
            / ("switch_rehearsal_%s.json" % datetime.now(SHANGHAI).strftime("%Y%m%d_%H%M%S"))
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        report["evidence"] = str(target)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if str(report.get("verdict", "")).endswith("REHEARSED_OK") else 2


if __name__ == "__main__":
    raise SystemExit(main())
