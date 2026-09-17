import pytest

from kitling_bigqmt.coordinator_event_store import CoordinatorEventStore
from kitling_bigqmt.coordinator_outbox import LocalOutbox, OutboxError


def event(event_id="event-001", account_id="90000001"):
    return {
        "event_id": event_id, "account_id": account_id, "strategy_id": "S10_D1_U25_NO_ALCOHOL_5D_SIM_MAIN_V1_1_15",
        "event_time": "2026-09-16T11:00:00+00:00", "state": "RUNNING",
    }


def test_outbox_is_idempotent_and_never_acts_as_an_order_queue(tmp_path):
    outbox = LocalOutbox(tmp_path / "host.sqlite3")
    first = outbox.enqueue("STRATEGY_RUNTIME", event())
    again = outbox.enqueue("STRATEGY_RUNTIME", event())
    assert first["status"] == "QUEUED"
    assert again["status"] == "DUPLICATE"
    pending = outbox.pending()
    assert pending[0]["event_type"] == "STRATEGY_RUNTIME"
    assert "symbol" not in pending[0]["payload"]
    assert outbox.acknowledge(["event-001"]) == 1
    assert outbox.pending() == []


def test_outbox_rejects_sensitive_payload_or_changed_event_id(tmp_path):
    outbox = LocalOutbox(tmp_path / "host.sqlite3")
    outbox.enqueue("STRATEGY_RUNTIME", event())
    changed = event()
    changed["state"] = "PAUSED"
    with pytest.raises(OutboxError, match="collision"):
        outbox.enqueue("STRATEGY_RUNTIME", changed)
    with pytest.raises(OutboxError, match="sensitive"):
        outbox.enqueue("STRATEGY_RUNTIME", {**event("event-002"), "password": "never"})


def test_coordinator_fact_store_deduplicates_and_rejects_altered_replay(tmp_path):
    outbox = LocalOutbox(tmp_path / "host.sqlite3")
    outbox.enqueue("STRATEGY_RUNTIME", event())
    item = outbox.pending()[0]
    store = CoordinatorEventStore(tmp_path / "coordinator.sqlite3")
    result = store.ingest("host-105", [item], received_at="2026-09-16T11:01:00+00:00")
    assert result == {"accepted": ["event-001"], "duplicates": []}
    assert store.ingest("host-105", [item], received_at="2026-09-16T11:02:00+00:00")["duplicates"] == ["event-001"]
    altered = dict(item)
    altered["payload"] = {**item["payload"], "state": "DEGRADED"}
    with pytest.raises(OutboxError, match="hash mismatch|collision"):
        store.ingest("host-105", [altered], received_at="2026-09-16T11:03:00+00:00")
    assert store.count() == 1


def test_failure_tracking_keeps_event_pending(tmp_path):
    outbox = LocalOutbox(tmp_path / "host.sqlite3")
    outbox.enqueue("STRATEGY_RUNTIME", event())
    assert outbox.record_delivery_failure(["event-001"], "network timeout") == 1
    assert outbox.pending()[0]["attempts"] == 1
