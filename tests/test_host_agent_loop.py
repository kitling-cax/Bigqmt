import json

import pytest

from kitling_bigqmt.host_agent_loop import HostAgentLoop
from kitling_bigqmt.host_agent_client import HostAgentClient


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return b"{}"


def _client(heartbeat_body=None, intent_payload=None, *, trap=None):
    if intent_payload is None:
        intent_payload = {
            "mode": "readonly-intent-preview",
            "readonly": True,
            "orders_enabled": False,
            "account_id": "90000001",
            "host_id": "192.0.2.105",
            "intents": [],
        }

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            if trap is not None:
                return trap
            return json.dumps(intent_payload).encode("utf-8")

    seen = {"heartbeat": None, "intent_url": None}

    def transport(request, timeout):
        seen["url"] = request.full_url
        if request.method == "GET":
            seen["intent_url"] = request.full_url
            return Response()
        seen["heartbeat"] = json.loads(request.data)
        return FakeResponse()

    return HostAgentClient("http://127.0.0.1:18443", "192.0.2.105", transport=transport), seen


def test_loop_sends_heartbeat_and_polls_intent_on_first_tick():
    client, seen = _client()
    loop = HostAgentLoop(client, "simulation", heartbeat_services_provider=lambda: {"tray": "UP"})
    result = loop.tick(now=0.0)
    assert result["heartbeat_sent"] is True
    assert result["intent_polled"] is True
    assert result["intent_count"] == 0
    assert result["orders_enabled"] is False
    assert seen["heartbeat"]["accounts"] == ["90000001"]
    assert "/api/v1/host-agent/intents" in seen["intent_url"]


def test_loop_does_not_resend_within_intervals():
    client, seen = _client()
    loop = HostAgentLoop(client, "simulation", heartbeat_services_provider=lambda: {"tray": "UP"})
    loop.tick(now=0.0)
    seen["heartbeat"] = None
    seen["intent_url"] = None
    result = loop.tick(now=1.0)
    assert result["heartbeat_sent"] is False
    assert result["intent_polled"] is False
    assert seen["heartbeat"] is None
    assert seen["intent_url"] is None


def test_loop_fails_closed_when_intent_preview_contains_an_intent():
    payload = {
        "mode": "readonly-intent-preview",
        "readonly": True,
        "orders_enabled": False,
        "account_id": "90000001",
        "host_id": "192.0.2.105",
        "intents": [{"symbol": "510300.SH"}],
    }
    client, _ = _client(intent_payload=payload)
    loop = HostAgentLoop(client, "simulation")
    result = loop.tick(now=0.0)
    assert result["intent_polled"] is False
    assert result["orders_enabled"] is False
    assert any(err["phase"] == "intent" for err in result["errors"])


def test_loop_keeps_running_when_heartbeat_transport_fails():
    def transport(request, timeout):
        raise OSError("coordinator down")

    client = HostAgentClient("http://127.0.0.1:18443", "192.0.2.105", transport=transport)
    loop = HostAgentLoop(client, "simulation")
    result = loop.tick(now=0.0)
    assert result["heartbeat_sent"] is False
    assert result["orders_enabled"] is False
    assert any(err["phase"] == "heartbeat" for err in result["errors"])


def test_production_profile_is_resolved_from_loop_without_orders():
    client, seen = _client()
    loop = HostAgentLoop(client, "production_readonly")
    result = loop.tick(now=0.0)
    assert result["orders_enabled"] is False
    assert loop.account_id == "90000002"
    assert seen["heartbeat"]["accounts"] == ["90000002"]
