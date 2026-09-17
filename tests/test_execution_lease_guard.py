import pytest

from kitling_bigqmt.execution_lease_guard import LeaseRejected, verify_execution_lease


def _lease(**changes):
    value = {
        "schema_version": 1, "account_id": "90000001", "host_id": "192.0.2.105",
        "mode": "ACTIVE_EXECUTOR", "fencing_token": 7, "coordinator_epoch": 3,
        "expires_at": 200.0,
    }
    value.update(changes)
    return value


def test_valid_simulation_lease_is_accepted_only_from_trusted_transport():
    lease = verify_execution_lease(_lease(), expected_account_id="90000001", expected_host_id="192.0.2.105",
                                   trusted_transport=True, now_epoch=100.0)
    assert lease.fencing_token == 7
    with pytest.raises(LeaseRejected, match="not authenticated"):
        verify_execution_lease(_lease(), expected_account_id="90000001", expected_host_id="192.0.2.105",
                               trusted_transport=False, now_epoch=100.0)


@pytest.mark.parametrize("changes,expected", [
    ({"host_id": "192.0.2.125"}, "another host"),
    ({"mode": "READ_ONLY"}, "not an active"),
    ({"expires_at": 100.0}, "expired"),
    ({"fencing_token": 0}, "invalid"),
])
def test_invalid_or_stale_lease_is_rejected(changes, expected):
    with pytest.raises(LeaseRejected, match=expected):
        verify_execution_lease(_lease(**changes), expected_account_id="90000001",
                               expected_host_id="192.0.2.105", trusted_transport=True, now_epoch=100.0)


def test_formal_account_is_never_an_active_executor():
    with pytest.raises(LeaseRejected, match="production readonly"):
        verify_execution_lease(_lease(account_id="90000002"), expected_account_id="90000002",
                               expected_host_id="192.0.2.105", trusted_transport=True, now_epoch=100.0)
