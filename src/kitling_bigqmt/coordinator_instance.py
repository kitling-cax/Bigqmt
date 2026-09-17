"""Fail-closed Coordinator instance identity, lock, and epoch-floor helpers.

These helpers are intentionally independent of the HTTP server.  They are
used by the future container entrypoint before it opens a listening socket.
The state directory is local to one Coordinator instance; it must never be an
SMB/NAS path shared by multiple instances.
"""
from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from pathlib import Path


class CoordinatorInstanceError(RuntimeError):
    """Raised when a Coordinator cannot prove it is the sole local instance."""


@dataclass(frozen=True)
class CoordinatorIdentity:
    instance_id: str
    epoch_floor: int


class CoordinatorInstanceLock:
    """A non-blocking advisory lock held for the process lifetime.

    Linux containers use ``flock``.  The Windows implementation exists only
    for local test tooling; both branches refuse to continue when another
    process owns the same lock.
    """

    _held_paths: set[Path] = set()

    def __init__(self, state_directory: str | Path):
        self.state_directory = Path(state_directory)
        self.path = self.state_directory / "coordinator.lock"
        self._handle = None

    def acquire(self) -> None:
        if self._handle is not None:
            return
        self.state_directory.mkdir(parents=True, exist_ok=True)
        canonical = self.path.resolve()
        if canonical in self._held_paths:
            raise CoordinatorInstanceError("coordinator state directory is already locked")
        handle = self.path.open("a+b")
        try:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                if handle.tell() == 0:
                    handle.write(b"0")
                    handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            handle.close()
            raise CoordinatorInstanceError("coordinator state directory is already locked") from exc
        self._handle = handle
        self._held_paths.add(canonical)

    def release(self) -> None:
        if self._handle is None:
            return
        canonical = self.path.resolve()
        try:
            if os.name == "nt":
                import msvcrt

                self._handle.seek(0)
                msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        finally:
            self._handle.close()
            self._handle = None
            self._held_paths.discard(canonical)

    def __enter__(self) -> "CoordinatorInstanceLock":
        self.acquire()
        return self

    def __exit__(self, *_: object) -> None:
        self.release()


def _read_nonnegative_int(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        value = int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError) as exc:
        raise CoordinatorInstanceError("invalid epoch floor") from exc
    if value < 0:
        raise CoordinatorInstanceError("invalid epoch floor")
    return value


def load_or_create_identity(state_directory: str | Path) -> CoordinatorIdentity:
    """Return stable local instance ID and durable epoch floor.

    A malformed identity fails closed instead of silently generating a new
    identity, because that could make an old fencing token appear current.
    """
    state = Path(state_directory)
    state.mkdir(parents=True, exist_ok=True)
    instance_path = state / "coordinator_instance_id"
    if instance_path.exists():
        value = instance_path.read_text(encoding="utf-8").strip()
        try:
            instance_id = str(uuid.UUID(value))
        except (ValueError, OSError) as exc:
            raise CoordinatorInstanceError("invalid coordinator instance ID") from exc
    else:
        instance_id = str(uuid.uuid4())
        temp = state / ".coordinator_instance_id.tmp"
        temp.write_text(instance_id + "\n", encoding="utf-8")
        os.replace(temp, instance_path)
    return CoordinatorIdentity(instance_id=instance_id, epoch_floor=_read_nonnegative_int(state / "epoch_floor"))


def advance_epoch_floor(state_directory: str | Path, database_epoch: int) -> int:
    """Persist and return a monotonic epoch after recovery from a backup."""
    if database_epoch < 0:
        raise CoordinatorInstanceError("invalid database epoch")
    state = Path(state_directory)
    state.mkdir(parents=True, exist_ok=True)
    floor_path = state / "epoch_floor"
    next_epoch = max(_read_nonnegative_int(floor_path), int(database_epoch)) + 1
    temp = state / ".epoch_floor.tmp"
    temp.write_text(str(next_epoch) + "\n", encoding="utf-8")
    os.replace(temp, floor_path)
    return next_epoch


def validate_instance_envelope(envelope: dict[str, object], identity: CoordinatorIdentity) -> None:
    """Reject a lease/authority envelope from another instance or older epoch."""
    if envelope.get("coordinator_instance_id") != identity.instance_id:
        raise CoordinatorInstanceError("coordinator instance mismatch")
    try:
        epoch = int(envelope.get("coordinator_epoch"))
    except (TypeError, ValueError) as exc:
        raise CoordinatorInstanceError("invalid coordinator epoch") from exc
    if epoch < identity.epoch_floor:
        raise CoordinatorInstanceError("coordinator epoch is below durable floor")
