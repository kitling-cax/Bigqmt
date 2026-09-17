from pathlib import Path

import pytest

from kitling_bigqmt.state_store import IdempotencyConflict, RuntimeStateStore
from kitling_bigqmt.sleeve_accounting import SleeveAccounting


def _store(tmp_path: Path) -> RuntimeStateStore:
    store = RuntimeStateStore(tmp_path / "state.sqlite3", tmp_path / "audit")
    SleeveAccounting(store).register_sleeve("strategy-a", 100000)
    return store


def _attempt():
    return {
        "signal_id": "signal-20260914-buy-a", "strategy_id": "strategy-a", "account_id": "90000001",
        "signal_day": "20260911", "stock_code": "160723.SZ", "side": "BUY", "quantity": 100,
    }


def test_execution_claim_is_idempotent_and_finalization_is_one_way(tmp_path: Path):
    store = _store(tmp_path)
    claimed = store.claim_strategy_execution_attempt(_attempt())
    assert claimed["result"] == "CLAIMED"
    duplicate = store.claim_strategy_execution_attempt(_attempt())
    assert duplicate["result"] == "DUPLICATE"
    assert duplicate["state"] == "SUBMITTING"
    done = store.finish_strategy_execution_attempt("signal-20260914-buy-a", "SUBMITTED", {"order_id": "42"})
    assert done["state"] == "SUBMITTED"
    with pytest.raises(IdempotencyConflict):
        store.finish_strategy_execution_attempt("signal-20260914-buy-a", "SUBMITTED", {"order_id": "42"})


def test_execution_claim_rejects_same_identity_with_changed_payload(tmp_path: Path):
    store = _store(tmp_path)
    store.claim_strategy_execution_attempt(_attempt())
    changed = {**_attempt(), "quantity": 200}
    with pytest.raises(IdempotencyConflict):
        store.claim_strategy_execution_attempt(changed)
