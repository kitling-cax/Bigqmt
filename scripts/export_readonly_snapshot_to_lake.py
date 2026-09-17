"""Export an authoritative local QMT snapshot to Parquet data-lake files.

This script never contacts QMT/Redis and never creates an order.  It exports
facts already persisted by the read-only snapshot worker, plus local strategy
NAV points, into a dated immutable run directory.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kitling_bigqmt.sleeve_accounting import SleeveAccounting  # noqa: E402
from kitling_bigqmt.etf_pool_benchmark import BENCHMARK_CODE  # noqa: E402
from kitling_bigqmt.state_store import RuntimeStateStore  # noqa: E402
from kitling_bigqmt.machine_config import load_gateway, apply_data_lake_root  # noqa: E402


def _rows(mapping: object, run_id: str, environment: str, key_name: str = "stock_code") -> list[dict]:
    if isinstance(mapping, list):
        output = []
        for index, value in enumerate(mapping):
            row = dict(value or {}) if isinstance(value, dict) else {"value": value}
            row[key_name] = str(index)
            row["source_run_id"] = run_id
            row["environment"] = environment
            output.append(row)
        return output
    if not isinstance(mapping, dict):
        return []
    output = []
    for key, value in mapping.items():
        row = dict(value or {}) if isinstance(value, dict) else {"value": value}
        row[key_name] = str(key)
        row["source_run_id"] = run_id
        row["environment"] = environment
        output.append(row)
    return output


def _write(rows: list[dict], path: Path, columns: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(rows)
    if frame.empty and columns:
        frame = pd.DataFrame(columns=columns)
    frame.to_parquet(path, index=False, engine="pyarrow")


def main() -> int:
    parser = argparse.ArgumentParser(description="Export persisted read-only QMT facts to Parquet.")
    parser.add_argument("--profile", choices=("simulation", "production_readonly"), default="simulation")
    parser.add_argument("--config", type=Path, default=None, help="deprecated; --profile is now authoritative")
    parser.add_argument("--output-root", type=Path, default=None)
    args = parser.parse_args()
    if args.profile == "production_readonly" or (args.config is not None and "production" in args.config.name):
        profile = "production_readonly"
    else:
        profile = "simulation"
    config = load_gateway(ROOT, profile)
    state_db = Path(config["state_db"])
    audit_dir = Path(config.get("audit_dir") or ROOT / "runtime_data" / "audit")
    output_root = args.output_root or Path(apply_data_lake_root(ROOT, ""))
    store = RuntimeStateStore(state_db, audit_dir)
    latest = store.latest_snapshot_bundle()
    if latest is None:
        print(json.dumps({"status": "BLOCKED", "reason": "no persisted read-only snapshot"}, ensure_ascii=False))
        return 1
    run_id, bundle = latest
    environment = str(config.get("environment") or "unknown")
    trading_date = datetime.now().strftime("%Y-%m-%d")
    target = output_root / environment / trading_date / str(run_id)
    target.mkdir(parents=True, exist_ok=True)
    asset = dict((bundle.get("asset") or {}).get("data") or {})
    files = {}
    _write([{**asset, "source_run_id": run_id, "environment": environment}], target / "account_assets.parquet")
    files["account_assets"] = "account_assets.parquet"
    for dataset, bundle_key in (("broker_positions", "positions"), ("broker_orders", "orders"),
                                ("broker_trades", "trades"), ("qmt_quotes", "quotes")):
        rows = _rows((bundle.get(bundle_key) or {}).get("data") or {}, run_id, environment,
                     "stock_code" if dataset != "broker_trades" else "row_key")
        columns = ["row_key", "source_run_id", "environment"] if dataset in ("broker_orders", "broker_trades") else ["stock_code", "source_run_id", "environment"]
        _write(rows, target / (dataset + ".parquet"), columns)
        files[dataset] = dataset + ".parquet"
    ledger = SleeveAccounting(store)
    with store.session() as db:
        sleeve_ids = [str(row[0]) for row in db.execute(
            "SELECT strategy_id FROM strategy_sleeves ORDER BY strategy_id"
        ).fetchall()]
    nav_rows = []
    benchmark_rows = []
    for strategy_id in sleeve_ids:
        nav_rows.extend({**row, "strategy_id": strategy_id, "environment": environment}
                        for row in ledger.nav_series(strategy_id, limit=365))
        benchmark_rows.extend({**row, "strategy_id": strategy_id, "environment": environment}
                        for row in ledger.benchmark_series(strategy_id, BENCHMARK_CODE, limit=365))
    _write(nav_rows, target / "strategy_nav.parquet",
           ["strategy_id", "valuation_run_id", "snapshot_time", "net_asset_value", "cash", "frozen_cash",
            "market_value", "realized_pnl", "unrealized_pnl", "total_pnl", "return_rate", "environment"])
    files["strategy_nav"] = "strategy_nav.parquet"
    _write(benchmark_rows, target / "strategy_benchmark.parquet",
           ["strategy_id", "benchmark_code", "valuation_run_id", "snapshot_time", "price", "base_price",
            "net_asset_value", "return_rate", "environment"])
    files["strategy_benchmark"] = "strategy_benchmark.parquet"
    manifest = {
        "schema_version": 1,
        "status": "PASSED",
        "source": "sqlite_wal_readonly_snapshot",
        "environment": environment,
        "source_run_id": run_id,
        "trading_date": trading_date,
        "orders_enabled": False,
        "broker_order_count": len((bundle.get("orders") or {}).get("data") or []),
        "broker_trade_count": len((bundle.get("trades") or {}).get("data") or []),
        "files": files,
        "target": str(target),
    }
    (target / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
