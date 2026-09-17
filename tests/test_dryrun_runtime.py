import tempfile
from pathlib import Path

from kitling_bigqmt.dryrun_runtime import DryRunRuntime
from kitling_bigqmt.state_store import RuntimeStateStore


def _payload() -> dict:
    return {
        "request_id": "dryrun-runtime-001", "environment": "production", "orders_enabled": True,
        "strategy_id": "S10_D1_V1_1_15", "signal_id": "signal-001", "stock_code": "511010.SH",
        "side": "BUY", "quantity": 100, "limit_price": 100, "strategy_cash": 10000,
        "quote_admission": "ALLOWED", "preflight_admission": "ALLOWED", "parity_admission": "ALLOWED",
    }


def _status(preflight: str = "ALLOWED", parity: str = "ALLOWED") -> dict:
    return {"environment": "simulation", "orders_enabled": False,
            "dryrun_admission": {"preflight": preflight, "parity": parity}}


def test_runtime_blocks_forged_payload_when_project_parity_is_blocked():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        store = RuntimeStateStore(root / "state.sqlite3", root / "audit")
        result = DryRunRuntime(store, _status(parity="BLOCKED")).evaluate(_payload())
        assert result["result"] == "BLOCKED"
        assert "parity" in result["reason"]
        store.initialize()
        with store.session() as db:
            assert db.execute("SELECT COUNT(*) FROM dryrun_order_intents").fetchone()[0] == 0


def test_runtime_overrides_caller_environment_and_order_switch_but_keeps_local_only():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        store = RuntimeStateStore(root / "state.sqlite3", root / "audit")
        result = DryRunRuntime(store, _status()).evaluate(_payload())
        assert result["result"] == "RECORDED"
        with store.session() as db:
            payload = db.execute("SELECT payload_json FROM dryrun_order_intents").fetchone()[0]
        assert '"environment":"simulation"' in payload
        assert '"orders_enabled":false' in payload
