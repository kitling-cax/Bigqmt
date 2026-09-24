"""Pull and locally install Coordinator strategy requests once.

The Host Agent is pull-based: the Coordinator never connects to a Windows
port. Installation is hash-verified and never starts a strategy or enables
orders. A failed NAS read is reported and can be retried by a new request.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from contextlib import AbstractContextManager
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kitling_bigqmt.coordinator_endpoint import resolve_coordinator  # noqa: E402
from kitling_bigqmt.machine_config import load_machine_local  # noqa: E402
from kitling_bigqmt.strategy_installer import install_package  # noqa: E402


class HostPollLock(AbstractContextManager):
    """Prevent the simulation and production trays racing on one host.

    Both account trays intentionally share one host queue.  A process-level
    lock is required because each tray launches this script independently.
    """

    def __init__(self, path: Path):
        self.path = Path(path)
        self.handle = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a+b")
        self.handle.seek(0)
        if os.name == "nt":
            import msvcrt
            if self.handle.tell() == 0:
                self.handle.write(b"0")
                self.handle.flush()
                self.handle.seek(0)
            try:
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                self.handle.close()
                self.handle = None
                raise RuntimeError("another tray is polling strategy deployments") from exc
        else:
            import fcntl
            try:
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                self.handle.close()
                self.handle = None
                raise RuntimeError("another tray is polling strategy deployments") from exc
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.handle is None:
            return False
        try:
            if os.name == "nt":
                import msvcrt
                self.handle.seek(0)
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        finally:
            self.handle.close()
            self.handle = None
        return False


def _json_request(url: str, *, method: str = "GET", payload: dict | None = None) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    request = Request(url, data=data, method=method, headers={"Accept": "application/json", "Content-Type": "application/json"})
    with urlopen(request, timeout=8) as response:
        body = response.read().decode("utf-8")
    parsed = json.loads(body) if body else {}
    if not isinstance(parsed, dict):
        raise ValueError("Coordinator response must be an object")
    return parsed


def _paths(machine: dict) -> tuple[Path, Path]:
    config = machine.get("strategy_deployment") if isinstance(machine.get("strategy_deployment"), dict) else {}
    library = str(config.get("library_root") or "").strip()
    install = str(config.get("install_root") or "").strip()
    if not library:
        raise ValueError("strategy_deployment.library_root is not configured")
    if not install:
        install = str(ROOT / "runtime_data" / "strategies" / "installed")
    return Path(library), Path(install)


def poll_once() -> dict:
    endpoint, host_id = resolve_coordinator(ROOT)
    if not host_id.strip():
        raise ValueError("host_id is not configured")
    library_root, install_root = _paths(load_machine_local(ROOT))
    lock_path = install_root.parent / ".strategy_deployment_poll.lock"
    try:
        lock = HostPollLock(lock_path)
        lock.__enter__()
    except RuntimeError:
        return {
            "status": "busy", "host_id": host_id, "orders_enabled": False,
            "deployments": [], "reason": "another tray is polling strategy deployments",
        }
    try:
        pending = _json_request(
            endpoint.rstrip("/") + "/api/v1/strategy-deployments?host_id=" + host_id
        ).get("deployments", [])
        results = []
        for request in pending if isinstance(pending, list) else []:
            deployment_id = str(request.get("deployment_id") or "")
            package_path = Path(str(request.get("package_path") or ""))
            package_dir = (library_root / package_path).resolve()
            try:
                package_dir.relative_to(library_root.resolve())
            except ValueError:
                package_dir = Path("__invalid_package_path__")
            try:
                _json_request(
                    endpoint.rstrip("/") + "/api/v1/strategy-deployments/" + deployment_id + "/status",
                    method="POST", payload={"host_id": host_id, "status": "INSTALLING", "result": {"orders_enabled": False}},
                )
                result = install_package(package_dir, install_root)
                status = "INSTALLED" if result.get("status") == "INSTALLED" else "INSTALLED"
                detail = result
            except (OSError, ValueError, HTTPError, URLError, json.JSONDecodeError) as exc:
                status = "FAILED"
                detail = {"reason": str(exc), "orders_enabled": False, "run_after_install": False}
            try:
                _json_request(
                    endpoint.rstrip("/") + "/api/v1/strategy-deployments/" + deployment_id + "/status",
                    method="POST", payload={"host_id": host_id, "status": status, "result": detail},
                )
            except (OSError, ValueError, HTTPError, URLError, json.JSONDecodeError) as exc:
                detail = {**detail, "status_callback_error": str(exc)}
            results.append({"deployment_id": deployment_id, "status": status, "result": detail})
        return {"status": "ok", "host_id": host_id, "orders_enabled": False, "deployments": results}
    finally:
        lock.__exit__(None, None, None)


def main() -> int:
    parser = argparse.ArgumentParser(description="Pull/install pending strategy deployments once")
    parser.add_argument("--once", action="store_true", help="compatibility flag; one poll is always performed")
    args = parser.parse_args()
    del args
    try:
        print(json.dumps(poll_once(), ensure_ascii=False))
        return 0
    except (OSError, ValueError, HTTPError, URLError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc), "orders_enabled": False}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
