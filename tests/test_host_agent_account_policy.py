import pytest

from kitling_bigqmt.host_agent_account_policy import (
    AccountPolicy,
    AccountPolicyRejected,
    evaluate_local_execution,
    resolve_account_policy,
)


def test_resolves_simulation_profile_readonly():
    policy = resolve_account_policy("simulation")
    assert policy.profile == "simulation"
    assert policy.account_id == "90000001"
    assert policy.environment == "simulation"
    assert policy.orders_enabled is False
    assert policy.execution_allowed is False
    assert policy.production_readonly is False


def test_resolves_production_profile_as_permanent_readonly():
    policy = resolve_account_policy("production_readonly")
    assert policy.account_id == "90000002"
    assert policy.environment == "production"
    assert policy.production_readonly is True
    assert policy.orders_enabled is False
    assert policy.execution_allowed is False


def test_account_id_mismatch_fails_closed():
    with pytest.raises(AccountPolicyRejected, match="does not match"):
        resolve_account_policy("simulation", "90000002")
    with pytest.raises(AccountPolicyRejected, match="does not match"):
        resolve_account_policy("production_readonly", "90000001")


def test_machine_configured_account_binding_does_not_require_repository_identity():
    policy = resolve_account_policy(
        "simulation", "LOCAL_ACCOUNT", configured_account_id="LOCAL_ACCOUNT"
    )
    assert policy.account_id == "LOCAL_ACCOUNT"
    with pytest.raises(AccountPolicyRejected, match="does not match"):
        resolve_account_policy(
            "simulation", "OTHER_ACCOUNT", configured_account_id="LOCAL_ACCOUNT"
        )


def test_unknown_profile_fails_closed():
    with pytest.raises(AccountPolicyRejected, match="unknown profile"):
        resolve_account_policy("production")


def test_production_is_denied_local_execution_even_with_no_lease():
    verdict = evaluate_local_execution("production_readonly")
    assert verdict["allowed"] is False
    assert verdict["orders_enabled"] is False
    assert verdict["reason"] == "PRODUCTION_READ_ONLY"


def test_simulation_without_trusted_transport_is_denied():
    verdict = evaluate_local_execution("simulation")
    assert verdict["allowed"] is False
    assert verdict["reason"] == "NO_TRUSTED_TRANSPORT"


def test_simulation_with_trusted_transport_still_locked_in_m03():
    verdict = evaluate_local_execution("simulation", trusted_transport=True)
    assert verdict["allowed"] is False
    assert verdict["orders_enabled"] is False
    assert verdict["reason"] == "LEASED_EXECUTION_NOT_ENABLED_IN_M03"


def test_simulation_valid_lease_does_not_open_execution_in_m03():
    lease = {
        "schema_version": 1,
        "account_id": "90000001",
        "host_id": "192.0.2.105",
        "mode": "ACTIVE_EXECUTOR",
        "fencing_token": 7,
        "coordinator_epoch": 3,
        "expires_at": 200.0,
    }
    verdict = evaluate_local_execution(
        "simulation",
        host_id="192.0.2.105",
        lease_envelope=lease,
        trusted_transport=True,
        now_epoch=100.0,
    )
    assert verdict["allowed"] is False
    assert verdict["orders_enabled"] is False
    assert verdict["reason"] == "LEASED_EXECUTION_NOT_ENABLED_IN_M03"


def test_simulation_stale_lease_is_rejected_with_lease_reason():
    lease = {
        "schema_version": 1,
        "account_id": "90000001",
        "host_id": "192.0.2.105",
        "mode": "ACTIVE_EXECUTOR",
        "fencing_token": 0,
        "coordinator_epoch": 3,
        "expires_at": 200.0,
    }
    verdict = evaluate_local_execution(
        "simulation",
        host_id="192.0.2.105",
        lease_envelope=lease,
        trusted_transport=True,
        now_epoch=100.0,
    )
    assert verdict["allowed"] is False
    assert "invalid" in verdict["reason"]
