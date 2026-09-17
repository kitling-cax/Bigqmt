import tempfile
from pathlib import Path

import pytest

from kitling_bigqmt.sleeve_accounting import SleeveAccounting, SleeveAccountingError
from kitling_bigqmt.state_store import RuntimeStateStore


def test_sleeves_compound_independently_and_reconcile_broker_totals():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        ledger = SleeveAccounting(RuntimeStateStore(root / "state.sqlite3", root / "audit"))
        assert ledger.register_sleeve("A", 100_000)["result"] == "REGISTERED"
        assert ledger.register_sleeve("B", 1_000_000)["result"] == "REGISTERED"
        ledger.record_fill({"fill_id": "a-buy", "strategy_id": "A", "stock_code": "510300.SH", "side": "BUY", "quantity": 1000, "price": 10, "fee": 5})
        ledger.record_fill({"fill_id": "b-buy", "strategy_id": "B", "stock_code": "510300.SH", "side": "BUY", "quantity": 5000, "price": 10, "fee": 10})
        a = ledger.summary("A", {"510300.SH": 11})
        b = ledger.summary("B", {"510300.SH": 11})
        assert a["cash"] == pytest.approx(89_995)
        assert a["net_asset_value"] == pytest.approx(100_995)
        assert a["return_rate"] == pytest.approx(0.00995)
        assert b["net_asset_value"] == pytest.approx(1_004_990)
        reconcile = ledger.reconcile_broker_positions({"510300.SH": 8000}, {"510300.SH": 2000})
        assert reconcile["status"] == "PASSED"


def test_sleeve_rejects_overspend_and_unowned_sell():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        ledger = SleeveAccounting(RuntimeStateStore(root / "state.sqlite3", root / "audit"))
        ledger.register_sleeve("A", 100)
        with pytest.raises(SleeveAccountingError, match="cash"):
            ledger.record_fill({"fill_id": "too-much", "strategy_id": "A", "stock_code": "510300.SH", "side": "BUY", "quantity": 100, "price": 2})
        with pytest.raises(SleeveAccountingError, match="strategy-owned"):
            ledger.record_fill({"fill_id": "bad-sell", "strategy_id": "A", "stock_code": "510300.SH", "side": "SELL", "quantity": 100, "price": 1})


def test_nav_snapshots_are_idempotent_and_queryable():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        ledger = SleeveAccounting(RuntimeStateStore(root / "state.sqlite3", root / "audit"))
        ledger.register_sleeve("A", 100_000)
        first = ledger.record_nav_snapshot("A", {}, "quote-run-1", "2026-09-09T10:00:00+08:00")
        duplicate = ledger.record_nav_snapshot("A", {}, "quote-run-1", "2026-09-09T10:00:00+08:00")
        second = ledger.record_nav_snapshot("A", {}, "quote-run-2", "2026-09-09T11:00:00+08:00")
        assert first["result"] == "RECORDED"
        assert duplicate["result"] == "DUPLICATE"
        assert second["result"] == "RECORDED"
        series = ledger.nav_series("A")
        assert [point["valuation_run_id"] for point in series] == ["quote-run-1", "quote-run-2"]
        assert series[-1]["net_asset_value"] == pytest.approx(100_000)


def test_benchmark_curve_is_rebased_to_the_independent_strategy_account():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        ledger = SleeveAccounting(RuntimeStateStore(root / "state.sqlite3", root / "audit"))
        ledger.register_sleeve("A", 100_000)
        first = ledger.record_benchmark_snapshot("A", "510300.SH", 4.0, "day-1", "2026-09-09T16:20:00+08:00")
        second = ledger.record_benchmark_snapshot("A", "510300.SH", 4.2, "day-2", "2026-09-10T16:20:00+08:00")
        assert first["net_asset_value"] == pytest.approx(100_000)
        assert second["net_asset_value"] == pytest.approx(105_000)
        assert second["return_rate"] == pytest.approx(0.05)
        series = ledger.benchmark_series("A", "510300.SH")
        assert len(series) == 2
        assert series[0]["benchmark_code"] == "510300.SH"
