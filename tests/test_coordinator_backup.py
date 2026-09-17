import sqlite3

import pytest

from kitling_bigqmt.coordinator_backup import CoordinatorBackupError, create_online_backup, prepare_shadow_database, verify_database
from kitling_bigqmt.coordinator_core import CoordinatorStore


def test_online_backup_is_verified_and_does_not_change_source(tmp_path):
    source, target = tmp_path / "source.sqlite3", tmp_path / "shadow.sqlite3"
    store = CoordinatorStore(source)
    lease = store.grant_lease("90000001", "host-105", ttl_seconds=60)
    result = create_online_backup(source, target)
    assert result["integrity_check"] == "ok"
    assert result["sha256"]
    assert CoordinatorStore(source).current_lease("90000001") == lease
    assert CoordinatorStore(target).current_lease("90000001") == lease


def test_shadow_preparation_expires_copied_leases_only(tmp_path):
    source, target = tmp_path / "source.sqlite3", tmp_path / "shadow.sqlite3"
    store = CoordinatorStore(source)
    store.grant_lease("90000001", "host-105", ttl_seconds=60)
    result = prepare_shadow_database(source, target)
    assert result["shadow_prepared"] is True
    assert result["inherited_leases_invalidated"] == 1
    assert CoordinatorStore(source).current_lease("90000001").expires_at > 0
    assert CoordinatorStore(target).current_lease("90000001").expires_at == 0


def test_backup_refuses_overwrite_and_verify_rejects_corrupt_file(tmp_path):
    source, target = tmp_path / "source.sqlite3", tmp_path / "shadow.sqlite3"
    CoordinatorStore(source).initialize()
    create_online_backup(source, target)
    with pytest.raises(CoordinatorBackupError, match="already exists"):
        create_online_backup(source, target)
    target.write_bytes(b"not sqlite")
    with pytest.raises(CoordinatorBackupError):
        verify_database(target)
