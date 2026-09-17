import json
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

from scripts.coordinator import serve
from scripts.coordinator.serve import Handler, HOSTS
from kitling_bigqmt.host_agent_client import HostAgentClient


def test_readonly_bootstrap_accepts_heartbeat_and_lists_host():
    HOSTS.clear()
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        conn = HTTPConnection(*server.server_address)
        body = {"schema_version": 1, "host_id": "host-105", "state": "HEALTHY_READONLY",
                "sent_at": "2026-09-14T08:00:00+00:00", "services": {"qmt": "UP"}, "accounts": ["90000001"]}
        conn.request("POST", "/api/v1/hosts/heartbeat", json.dumps(body), {"Content-Type": "application/json"})
        assert conn.getresponse().status == 202
        conn.request("GET", "/api/v1/hosts")
        response = conn.getresponse()
        assert response.status == 200
        host = json.loads(response.read())["hosts"][0]
        assert host["host_id"] == "host-105"
        assert host["profiles"]["90000001"]["services"]["qmt"] == "UP"
    finally:
        server.shutdown()


def test_coordinator_root_is_readonly_dashboard():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        conn = HTTPConnection(*server.server_address)
        conn.request("GET", "/")
        response = conn.getresponse()
        body = response.read().decode("utf-8")
        assert response.status == 200
        assert "BigQMT Coordinator" in body
        assert "订单控制未开放" in body
    finally:
        server.shutdown()


def test_executor_preview_is_readonly_and_filters_formal_account():
    HOSTS.clear()
    HOSTS["host-105"] = {
        "host_id": "host-105", "profiles": {
            "90000001": {"sent_at": "2999-01-01T00:00:00+00:00",
                          "services": {"qmt": "UP", "redis": "UP", "bridge": "UP", "tray": "UP"}},
            "90000002": {"sent_at": "2999-01-01T00:00:00+00:00",
                          "services": {"qmt": "UP", "redis": "UP", "bridge": "UP", "tray": "UP"}},
        },
    }
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        conn = HTTPConnection(*server.server_address)
        conn.request("GET", "/api/v1/executor-preview")
        payload = json.loads(conn.getresponse().read())
        simulation, formal = payload["accounts"]
        assert simulation["lease_state"] == "UNASSIGNED_READONLY"
        assert simulation["candidates"][0]["eligible"] is True
        assert formal["candidates"][0]["eligible"] is False
        assert formal["control"] == "PREVIEW_ONLY_NO_LEASE_WRITE"
    finally:
        server.shutdown()


def test_executor_preview_projects_existing_lease_without_writing_new_one(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGQMT_COORDINATOR_DB", str(tmp_path / "coordinator.sqlite3"))
    store = serve.coordinator_store()
    lease = store.grant_lease("90000001", "host-105", ttl_seconds=60)
    payload = serve.executor_preview()
    simulation = payload["accounts"][0]
    assert simulation["lease_state"] == "ACTIVE"
    assert simulation["current_executor"] == "host-105"
    assert simulation["fencing_token"] == lease.token


def test_host_agent_intent_preview_is_empty_readonly_get_only():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        preview = HostAgentClient(f"http://{host}:{port}", "host-105").readonly_intent_preview("90000001")
        assert preview.intents == ()
        assert preview.orders_enabled is False
        conn = HTTPConnection(host, port)
        conn.request("GET", "/api/v1/host-agent/intents?account_id=bad&host_id=host-105")
        assert conn.getresponse().status == 400
    finally:
        server.shutdown()


def test_intent_preview_status_is_aggregate_readonly_and_never_exposes_intents():
    HOSTS.clear()
    HOSTS["host-105"] = {"host_id": "host-105", "profiles": {"90000001": {}, "90000002": {}}}
    code, payload = serve.response_payload("/api/v1/host-agent/intent-preview-status")
    assert code == 200
    assert payload["readonly"] is True
    assert payload["orders_enabled"] is False
    assert [(item["host_id"], item["account_id"], item["intent_count"]) for item in payload["targets"]] == [
        ("host-105", "90000001", 0), ("host-105", "90000002", 0)
    ]
    assert "intents" not in payload


def test_load_progress_scans_only_top_level_status_key():
    snapshot = serve.load_progress()
    assert snapshot["phase"].startswith("M03_")
    assert snapshot["phase"] is not None and snapshot["phase"] != "NOT_STARTED"
    assert snapshot["overall_verified_percent"] == 30
    assert snapshot["updated_at"].startswith("2026-") and snapshot["updated_at"].endswith("+08:00")


def test_progress_endpoint_is_readonly_snapshot():
    code, payload = serve.response_payload("/api/v1/progress")
    assert code == 200
    assert payload["readonly"] is True
    assert payload["orders_enabled"] is False
    assert payload["phase"].startswith("M03_")
    assert payload["overall_verified_percent"] == 30


def test_fleet_endpoint_is_readonly_projection_no_intents():
    HOSTS.clear()
    HOSTS["host-105"] = {"host_id": "host-105", "profiles": {}}
    code, payload = serve.response_payload("/api/v1/fleet")
    assert code == 200
    assert payload["mode"] == "readonly-fleet"
    assert payload["readonly"] is True
    assert payload["orders_enabled"] is False
    assert payload["control"] == "READ_ONLY_FLEET_PROJECTION"
    assert isinstance(payload["hosts"], list)
    assert "executor_preview" in payload
    assert "intent_preview" in payload
    assert "progress" in payload
    assert "intents" not in payload


def test_bootstrap_does_not_expose_fact_ingest_or_any_order_write_route():
    for path in ("/api/v1/facts/ingest", "/api/v1/orders", "/api/v1/leases"):
        code, payload = serve.response_payload(path)
        assert code == 404
        assert payload["status"] == "not_found"
