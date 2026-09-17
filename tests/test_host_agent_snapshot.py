from kitling_bigqmt.host_agent_snapshot import build_heartbeat


def test_snapshot_is_versioned_and_sanitized():
    data = build_heartbeat("192.0.2.105", "HEALTHY_READONLY", {"qmt": "UP", "redis": "UP"}, account_ids=["90000001"])
    assert data["schema_version"] == 1
    assert data["state"] == "HEALTHY_READONLY"
    assert "password" not in data
    assert "orders" not in data
