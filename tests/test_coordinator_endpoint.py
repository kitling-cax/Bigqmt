import json

from kitling_bigqmt.coordinator_endpoint import resolve_coordinator


def test_machine_local_supplies_portable_coordinator_settings(tmp_path, monkeypatch):
    monkeypatch.delenv("BIGQMT_COORDINATOR_ENDPOINT", raising=False)
    monkeypatch.delenv("BIGQMT_HOST_ID", raising=False)
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "machine.local.json").write_text(json.dumps({"coordinator": {
        "endpoint": "http://10.10.10.121:18443", "host_id": "198.51.100.113"
    }}), encoding="utf-8")
    assert resolve_coordinator(tmp_path) == ("http://10.10.10.121:18443", "198.51.100.113")


def test_environment_override_wins_over_machine_local(tmp_path, monkeypatch):
    monkeypatch.setenv("BIGQMT_COORDINATOR_ENDPOINT", "http://127.0.0.1:9999")
    monkeypatch.setenv("BIGQMT_HOST_ID", "test-host")
    assert resolve_coordinator(tmp_path) == ("http://127.0.0.1:9999", "test-host")
