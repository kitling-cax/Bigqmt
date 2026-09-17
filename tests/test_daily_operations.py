from kitling_bigqmt.daily_operations import reconcile_daily_positions


def test_daily_reconciliation_requires_complete_attribution():
    passed = reconcile_daily_positions({"A": 100, "B": 200}, {"A": 100}, {"B": 200})
    assert passed["status"] == "PASSED"
    blocked = reconcile_daily_positions({"A": 100}, {"A": 100}, {"B": 200})
    assert blocked["status"] == "BLOCKED"
    assert blocked["differences"][0]["stock_code"] == "B"
