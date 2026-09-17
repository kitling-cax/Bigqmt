import json
import subprocess
import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from kitling_bigqmt.host_agent_client import HostAgentClient
from kitling_bigqmt.host_agent_intent_preview import IntentPreviewRejected, parse_readonly_intent_preview
from scripts.coordinator.serve import Handler


ROOT = Path(__file__).resolve().parents[1]


def _run_probe(*arguments: str) -> dict:
    """Run the account-tray probe CLI and return its single JSON envelope."""
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "probe_host_agent_intent_preview.py"), *arguments],
        capture_output=True, text=True, timeout=120,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout.strip().splitlines()[-1])


def _payload(**changes):
    value = {
        "mode": "readonly-intent-preview", "readonly": True, "orders_enabled": False,
        "account_id": "90000001", "host_id": "192.0.2.105", "intents": [],
    }
    value.update(changes)
    return value


def test_empty_explicit_readonly_preview_is_accepted():
    preview = parse_readonly_intent_preview(
        _payload(), expected_account_id="90000001", expected_host_id="192.0.2.105"
    )
    assert preview.intents == ()
    assert preview.orders_enabled is False


@pytest.mark.parametrize("changes, expected", [
    ({"mode": "intent-execution"}, "unexpected"),
    ({"orders_enabled": True}, "explicitly read-only"),
    ({"host_id": "192.0.2.125"}, "host mismatch"),
    ({"intents": [{"symbol": "510300.SH"}]}, "must not contain"),
])
def test_preview_fails_closed_for_any_executable_or_mismatched_shape(changes, expected):
    with pytest.raises(IntentPreviewRejected, match=expected):
        parse_readonly_intent_preview(
            _payload(**changes), expected_account_id="90000001", expected_host_id="192.0.2.105"
        )


def test_client_uses_get_only_and_rejects_no_order_response_shape():
    seen = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(_payload()).encode("utf-8")

    def transport(request, timeout):
        seen["url"] = request.full_url
        seen["method"] = request.method
        seen["body"] = request.data
        return Response()

    preview = HostAgentClient("http://127.0.0.1:18443", "192.0.2.105", transport=transport).readonly_intent_preview("90000001")
    assert preview.orders_enabled is False
    assert seen["method"] == "GET"
    assert seen["body"] is None
    assert "/api/v1/host-agent/intents?" in seen["url"]


def test_probe_cli_reads_the_real_handler_envelope_as_readonly_and_empty():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        envelope = _run_probe(
            "--endpoint", "http://127.0.0.1:%d" % server.server_address[1],
            "--host-id", "host-105", "--account-id", "90000001", "--timeout", "5",
        )
    finally:
        server.shutdown()
    assert envelope["status"] == "passed"
    assert envelope["intent_count"] == 0
    assert envelope["readonly"] is True
    assert envelope["orders_enabled"] is False


def test_probe_cli_stays_fail_closed_when_the_coordinator_is_unreachable():
    envelope = _run_probe(
        "--endpoint", "http://127.0.0.1:9", "--host-id", "host-105",
        "--account-id", "90000001", "--timeout", "1",
    )
    assert envelope["status"] == "DEGRADED"
    assert envelope["intent_count"] == 0
    assert envelope["readonly"] is True
    assert envelope["orders_enabled"] is False
