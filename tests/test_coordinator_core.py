from datetime import datetime, timezone

import pytest

from kitling_bigqmt.coordinator_core import AuthorizationError, CoordinatorStore, StaleLeaseError


def test_two_fake_hosts_cannot_hold_valid_lease_simultaneously(tmp_path):
    # Two independent store handles over the same SQLite file model two
    # separate "fake hosts" running in their own process/connection.  Each
    # grants a lease for the same account; only the latest is current and the
    # earlier token must fail validation.
    db = tmp_path / "coordinator.sqlite3"
    host_a = CoordinatorStore(db)
    host_b = CoordinatorStore(db)
    host_a.initialize()

    lease_a = host_a.grant_lease("90000001", "host-105", ttl_seconds=60)
    lease_b = host_b.grant_lease("90000001", "host-125", ttl_seconds=60)

    current = host_b.current_lease("90000001")
    assert current.host_id == "host-125"
    assert current.token == lease_b.token == lease_a.token + 1

    with pytest.raises(StaleLeaseError):
        host_a.validate_lease(lease_a)
    host_b.validate_lease(lease_b)
    with pytest.raises(StaleLeaseError):
        host_a.preview_intent(lease_a, {"account_id": "90000001", "strategy_id": "s",
                                        "symbol": "510300.SH", "side": "BUY", "quantity": 100})


def test_single_active_lease_and_fencing(tmp_path):
    store = CoordinatorStore(tmp_path / "coordinator.sqlite3")
    first = store.grant_lease("90000001", "host-105", ttl_seconds=60)
    second = store.grant_lease("90000001", "host-125", ttl_seconds=60)
    with pytest.raises(StaleLeaseError):
        store.preview_intent(first, {"account_id": "90000001", "strategy_id": "s", "symbol": "510300.SH", "side": "BUY", "quantity": 100})
    request_id = store.preview_intent(second, {"account_id": "90000001", "strategy_id": "s", "symbol": "510300.SH", "side": "BUY", "quantity": 100})
    store.confirm_intent(second, request_id)


def test_readonly_cannot_preview(tmp_path):
    store = CoordinatorStore(tmp_path / "coordinator.sqlite3")
    lease = store.grant_lease("90000002", "host-105", mode="READ_ONLY", ttl_seconds=60)
    with pytest.raises(StaleLeaseError):
        store.preview_intent(lease, {"account_id": "90000002", "strategy_id": "s", "symbol": "600000.SH", "side": "BUY", "quantity": 100})


def test_epoch_invalidates_old_lease(tmp_path):
    store = CoordinatorStore(tmp_path / "coordinator.sqlite3")
    lease = store.grant_lease("90000001", "host-105", ttl_seconds=60)
    store.bump_epoch()
    with pytest.raises(StaleLeaseError):
        store.preview_intent(lease, {"account_id": "90000001", "strategy_id": "s", "symbol": "510300.SH", "side": "BUY", "quantity": 100})


def test_expired_lease_and_duplicate_confirm_are_rejected(tmp_path):
    store = CoordinatorStore(tmp_path / "coordinator.sqlite3")
    lease = store.grant_lease("90000001", "host-105", ttl_seconds=-1)
    with pytest.raises(StaleLeaseError):
        store.preview_intent(lease, {"account_id": "90000001", "strategy_id": "s", "symbol": "510300.SH", "side": "BUY", "quantity": 100})

    live = store.grant_lease("90000001", "host-105", ttl_seconds=60)
    request_id = store.preview_intent(live, {"account_id": "90000001", "strategy_id": "s", "symbol": "510300.SH", "side": "BUY", "quantity": 100})
    store.confirm_intent(live, request_id)
    with pytest.raises(AuthorizationError):
        store.confirm_intent(live, request_id)


def test_heartbeat_and_takeover_leave_only_latest_host_current(tmp_path):
    store = CoordinatorStore(tmp_path / "coordinator.sqlite3")
    store.heartbeat("host-105", "ACTIVE_EXECUTOR", "HEALTHY_READONLY", {"qmt": "UP"})
    store.heartbeat("host-125", "STANDBY_READONLY", "OFFLINE", {"qmt": "DOWN"})
    old = store.grant_lease("90000001", "host-105", ttl_seconds=60)
    new = store.grant_lease("90000001", "host-125", ttl_seconds=60)
    assert new.token == old.token + 1
    assert store.current_lease("90000001") == new
    with pytest.raises(StaleLeaseError):
        store.validate_lease(old)
