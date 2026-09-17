from kitling_bigqmt.ops_alerts import build_ops_alerts


def test_ops_alerts_flag_stale_quotes_and_active_blockers():
    result = build_ops_alerts(
        bridge="RUNNING_READ_ONLY",
        orders_enabled=False,
        quote_summary={"states": {"STALE": 2, "UNKNOWN": 0}},
        active_blockers=[{"id": "T1", "description": "等待 T+1"}],
        lake_cycle={"status": "PASSED"},
    )
    assert result["alert_count"] == 2
    assert result["highest_severity"] == "WARNING"
    assert result["read_only"] is True


def test_ops_alerts_flag_unexpected_order_enablement_as_critical():
    result = build_ops_alerts(
        bridge="RUNNING_READ_ONLY",
        orders_enabled=True,
        quote_summary={"states": {}}, active_blockers=[], lake_cycle={"status": "PASSED"},
    )
    assert result["highest_severity"] == "CRITICAL"
    assert result["alerts"][0]["id"] == "ORDERS_ENABLED_UNEXPECTED"
