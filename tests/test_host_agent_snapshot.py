import json

from kitling_bigqmt.host_agent_snapshot import build_heartbeat


def test_snapshot_is_versioned_and_sanitized():
    data = build_heartbeat("192.0.2.105", "HEALTHY_READONLY", {"qmt": "UP", "redis": "UP"}, account_ids=["90000001"])
    assert data["schema_version"] == 1
    assert data["state"] == "HEALTHY_READONLY"
    assert "password" not in data
    assert "orders" not in data


def test_snapshot_carries_only_sanitized_strategy_visibility():
    data = build_heartbeat(
        "192.0.2.105", "HEALTHY_READONLY", {"qmt": "UP"}, account_ids=["90000001"],
        strategy_instances=[{"strategy_id": "S10", "version": "v1.1.15",
                             "state": "RUNNING", "policy_enabled": True,
                             "authorization_key_state": "VALID", "bridge_version": "0.3.26"}],
    )
    assert data["strategy_instances"][0]["strategy_id"] == "S10"
    assert "authorization_key" not in data["strategy_instances"][0]
    assert "secret" not in json.dumps(data)
