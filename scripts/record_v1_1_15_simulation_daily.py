"""Create one read-only v1.1.15 simulation daily operating record.

No order, cancel, runtime-control, or Redis write route is imported here.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kitling_bigqmt.daily_operations import reconcile_daily_positions  # noqa: E402
from kitling_bigqmt.fill_reconciliation import reconcile_attributable_trades  # noqa: E402
from kitling_bigqmt.etf_pool_benchmark import BENCHMARK_CODE, equal_weight_chain_point, load_pool  # noqa: E402
from kitling_bigqmt.market_data import normalize_daily_bars  # noqa: E402
from kitling_bigqmt.redis_resp import RedisRespClient  # noqa: E402
from kitling_bigqmt.readonly_rpc import ReadOnlyBigQmtClient  # noqa: E402
from kitling_bigqmt.sleeve_accounting import SleeveAccounting, SleeveAccountingError  # noqa: E402
from kitling_bigqmt.state_store import RuntimeStateStore  # noqa: E402
from kitling_bigqmt.machine_config import load_gateway  # noqa: E402

STRATEGY_ID = "S10_D1_U25_NO_ALCOHOL_5D_SIM_MAIN_V1_1_15"


def main() -> int:
    config = load_gateway(ROOT, "simulation")
    account_id = str(config.get("account_id") or "").strip()
    if config.get("environment") != "simulation" or not account_id:
        raise SystemExit("daily record requires a configured simulation account")
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    day = now.strftime("%Y%m%d")
    redis = RedisRespClient(**dict(config["redis"]))
    client = ReadOnlyBigQmtClient(redis, account_id, float(config.get("rpc_timeout_seconds", 12)))
    store = RuntimeStateStore(Path(config["state_db"]), Path(config["audit_dir"]))
    accounting = SleeveAccounting(store)
    attributable_trades_reply = client.trades()
    fill_reconciliation = reconcile_attributable_trades(
        accounting, STRATEGY_ID, list(attributable_trades_reply.get("data") or []),
    )
    positions_reply = client.positions()
    orders_reply = client.orders()
    trades_reply = client.trades()
    asset_reply = client.account_asset()
    ping_reply = client.ping()
    positions_data = positions_reply.get("data") or []
    if isinstance(positions_data, dict):
        # 0.3.26 bridge shape: dict keyed by stock_code
        positions = positions_data
    elif isinstance(positions_data, list):
        # 0.3.54+ bridge shape: list of position dicts, each with stock_code
        positions = {
            item["stock_code"]: item for item in positions_data
            if isinstance(item, dict) and item.get("stock_code")
        }
    else:
        positions = {}
    owned_quantities = accounting.position_quantities(STRATEGY_ID)
    ticks = client.full_tick(sorted(owned_quantities)) if owned_quantities else {"data": {}}
    prices = {
        code: float(((ticks.get("data") or {}).get(code) or {}).get("lastPrice") or 0)
        for code in owned_quantities
    }
    sleeve_rows = accounting.summary(STRATEGY_ID, prices)
    # The closing report has one stable valuation identity per local trading
    # day.  A retry must retain the first durable close point rather than
    # failing because its wall-clock timestamp or last quote changed.
    nav_run_id = "daily_%s_close" % day
    try:
        nav = accounting.record_nav_snapshot(
            STRATEGY_ID, prices, nav_run_id, "%sT16:20:00+08:00" % now.strftime("%Y-%m-%d"),
        )
    except SleeveAccountingError:
        existing = next((row for row in accounting.nav_series(STRATEGY_ID, limit=366)
                         if row.get("valuation_run_id") == nav_run_id), None)
        if existing is None:
            raise
        nav = {"result": "DUPLICATE_EXISTING", "valuation_run_id": nav_run_id,
               "snapshot_time": existing.get("snapshot_time")}
    benchmark: dict = {"status": "UNAVAILABLE"}
    try:
        pool_codes = load_pool(ROOT)
        existing_series = accounting.benchmark_series(STRATEGY_ID, BENCHMARK_CODE, 366)
        previous_price = float(existing_series[-1]["price"]) if existing_series else None
        point = equal_weight_chain_point(client, pool_codes, day, previous_price)
        try:
            benchmark = accounting.record_benchmark_snapshot(
                STRATEGY_ID, BENCHMARK_CODE, float(point["price"]), nav_run_id,
                "%sT16:20:00+08:00" % now.strftime("%Y-%m-%d"),
            )
        except SleeveAccountingError:
            existing_benchmark = next((row for row in accounting.benchmark_series(STRATEGY_ID, BENCHMARK_CODE, 366)
                                       if row.get("valuation_run_id") == nav_run_id), None)
            if existing_benchmark is None:
                raise
            benchmark = {"result": "DUPLICATE_EXISTING", **existing_benchmark}
        benchmark.update({"status": "RECORDED", "benchmark_name": point["benchmark_name"],
                          "constituent_count": point["constituent_count"],
                          "mean_return": point["mean_return"]})
    except Exception as exc:
        benchmark = {"status": "UNAVAILABLE", "reason": "%s: %s" % (type(exc).__name__, exc)}
    baseline = json.loads((ROOT / "runtime_data" / "baselines" / ("simulation_%s_external_positions.json" % account_id)).read_text(encoding="utf-8"))
    broker = {code: int((row or {}).get("volume") or 0) for code, row in positions.items()}
    owned = owned_quantities
    reconciliation = reconcile_daily_positions(broker, dict(baseline.get("positions") or {}), owned)
    shadow = next((row for row in store.latest_strategy_shadow_events(20) if row.get("strategy_id") == STRATEGY_ID), None)
    control_path = ROOT / "runtime_data" / "control" / "simulation" / "runtime_control.json"
    control = json.loads(control_path.read_text(encoding="utf-8")) if control_path.is_file() else {}
    report = {
        "schema_version": 1,
        "kind": "v1_1_15_simulation_daily_operations",
        "recorded_at": now.isoformat(),
        "trading_day": day,
        "account_id": account_id,
        "strategy_id": STRATEGY_ID,
        "bridge": ping_reply.get("data"),
        "account": asset_reply.get("data"),
        "broker_order_count": len(orders_reply.get("data") or []),
        "broker_trade_count": len(trades_reply.get("data") or []),
        "fill_reconciliation": fill_reconciliation,
        "latest_close_signal": shadow,
        "sleeve": sleeve_rows,
        "nav_snapshot": nav,
        "benchmark": benchmark,
        "reconciliation": reconciliation,
        "runtime_order_lock": {
            "mode": control.get("mode"),
            "orders_enabled": control.get("orders_enabled"),
            "execution_consumer_enabled": control.get("execution_consumer_enabled"),
        },
        "broker_call_made": False,
    }
    destination = ROOT / "runtime_data" / "evidence" / "simulation" / "daily_operations"
    destination.mkdir(parents=True, exist_ok=True)
    path = destination / ("v1_1_15_daily_%s_%s.json" % (day, now.strftime("%H%M%S")))
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": reconciliation["status"], "evidence": str(path), "nav": sleeve_rows["net_asset_value"], "orders_enabled": False}, ensure_ascii=False, indent=2))
    return 0 if reconciliation["status"] == "PASSED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
