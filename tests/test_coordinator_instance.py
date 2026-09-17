import pytest

from kitling_bigqmt.coordinator_instance import (
    CoordinatorInstanceError,
    CoordinatorInstanceLock,
    advance_epoch_floor,
    load_or_create_identity,
    validate_instance_envelope,
)


def test_identity_is_stable_and_epoch_floor_never_moves_backward(tmp_path):
    first = load_or_create_identity(tmp_path)
    assert load_or_create_identity(tmp_path).instance_id == first.instance_id
    assert advance_epoch_floor(tmp_path, 3) == 4
    assert advance_epoch_floor(tmp_path, 1) == 5
    identity = load_or_create_identity(tmp_path)
    assert identity.epoch_floor == 5


def test_same_state_directory_cannot_have_two_local_locks(tmp_path):
    first = CoordinatorInstanceLock(tmp_path)
    second = CoordinatorInstanceLock(tmp_path)
    first.acquire()
    try:
        with pytest.raises(CoordinatorInstanceError, match="already locked"):
            second.acquire()
    finally:
        first.release()
    second.acquire()
    second.release()


def test_instance_envelope_rejects_other_instance_and_old_epoch(tmp_path):
    identity = load_or_create_identity(tmp_path)
    advance_epoch_floor(tmp_path, 4)
    identity = load_or_create_identity(tmp_path)
    with pytest.raises(CoordinatorInstanceError, match="instance mismatch"):
        validate_instance_envelope({"coordinator_instance_id": "bad", "coordinator_epoch": 9}, identity)
    with pytest.raises(CoordinatorInstanceError, match="below durable floor"):
        validate_instance_envelope({"coordinator_instance_id": identity.instance_id, "coordinator_epoch": 1}, identity)
