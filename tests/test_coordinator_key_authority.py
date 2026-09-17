from kitling_bigqmt.coordinator_key_authority import (
    KeyObservation,
    reconcile_account_authority,
)


def observe(account, host, environment, *, valid=True, expires_at=200):
    return KeyObservation(account, host, environment, "sha256:test-" + host, 100, expires_at, valid)


def test_missing_or_expired_key_is_readonly():
    result = reconcile_account_authority("90000001", [], now_epoch=100, simulation_execution_policy=True)
    assert result.state == "NO_VALID_KEY_READONLY"
    expired = reconcile_account_authority("90000001", [observe("90000001", "host-a", "SIMULATION", expires_at=100)], now_epoch=100, simulation_execution_policy=True)
    assert expired.state == "NO_VALID_KEY_READONLY"


def test_two_hosts_with_same_account_key_lock_everyone_down():
    result = reconcile_account_authority("90000001", [
        observe("90000001", "host-a", "SIMULATION"),
        observe("90000001", "host-b", "SIMULATION"),
    ], now_epoch=100, simulation_execution_policy=True)
    assert result.state == "DUPLICATE_KEY_LOCKDOWN"
    assert result.valid_host_ids == ("host-a", "host-b")
    assert result.execution_eligible is False
    assert result.orders_enabled is False


def test_one_simulation_key_can_be_lease_candidate_but_not_open_orders():
    result = reconcile_account_authority("90000001", [observe("90000001", "host-a", "SIMULATION")], now_epoch=100, simulation_execution_policy=True)
    assert result.state == "SINGLE_KEY_LEASE_ELIGIBLE"
    assert result.eligible_host_id == "host-a"
    assert result.execution_eligible is True
    assert result.orders_enabled is False


def test_production_key_remains_policy_readonly_by_default():
    result = reconcile_account_authority("90000002", [observe("90000002", "host-a", "PRODUCTION")], now_epoch=100)
    assert result.state == "SINGLE_KEY_POLICY_READONLY"
    assert result.execution_eligible is False
