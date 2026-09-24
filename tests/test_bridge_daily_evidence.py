"""Daily BIGQMT_BRIDGE running-evidence recorder.

The recorder is the durable answer to "was the strategy actually running on
that trading day, and which Redis RPC revision answered?"  These tests pin the
fail-closed behaviour: a missing version, a mismatched account or a failed ping
must never be rounded up to a clean day.
"""

from pathlib import Path

from scripts import record_bridge_daily_evidence as recorder


def _reply(**overrides) -> dict:
    data = {
        "account_id": "90000001",
        "account_type": "SIMULATION",
        "version": "0.3.26",
        "rpc_revision": "20260715-execution-snapshot-v1",
        "server_time": "20260916 09:35:00",
        "allow_order_methods": True,
    }
    data.update(overrides)
    return {"status": "PASS", "bridge_reply": data, "latency_ms": 12.0}


def _config() -> dict:
    return {"environment": "simulation", "account_id": "90000001"}


def _stub_support(monkeypatch, ping, fresh=True, orders_enabled=False):
    monkeypatch.setattr(recorder, "probe_bridge_ping", lambda *_args, **_kwargs: ping)
    monkeypatch.setattr(recorder, "snapshot_freshness", lambda *_args, **_kwargs: {
        "status": "PASS" if fresh else "DEGRADED", "fresh": fresh, "detail": "stub"})
    monkeypatch.setattr(recorder, "order_lock_state", lambda *_args, **_kwargs: {
        "mode": "READ_ONLY_LOCKED" if not orders_enabled else "live",
        "orders_enabled": orders_enabled, "execution_consumer_enabled": orders_enabled})


def test_build_sample_passes_when_strategy_is_running_and_locked(monkeypatch):
    _stub_support(monkeypatch, _reply())
    sample = recorder.build_sample("simulation", _config(), 3.0)
    assert sample["status"] == "PASSED"
    assert all(value == "PASS" for value in sample["checks"].values())
    assert sample["bridge_version"] == "0.3.26"
    assert sample["rpc_revision"] == "20260715-execution-snapshot-v1"
    assert "version=0.3.26" in sample["strategy_running_evidence"]
    # Recording evidence must never become a trading action.
    assert sample["broker_call_made"] is False
    assert sample["orders_enabled"] is False
    assert sample["read_only"] is True


def test_build_sample_degrades_when_version_is_not_reported(monkeypatch):
    _stub_support(monkeypatch, _reply(version=""))
    sample = recorder.build_sample("simulation", _config(), 3.0)
    assert sample["checks"]["bridge_version_reported"] == "DEGRADED"
    assert sample["status"] == "DEGRADED"


def test_build_sample_flags_account_mismatch(monkeypatch):
    _stub_support(monkeypatch, _reply(account_id="90000002"))
    sample = recorder.build_sample("simulation", _config(), 3.0)
    assert sample["checks"]["account_match"] == "FAIL"
    assert sample["status"] == "DEGRADED"


def test_build_sample_blocks_when_ping_fails(monkeypatch):
    _stub_support(monkeypatch, {"status": "FAIL", "detail": "connection refused"})
    sample = recorder.build_sample("simulation", _config(), 3.0)
    assert sample["checks"]["bridge_ping"] == "FAIL"
    assert sample["status"] == "BLOCKED"
    assert "ping failed" in sample["strategy_running_evidence"]
    assert sample["broker_call_made"] is False


def test_build_sample_keeps_live_ping_authoritative_over_stale_snapshot(monkeypatch):
    _stub_support(monkeypatch, _reply(), fresh=False)
    sample = recorder.build_sample("simulation", _config(), 3.0)
    # A stale hourly snapshot is a scheduling symptom, not a liveness failure.
    assert sample["checks"]["snapshot_fresh"] == "DEGRADED"
    assert sample["checks"]["bridge_ping"] == "PASS"
    assert sample["status"] == "DEGRADED"


def test_build_sample_marks_open_order_lock_as_failure(monkeypatch):
    _stub_support(monkeypatch, _reply(), orders_enabled=True)
    sample = recorder.build_sample("simulation", _config(), 3.0)
    assert sample["checks"]["order_lock"] == "FAIL"
    assert sample["status"] == "DEGRADED"


def test_build_sample_accepts_persistent_local_simulation_execution(monkeypatch):
    _stub_support(monkeypatch, _reply(), orders_enabled=True)
    monkeypatch.setattr(recorder, "order_lock_state", lambda *_args, **_kwargs: {
        "mode": "SIMULATION_STRATEGY_EXECUTION_ENABLED",
        "orders_enabled": True,
        "execution_consumer_enabled": True,
    })
    sample = recorder.build_sample("simulation", _config(), 3.0)
    assert sample["checks"]["order_lock"] == "PASS"
    assert sample["orders_enabled"] is True
    assert sample["read_only"] is False


def test_write_sample_merges_same_day_and_caps_samples(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(recorder, "evidence_directory", lambda profile: tmp_path / profile)
    _stub_support(monkeypatch, _reply())
    sample = recorder.build_sample("simulation", _config(), 3.0)

    first = recorder.write_sample("simulation", sample)
    second = recorder.write_sample("simulation", sample)
    assert first == second
    document = recorder.json.loads(first.read_text(encoding="utf-8"))
    assert document["sample_count"] == 2
    assert document["bridge_strategy"] == "BIGQMT_BRIDGE"
    assert document["last_status"] == "PASSED"
    assert document["latest"]["bridge_version"] == "0.3.26"

    for _ in range(recorder.MAX_SAMPLES_PER_DAY + 10):
        recorder.write_sample("simulation", sample)
    document = recorder.json.loads(first.read_text(encoding="utf-8"))
    assert document["sample_count"] == recorder.MAX_SAMPLES_PER_DAY
