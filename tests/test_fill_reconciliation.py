from pathlib import Path

import pytest

from kitling_bigqmt.fill_reconciliation import FillReconciliationBlocked, reconcile_attributable_trades
from kitling_bigqmt.sleeve_accounting import SleeveAccounting
from kitling_bigqmt.state_store import RuntimeStateStore


def _accounting(tmp_path: Path) -> SleeveAccounting:
    ledger = SleeveAccounting(RuntimeStateStore(tmp_path / "state.sqlite3", tmp_path / "audit"))
    ledger.register_sleeve("S", 100000)
    return ledger


def _trade():
    return {"strategy_name": "S", "trade_id": "T1", "stock_code": "160723.SZ", "action": "BUY",
            "volume": 100, "price": 2.36, "commission": 5, "traded_time": "1789093235"}


def _attribution(ledger: SleeveAccounting):
    return ledger.store.register_strategy_order_attribution({
        "strategy_id": "S", "account_id": "90000001", "user_order_id": "strategy-order-1",
        "order_sys_id": "365", "stock_code": "160723.SZ", "side": "BUY", "quantity": 100,
        "source_evidence": "test evidence",
    })


def test_attributable_trade_is_fill_driven_and_idempotent(tmp_path: Path):
    ledger = _accounting(tmp_path)
    assert reconcile_attributable_trades(ledger, "S", [_trade()])["recorded"] == 1
    assert reconcile_attributable_trades(ledger, "S", [_trade()])["duplicates"] == 1
    assert ledger.position_quantities("S") == {"160723.SZ": 100}


def test_bridge_named_trade_uses_durable_order_attribution(tmp_path: Path):
    ledger = _accounting(tmp_path)
    _attribution(ledger)
    split = [
        {**_trade(), "strategy_name": "BIGQMT_BRIDGE", "trade_id": "T1", "user_order_id": "strategy-order-1",
         "order_sys_id": "365", "volume": 60},
        {**_trade(), "strategy_name": "BIGQMT_BRIDGE", "trade_id": "T2", "user_order_id": "strategy-order-1",
         "order_sys_id": "365", "volume": 40},
    ]
    result = reconcile_attributable_trades(ledger, "S", split)
    assert result["recorded"] == 2
    assert result["ignored_unattributable_count"] == 0
    assert ledger.position_quantities("S") == {"160723.SZ": 100}


def test_unattributable_shared_account_trade_is_ignored(tmp_path: Path):
    result = reconcile_attributable_trades(
        _accounting(tmp_path), "S", [{**_trade(), "strategy_name": "manual"}],
    )
    assert result["attributable_trade_count"] == 0
    assert result["ignored_unattributable_count"] == 1


def test_bridge_trade_with_mapped_identity_but_changed_symbol_blocks(tmp_path: Path):
    ledger = _accounting(tmp_path)
    _attribution(ledger)
    row = {**_trade(), "strategy_name": "BIGQMT_BRIDGE", "user_order_id": "strategy-order-1",
           "order_sys_id": "365", "stock_code": "510300.SH"}
    with pytest.raises(FillReconciliationBlocked, match="conflict"):
        reconcile_attributable_trades(ledger, "S", [row])
