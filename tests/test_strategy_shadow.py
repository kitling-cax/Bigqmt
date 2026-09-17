from pathlib import Path

import pytest

from kitling_bigqmt.state_store import IdempotencyConflict, RuntimeStateStore
from kitling_bigqmt.strategy_shadow import ShadowStateError, build_close_shadow_event


def _market():
    return {
        "518880.SS": {
            "adjusted": [100.0 + index * 0.2 for index in range(25)],
            "raw": [100.0, 101.0],
        },
        "511880.SS": {"adjusted": [], "raw": [100.0, 100.0]},
    }


def test_close_shadow_is_non_broker_and_carries_pending_state():
    first = build_close_shadow_event("S", "20260908", _market(), source_baseline_sha256="abc")
    assert first["orders_enabled"] is False
    assert first["broker_call_made"] is False
    assert first["signal"]["desired_qmt"] == "518880.SH"
    second = build_close_shadow_event("S", "20260909", _market(), first["state_after"], "20260908", "front", "abc")
    assert second["virtual_transition"]["to"] == "518880.SS"
    assert second["execution_intent"] == "NONE_CLOSE_SIGNAL_ONLY"


def test_close_shadow_rejects_same_or_earlier_day():
    with pytest.raises(ShadowStateError, match="after prior"):
        build_close_shadow_event("S", "20260908", _market(), prior_signal_day="20260908")


def test_shadow_events_are_idempotent_and_conflict_on_rewrite(tmp_path: Path):
    store = RuntimeStateStore(tmp_path / "state.sqlite3", tmp_path / "audit")
    event = build_close_shadow_event("S", "20260908", _market())
    assert store.record_strategy_shadow_event(event)["result"] == "RECORDED"
    assert store.record_strategy_shadow_event(event)["result"] == "DUPLICATE"
    changed = dict(event)
    changed["signal"] = dict(event["signal"], reason="CHANGED")
    with pytest.raises(IdempotencyConflict):
        store.record_strategy_shadow_event(changed)
    assert store.latest_strategy_shadow_events()[0]["event_id"] == event["event_id"]
