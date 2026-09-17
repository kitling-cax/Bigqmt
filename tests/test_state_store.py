import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kitling_bigqmt.dryrun_orders import DryRunOrderPlanner, DryRunRejected
from kitling_bigqmt.state_store import IdempotencyConflict, RuntimeStateStore


class RuntimeStateStoreTests(unittest.TestCase):
    def test_record_snapshot_persists_authoritative_rows(self):
        bundle = {
            "ping": {"data": {"version": "test"}},
            "asset": {"data": {"cash": 1, "frozen_cash": 0, "market_value": 2, "total_asset": 3}},
            "positions": {"data": {"510300.SH": {"volume": 100, "available": 100, "cost": 4, "price": 5, "market_value": 500}}},
            "orders": {"data": []}, "trades": {"data": []},
            "quotes": {"data": {"510300.SH": {"timetag": "20260908 09:30:00", "lastPrice": 5}}},
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = RuntimeStateStore(root / "state.sqlite3", root / "audit")
            run_id = store.record_snapshot("simulation", "account", bundle)
            with store.session() as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM snapshot_runs").fetchone()[0], 1)
                self.assertEqual(db.execute("SELECT total_asset FROM account_assets WHERE run_id=?", (run_id,)).fetchone()[0], 3)
                self.assertEqual(db.execute("SELECT COUNT(*) FROM positions WHERE run_id=?", (run_id,)).fetchone()[0], 1)
                self.assertEqual(db.execute("SELECT COUNT(*) FROM quote_snapshots WHERE run_id=?", (run_id,)).fetchone()[0], 1)
                self.assertEqual(db.execute("SELECT COUNT(*) FROM quote_quality WHERE run_id=?", (run_id,)).fetchone()[0], 1)
            self.assertTrue(list((root / "audit").rglob("*.jsonl")))
            latest = store.latest_snapshot_bundle()
            self.assertEqual(latest[0], run_id)
            self.assertEqual(store.quote_freshness_summary()["samples"], 1)

    def test_dryrun_intent_is_idempotent_and_never_enables_orders(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            planner = DryRunOrderPlanner(RuntimeStateStore(root / "state.sqlite3", root / "audit"))
            payload = {
                "request_id": "intent-001", "environment": "simulation", "strategy_id": "S10_D1_V1_1_15",
                "signal_id": "signal-001", "stock_code": "511010.SH", "side": "BUY", "quantity": 100,
                "limit_price": 100, "estimated_fee": 5, "strategy_cash": 10005,
                "quote_admission": "ALLOWED", "preflight_admission": "ALLOWED", "parity_admission": "ALLOWED",
                "orders_enabled": False,
            }
            self.assertEqual("RECORDED", planner.plan(payload)["result"])
            self.assertEqual("DUPLICATE", planner.plan(payload)["result"])
            with self.assertRaises(IdempotencyConflict):
                planner.plan(dict(payload, quantity=200, strategy_cash=20005))
            with self.assertRaises(DryRunRejected):
                planner.plan(dict(payload, request_id="intent-002", orders_enabled=True))

    def test_dryrun_rejects_unadmitted_or_unfunded_intents(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            planner = DryRunOrderPlanner(RuntimeStateStore(root / "state.sqlite3", root / "audit"))
            payload = {
                "request_id": "intent-003", "environment": "simulation", "strategy_id": "S10_D1_V1_1_15",
                "signal_id": "signal-003", "stock_code": "511010.SH", "side": "BUY", "quantity": 100,
                "limit_price": 100, "strategy_cash": 9999, "quote_admission": "ALLOWED",
                "preflight_admission": "ALLOWED", "parity_admission": "ALLOWED", "orders_enabled": False,
            }
            with self.assertRaisesRegex(DryRunRejected, "sleeve cash"):
                planner.plan(payload)
            with self.assertRaisesRegex(DryRunRejected, "parity"):
                planner.plan(dict(payload, request_id="intent-004", strategy_cash=10000,
                                  parity_admission="BLOCKED"))

    def test_dryrun_sell_requires_strategy_and_broker_availability(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            planner = DryRunOrderPlanner(RuntimeStateStore(root / "state.sqlite3", root / "audit"))
            payload = {
                "request_id": "intent-005", "environment": "simulation", "strategy_id": "S10_D1_V1_1_15",
                "signal_id": "signal-005", "stock_code": "511010.SH", "side": "SELL", "quantity": 200,
                "limit_price": 100, "strategy_owned_quantity": 100, "broker_available_quantity": 200,
                "quote_admission": "ALLOWED", "preflight_admission": "ALLOWED", "parity_admission": "ALLOWED",
                "orders_enabled": False,
            }
            with self.assertRaisesRegex(DryRunRejected, "strategy-owned"):
                planner.plan(payload)
            with self.assertRaisesRegex(DryRunRejected, "broker available"):
                planner.plan(dict(payload, request_id="intent-006", strategy_owned_quantity=200,
                                  broker_available_quantity=100))


if __name__ == "__main__":
    unittest.main()
