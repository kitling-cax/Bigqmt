"""Run one no-order v1.1.15 QMT close-shadow cycle.

The cycle fetches completed daily bars through the read-only QMT bridge,
persists a deterministic local shadow signal, publishes an informational Redis
event, and records a zero-position sleeve valuation.  It never creates a QMT
order, a broker fill, or an executable order intent.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kitling_bigqmt.market_data import normalize_daily_bars  # noqa: E402
from kitling_bigqmt.readonly_rpc import ReadOnlyBigQmtClient  # noqa: E402
from kitling_bigqmt.redis_resp import RedisRespClient  # noqa: E402
from kitling_bigqmt.sleeve_accounting import SleeveAccounting  # noqa: E402
from kitling_bigqmt.state_store import RuntimeStateStore  # noqa: E402
from kitling_bigqmt.strategy_shadow import ShadowStateError, build_close_shadow_event  # noqa: E402
from kitling_bigqmt.v1_1_15_reproduction import FALLBACK_PTRADE, UNIVERSE_PTRADE, ptrade_to_qmt  # noqa: E402
from kitling_bigqmt.machine_config import load_gateway  # noqa: E402


def _positive_series(bars: list[Any]) -> dict[str, float]:
    return {bar.trade_date: float(bar.close) for bar in bars if bar.close is not None and float(bar.close) > 0}


def _completed_day(dates: list[str], requested: str | None, now: datetime) -> str:
    if not dates:
        raise ShadowStateError("no daily bars returned")
    if requested:
        normalized = requested.replace("-", "")
        if normalized not in dates:
            raise ShadowStateError("requested as-of date is unavailable")
        return normalized
    local = now.astimezone(ZoneInfo("Asia/Shanghai"))
    today = local.strftime("%Y%m%d")
    cutoff = time(15, 30)
    completed = [day for day in dates if day < today or (day == today and local.time() >= cutoff)]
    if not completed:
        raise ShadowStateError("no completed daily bar is available before close cutoff")
    return completed[-1]


def _publish(redis: RedisRespClient, environment: str, event: dict[str, Any]) -> dict[str, Any]:
    strategy_id = str(event["strategy_id"])
    base = "bigqmt:%s:strategy_shadow:%s" % (environment, strategy_id)
    payload = json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    stream_id = redis.command("XADD", base + ":stream", "*", "event_id", event["event_id"],
                              "signal_day", event["signal_day"], "payload", payload)
    redis.command("SET", base + ":latest", payload)
    return {"status": "PUBLISHED", "stream": base + ":stream", "stream_id": stream_id,
            "latest_key": base + ":latest"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Persist one v1.1.15 completed-bar close shadow without orders.")
    parser.add_argument("--as-of", help="completed signal date YYYYMMDD; default observes the 15:30 close cutoff")
    parser.add_argument("--history-start", default="20260101", help="warm-up date for the 25 completed bars")
    parser.add_argument("--end", default=datetime.now().strftime("%Y%m%d"))
    parser.add_argument("--adjustment", choices=("front", "back", "none"), default="front")
    parser.add_argument("--config", default=None)
    parser.add_argument("--no-redis-publish", action="store_true", help="persist local evidence only")
    args = parser.parse_args()

    config = load_gateway(ROOT, "simulation") if args.config is None else json.loads(Path(args.config).read_text(encoding="utf-8"))
    if str(config.get("environment")) != "simulation":
        raise SystemExit("close shadow is simulation-only")
    manifest_path = ROOT / "strategy_baselines" / "s10_d1_v1_1_15_ptrade.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    strategy_id = str(manifest["strategy_id"])
    store = RuntimeStateStore(Path(config["state_db"]), Path(config["audit_dir"]))

    all_prior = store.latest_strategy_shadow_events(limit=50)
    if args.as_of:
        requested = args.as_of.replace("-", "")
        existing = next((item for item in all_prior if item.get("strategy_id") == strategy_id
                         and item.get("signal_day") == requested), None)
        if existing is not None:
            print(json.dumps({"result": "DUPLICATE", "event_id": existing.get("event_id"),
                              "signal_day": requested, "orders_enabled": False,
                              "broker_call_made": False, "execution_intent": "NONE_CLOSE_SIGNAL_ONLY"},
                             ensure_ascii=False, indent=2))
            return 0

    client = ReadOnlyBigQmtClient(
        RedisRespClient(**dict(config["redis"])), str(config["account_id"]),
        timeout_seconds=float(config.get("rpc_timeout_seconds", 12)),
    )
    adjusted: dict[str, dict[str, float]] = {}
    raw: dict[str, dict[str, float]] = {}
    errors = []
    for ptrade_code in list(UNIVERSE_PTRADE) + [FALLBACK_PTRADE]:
        qmt_code = ptrade_to_qmt(ptrade_code)
        try:
            client.download_history_data(qmt_code, "1d", args.history_start, args.end)
            adjusted[ptrade_code] = _positive_series(normalize_daily_bars(
                client.market_data_ex([qmt_code], ["close", "time"], "1d", args.history_start, args.end, -1,
                                      args.adjustment), qmt_code))
            raw[ptrade_code] = _positive_series(normalize_daily_bars(
                client.market_data_ex([qmt_code], ["close", "time"], "1d", args.history_start, args.end, -1,
                                      "none"), qmt_code))
        except Exception as exc:
            errors.append({"ptrade_code": ptrade_code, "qmt_code": qmt_code,
                           "type": type(exc).__name__, "message": str(exc)})

    evidence_dir = ROOT / "runtime_data" / "evidence" / "simulation" / "strategy_shadow"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if errors:
        blocked = {
            "schema_version": 1, "kind": "v1_1_15_qmt_close_shadow", "status": "BLOCKED_INCOMPLETE_QMT_UNIVERSE",
            "created_at": datetime.now().astimezone().isoformat(), "strategy_id": strategy_id,
            "orders_enabled": False, "broker_call_made": False, "execution_intent": "NONE",
            "errors": errors,
        }
        output = evidence_dir / ("v1_1_15_close_shadow_blocked_%s.json" % stamp)
        output.write_text(json.dumps(blocked, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"result": "BLOCKED", "output": str(output), "errors": errors,
                          "orders_enabled": False, "broker_call_made": False}, ensure_ascii=False, indent=2))
        return 2

    available_dates = sorted({day for values in adjusted.values() for day in values})
    signal_day = _completed_day(available_dates, args.as_of, datetime.now().astimezone())
    existing = next((item for item in all_prior if item.get("strategy_id") == strategy_id
                     and item.get("signal_day") == signal_day), None)
    if existing is not None:
        print(json.dumps({"result": "DUPLICATE", "event_id": existing.get("event_id"), "signal_day": signal_day,
                          "orders_enabled": False, "broker_call_made": False,
                          "execution_intent": "NONE_CLOSE_SIGNAL_ONLY"}, ensure_ascii=False, indent=2))
        return 0
    prior = next((item for item in all_prior if item.get("strategy_id") == strategy_id), None)
    market = {
        code: {
            "adjusted": [value for day, value in adjusted.get(code, {}).items() if day <= signal_day],
            "raw": [value for day, value in raw.get(code, {}).items() if day <= signal_day],
        }
        for code in list(UNIVERSE_PTRADE) + [FALLBACK_PTRADE]
    }
    event = build_close_shadow_event(
        strategy_id=strategy_id, signal_day=signal_day, market=market,
        prior_state=(prior or {}).get("state_after"), prior_signal_day=(prior or {}).get("signal_day"),
        adjustment_mode=args.adjustment, source_baseline_sha256=str(manifest["source"]["sha256"]),
    )
    event.update({
        "created_at": datetime.now().astimezone().isoformat(),
        "environment": "simulation", "history_start": args.history_start, "history_end": args.end,
        "bar_coverage": {code: len(values) for code, values in adjusted.items()},
    })
    result = store.record_strategy_shadow_event(event)
    sleeve = SleeveAccounting(store)
    sleeve_registration = sleeve.register_sleeve(strategy_id, float(manifest["capital_and_costs"]["sleeve_initial_capital"]))
    nav = sleeve.record_nav_snapshot(strategy_id, {}, "shadow:" + event["event_id"], event["created_at"])
    publication = {"status": "NOT_REQUESTED"}
    if not args.no_redis_publish:
        try:
            publication = _publish(RedisRespClient(**dict(config["redis"])), "simulation", event)
        except Exception as exc:
            publication = {"status": "LOCAL_PERSISTED_REDIS_UNAVAILABLE", "type": type(exc).__name__,
                           "message": str(exc)}
    artifact = {"status": "RECORDED_SHADOW_PROVISIONAL_ADJUSTMENT", "event": event, "state_store": result,
                "sleeve_registration": sleeve_registration, "sleeve_nav": nav, "redis_publication": publication,
                "orders_enabled": False, "broker_call_made": False}
    output = evidence_dir / ("v1_1_15_close_shadow_%s_%s.json" % (signal_day, stamp))
    output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"result": result["result"], "output": str(output), "event_id": event["event_id"],
                      "signal_day": signal_day, "desired_qmt": event["signal"]["desired_qmt"],
                      "reason": event["signal"]["reason"], "redis_publication": publication,
                      "orders_enabled": False, "broker_call_made": False,
                      "execution_intent": "NONE_CLOSE_SIGNAL_ONLY"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
