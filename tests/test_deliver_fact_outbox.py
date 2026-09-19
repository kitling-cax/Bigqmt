import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from kitling_bigqmt.coordinator_outbox import LocalOutbox
from scripts.host_agent.deliver_fact_outbox import main


class _Handler(BaseHTTPRequestHandler):
    response = {"status": "ACCEPTED", "accepted": ["event-1"], "duplicates": [], "facts_only": True}

    def do_POST(self):  # noqa: N802
        length = int(self.headers["Content-Length"])
        json.loads(self.rfile.read(length))
        body = json.dumps(self.response).encode("utf-8")
        self.send_response(202)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        return


def test_delivery_refuses_non_shadow_without_explicit_flag(tmp_path, capsys):
    rc = main([
        "--profile", "simulation", "--secret-file", str(tmp_path / "missing.json"),
        "--outbox-path", str(tmp_path / "outbox.sqlite3"),
        "--endpoint", "http://127.0.0.1:18443/api/v1/facts/ingest",
    ])
    assert rc == 2
    assert "REFUSED_NON_SHADOW_ENDPOINT" in capsys.readouterr().out


def test_delivery_acks_only_coordinator_ids(tmp_path, monkeypatch, capsys):
    outbox = LocalOutbox(tmp_path / "outbox.sqlite3")
    outbox.enqueue("STRATEGY_RUNTIME", {"event_id": "event-1", "account_id": "90000001", "strategy_id": "s", "state": "RUNNING"})
    secret = tmp_path / "secret.json"
    secret.write_text(json.dumps({"schema_version": 1, "hosts": [{"host_id": "host-105", "key_id": "key-1", "status": "ACTIVE", "secret_b64": "dGVzdC1zZWNyZXQta2V5LWxvbmc="}]}), encoding="utf-8")
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        # Use a fake host identity with a sufficiently long decoded secret.
        secret.write_text(json.dumps({"schema_version": 1, "hosts": [{"host_id": "host-105", "key_id": "key-1", "status": "ACTIVE", "secret_b64": "QUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUE="}]}), encoding="utf-8")
        rc = main([
            "--profile", "simulation", "--secret-file", str(secret), "--outbox-path", str(tmp_path / "outbox.sqlite3"),
            "--endpoint", f"http://127.0.0.1:{server.server_address[1]}/api/v1/facts/ingest",
            "--allow-non-shadow",
        ])
    finally:
        server.shutdown()
    assert rc == 0
    assert outbox.pending() == []
    assert '"facts_only": true' in capsys.readouterr().out


def test_delivery_transport_failure_keeps_pending(tmp_path, capsys):
    outbox = LocalOutbox(tmp_path / "outbox.sqlite3")
    outbox.enqueue("STRATEGY_RUNTIME", {"event_id": "event-1", "account_id": "90000001", "strategy_id": "s", "state": "RUNNING"})
    secret = tmp_path / "secret.json"
    secret.write_text(json.dumps({"schema_version": 1, "hosts": [{"host_id": "host-105", "key_id": "key-1", "status": "ACTIVE", "secret_b64": "QUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUE="}]}), encoding="utf-8")
    rc = main([
        "--profile", "simulation", "--secret-file", str(secret), "--outbox-path", str(tmp_path / "outbox.sqlite3"),
        "--endpoint", "http://127.0.0.1:1/api/v1/facts/ingest", "--allow-non-shadow", "--timeout", "0.2",
    ])
    assert rc == 1
    assert len(outbox.pending()) == 1
    assert outbox.pending()[0]["attempts"] == 1
    assert '"status": "RETRY_PENDING"' in capsys.readouterr().out


def test_delivery_blocks_fact_secret_host_mismatch_before_network(tmp_path, capsys):
    outbox = LocalOutbox(tmp_path / "outbox.sqlite3")
    outbox.enqueue("STRATEGY_RUNTIME", {"event_id": "event-1", "account_id": "90000001", "strategy_id": "s", "state": "RUNNING"})
    secret = tmp_path / "secret.json"
    secret.write_text(json.dumps({"schema_version": 1, "hosts": [{
        "host_id": "host-placeholder", "key_id": "key-1", "status": "ACTIVE",
        "secret_b64": "QUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUE="
    }]}), encoding="utf-8")
    rc = main([
        "--profile", "simulation", "--secret-file", str(secret),
        "--outbox-path", str(tmp_path / "outbox.sqlite3"),
        "--expected-host-id", "host-real",
        "--endpoint", "http://127.0.0.1:1/api/v1/facts/ingest",
        "--allow-non-shadow",
    ])
    assert rc == 3
    assert len(outbox.pending()) == 1
    assert "FACT_HOST_ID_MISMATCH" in capsys.readouterr().out
