from pathlib import Path

import pytest

from kitling_bigqmt.sleeve_accounting import SleeveAccounting
from kitling_bigqmt.state_store import IdempotencyConflict, RuntimeStateStore


def _store(tmp_path: Path) -> RuntimeStateStore:
    store = RuntimeStateStore(tmp_path / "state.sqlite3", tmp_path / "audit")
    SleeveAccounting(store).register_sleeve("strategy-a", 100000)
    return store


def _attribution():
    return {
        "strategy_id": "strategy-a", "account_id": "90000001", "user_order_id": "u-1",
        "order_sys_id": "365", "stock_code": "160723.SZ", "side": "BUY", "quantity": 100,
        "source_evidence": "evidence/test.json",
    }


def test_order_attribution_is_durable_and_idempotent(tmp_path: Path):
    store = _store(tmp_path)
    assert store.register_strategy_order_attribution(_attribution())["result"] == "RECORDED"
    assert store.register_strategy_order_attribution(_attribution())["result"] == "DUPLICATE"
    rows = store.strategy_order_attributions("strategy-a")
    assert rows[0]["user_order_id"] == "u-1"
    assert rows[0]["order_sys_id"] == "365"


def test_order_attribution_rejects_identity_reuse(tmp_path: Path):
    store = _store(tmp_path)
    store.register_strategy_order_attribution(_attribution())
    with pytest.raises(IdempotencyConflict):
        store.register_strategy_order_attribution({**_attribution(), "stock_code": "510300.SH"})
