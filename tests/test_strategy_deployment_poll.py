from pathlib import Path

import pytest

from scripts.poll_strategy_deployments import HostPollLock


def test_host_poll_lock_rejects_same_process(tmp_path: Path):
    path = tmp_path / "state" / ".strategy_deployment_poll.lock"
    first = HostPollLock(path)
    with first:
        second = HostPollLock(path)
        with pytest.raises(RuntimeError, match="another tray"):
            second.__enter__()
        assert second.handle is None


def test_host_poll_lock_releases(tmp_path: Path):
    path = tmp_path / ".strategy_deployment_poll.lock"
    with HostPollLock(path):
        pass
    with HostPollLock(path):
        pass
