from kitling_bigqmt.bridge_probe import REPLY_EVIDENCE_FIELDS, probe_bridge_ping, reply_evidence


class _FakeRedis:
    def __init__(self, **_kwargs):
        pass


class _PassingClient:
    def __init__(self, **_kwargs):
        pass

    def ping(self):
        return {"ok": True}


class _TimeoutClient:
    def __init__(self, **_kwargs):
        pass

    def ping(self):
        raise TimeoutError("offline")


class _EvidenceClient:
    """Answers like the live BIGQMT_BRIDGE: identity block nested under 'data'."""

    def __init__(self, **_kwargs):
        pass

    def ping(self):
        return {
            "ok": True,
            "data": {
                "account_id": "90000001",
                "account_type": "STOCK",
                "version": "0.3.26",
                "rpc_revision": "20260715-execution-snapshot-v1",
                "server_time": "2026-09-16 07:45:00",
                "allow_order_methods": True,
                "positions": {"160723.SZ": {"volume": 41400}},
                "asset": {"cash": 1234.0},
            },
        }


def test_bridge_probe_passes_only_for_readonly_ping(monkeypatch):
    monkeypatch.setattr("kitling_bigqmt.bridge_probe.RedisRespClient", _FakeRedis)
    result = probe_bridge_ping(
        {"account_id": "90000001", "redis": {"host": "127.0.0.1", "port": 6379, "db": 5}},
        client_factory=_PassingClient,
    )
    assert result["status"] == "PASS"
    assert result["broker_call_made"] is False
    assert result["order_capability"] is False


def test_bridge_probe_degrades_on_timeout(monkeypatch):
    monkeypatch.setattr("kitling_bigqmt.bridge_probe.RedisRespClient", _FakeRedis)
    result = probe_bridge_ping(
        {"account_id": "90000001", "redis": {"host": "127.0.0.1", "port": 6379, "db": 5}},
        client_factory=_TimeoutClient,
    )
    assert result["status"] == "DEGRADED"
    assert result["broker_call_made"] is False


def test_reply_evidence_reads_nested_data_block_and_whitelists_fields():
    evidence = reply_evidence(_EvidenceClient().ping())
    assert evidence["version"] == "0.3.26"
    assert evidence["rpc_revision"] == "20260715-execution-snapshot-v1"
    assert evidence["account_id"] == "90000001"
    assert evidence["allow_order_methods"] is True
    # Position/asset payloads must never leak into the evidence block.
    assert set(evidence) <= set(REPLY_EVIDENCE_FIELDS)
    assert "positions" not in evidence and "asset" not in evidence


def test_reply_evidence_accepts_top_level_legacy_shape():
    assert reply_evidence({"version": "0.3.20", "rpc_revision": "legacy", "unexpected": "x"}) == {
        "version": "0.3.20",
        "rpc_revision": "legacy",
    }


def test_bridge_probe_records_version_evidence_without_enabling_orders(monkeypatch):
    monkeypatch.setattr("kitling_bigqmt.bridge_probe.RedisRespClient", _FakeRedis)
    result = probe_bridge_ping(
        {"account_id": "90000001", "redis": {"host": "127.0.0.1", "port": 6379, "db": 5}},
        client_factory=_EvidenceClient,
    )
    assert result["status"] == "PASS"
    assert result["bridge_reply_ok"] is True
    assert result["bridge_reply"]["version"] == "0.3.26"
    assert result["bridge_reply"]["rpc_revision"] == "20260715-execution-snapshot-v1"
    # Capturing evidence is bookkeeping only; the probe still reports no order path.
    assert result["broker_call_made"] is False
    assert result["order_capability"] is False
