import pytest

from kitling_bigqmt.host_fact_uploader import FactDeliveryError, acknowledge_fact_batch, build_pending_envelope
from kitling_bigqmt.host_fact_identity import generate_credential
from kitling_bigqmt.coordinator_outbox import LocalOutbox


def test_uploader_builds_signed_batch_without_network_and_acks_only_server_ids(tmp_path):
    outbox = LocalOutbox(tmp_path / "host.sqlite3")
    outbox.enqueue("STRATEGY_RUNTIME", {"event_id": "event-1", "account_id": "90000001", "strategy_id": "s", "state": "RUNNING"})
    credential = generate_credential("host-105", key_id="host-105-fact-v1")
    envelope, event_ids = build_pending_envelope(outbox, credential, now_epoch=100)
    assert envelope["host_id"] == "host-105"
    assert event_ids == ("event-1",)
    assert outbox.pending()[0]["attempts"] == 0
    assert acknowledge_fact_batch(outbox, event_ids, {"status": "ACCEPTED", "accepted": [], "duplicates": []}) == 0
    assert len(outbox.pending()) == 1
    assert acknowledge_fact_batch(outbox, event_ids, {"status": "ACCEPTED", "accepted": ["event-1"], "duplicates": []}) == 1
    assert outbox.pending() == []


def test_uploader_rejects_ack_for_another_event_and_keeps_rejected_batch_pending(tmp_path):
    outbox = LocalOutbox(tmp_path / "host.sqlite3")
    outbox.enqueue("STRATEGY_RUNTIME", {"event_id": "event-1", "account_id": "90000001", "strategy_id": "s", "state": "RUNNING"})
    with pytest.raises(FactDeliveryError, match="not in this batch"):
        acknowledge_fact_batch(outbox, ("event-1",), {"status": "ACCEPTED", "accepted": ["event-evil"], "duplicates": []})
    assert len(outbox.pending()) == 1
    assert acknowledge_fact_batch(outbox, ("event-1",), {"status": "REJECTED"}) == 0
