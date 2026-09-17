import pytest
import json
from http.client import HTTPConnection
import threading
from http.server import ThreadingHTTPServer

from kitling_bigqmt.coordinator_fact_auth import (
    FactAuthenticationError,
    TrustedFactHost,
    build_signed_fact_envelope,
    verify_signed_fact_envelope,
)
from kitling_bigqmt.coordinator_fact_ingress import CoordinatorFactIngress
from kitling_bigqmt.coordinator_outbox import LocalOutbox
from scripts.coordinator.serve import Handler
from kitling_bigqmt.host_fact_identity import credential_document, generate_credential


SECRET = b"test-secret-not-a-real-release-key"
TRUSTED = {"host-105-fact-v1": TrustedFactHost("host-105", "host-105-fact-v1", SECRET)}


def fact_event(event_id="11111111-1111-4111-8111-111111111111"):
    return {"event_id": event_id, "event_type": "STRATEGY_RUNTIME", "payload": {
        "event_id": event_id, "account_id": "90000001", "strategy_id": "s", "state": "RUNNING"
    }}


def test_signed_envelope_verifies_only_for_expected_host_and_body():
    envelope = build_signed_fact_envelope("host-105", "host-105-fact-v1", SECRET, {"events": [fact_event()]}, now_epoch=100, request_id="22222222-2222-4222-8222-222222222222")
    assert verify_signed_fact_envelope(envelope, TRUSTED, now_epoch=110).host_id == "host-105"
    changed = {**envelope, "body": {"events": []}}
    with pytest.raises(FactAuthenticationError, match="body hash"):
        verify_signed_fact_envelope(changed, TRUSTED, now_epoch=110)
    with pytest.raises(FactAuthenticationError, match="expired"):
        verify_signed_fact_envelope(envelope, TRUSTED, now_epoch=161)


def test_authenticated_ingress_deduplicates_event_and_rejects_replayed_request(tmp_path):
    ingress = CoordinatorFactIngress(tmp_path / "coordinator.sqlite3", TRUSTED)
    envelope = build_signed_fact_envelope("host-105", "host-105-fact-v1", SECRET, {"events": [fact_event()]}, now_epoch=100, request_id="22222222-2222-4222-8222-222222222222")
    assert ingress.ingest_signed(envelope, now_epoch=110)["status"] == "ACCEPTED"
    assert ingress.ingest_signed(envelope, now_epoch=110)["status"] == "REPLAYED"
    another = build_signed_fact_envelope("host-105", "host-105-fact-v1", SECRET, {"events": [fact_event("33333333-3333-4333-8333-333333333333")]}, now_epoch=100, request_id="22222222-2222-4222-8222-222222222222")
    with pytest.raises(FactAuthenticationError, match="different body"):
        ingress.ingest_signed(another, now_epoch=110)


def test_outbox_payload_can_be_wrapped_without_order_capability(tmp_path):
    outbox = LocalOutbox(tmp_path / "host.sqlite3")
    payload = {"event_id": "11111111-1111-4111-8111-111111111111", "account_id": "90000001", "strategy_id": "s", "state": "RUNNING"}
    outbox.enqueue("STRATEGY_RUNTIME", payload)
    envelope = build_signed_fact_envelope("host-105", "host-105-fact-v1", SECRET, {"events": outbox.pending()}, now_epoch=100)
    assert envelope["body"]["events"][0]["event_type"] == "STRATEGY_RUNTIME"
    assert "orders_enabled" not in envelope


def test_http_fact_route_is_opt_in_and_facts_only(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGQMT_FACT_INGEST_ENABLED", "1")
    credential = generate_credential("host-105", key_id="host-105-fact-v1")
    secret_file = tmp_path / "fact-identities.json"
    secret_file.write_text(json.dumps(credential_document([credential])), encoding="utf-8")
    monkeypatch.setenv("BIGQMT_FACT_TRUSTED_HOSTS_FILE", str(secret_file))
    monkeypatch.setenv("BIGQMT_COORDINATOR_DB", str(tmp_path / "coordinator.sqlite3"))
    envelope = build_signed_fact_envelope("host-105", "host-105-fact-v1", credential.secret, {"events": [fact_event()]}, now_epoch=__import__("time").time())
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        connection = HTTPConnection(*server.server_address)
        encoded = json.dumps(envelope).encode("utf-8")
        connection.request("POST", "/api/v1/facts/ingest", encoded, {"Content-Type": "application/json"})
        response = connection.getresponse()
        body = json.loads(response.read())
        assert response.status == 202
        assert body["status"] == "ACCEPTED"
        assert body["facts_only"] is True
        assert body["orders_enabled"] is False
    finally:
        server.shutdown()
