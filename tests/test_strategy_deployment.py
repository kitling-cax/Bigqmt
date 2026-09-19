import hashlib
import json
from pathlib import Path

from kitling_bigqmt.strategy_deployment import StrategyDeploymentStore
from kitling_bigqmt.strategy_installer import install_package


def _package(root: Path) -> Path:
    package = root / "S10" / "v1" / "r1"
    payload = package / "payload"
    payload.mkdir(parents=True)
    file = payload / "strategy.py"
    file.write_text("print('safe')\n", encoding="utf-8")
    manifest = {
        "strategy_id": "S10", "version": "v1", "build_id": "r1",
        "artifacts": [{"path": "payload/strategy.py", "sha256": hashlib.sha256(file.read_bytes()).hexdigest()}],
        "safety": {"orders_enabled": False, "formal_account_allowed": False},
    }
    (package / "MANIFEST.json").write_text(json.dumps(manifest), encoding="utf-8")
    return package


def test_installer_verifies_and_is_idempotent(tmp_path: Path):
    package = _package(tmp_path / "library")
    target = tmp_path / "installed"
    first = install_package(package, target)
    second = install_package(package, target)
    assert first["status"] == "INSTALLED"
    assert second["status"] == "ALREADY_INSTALLED"
    assert first["orders_enabled"] is False
    assert (target / "S10" / "v1" / "r1" / "payload" / "strategy.py").is_file()


def test_deployment_store_is_idempotent_and_host_scoped(tmp_path: Path):
    store = StrategyDeploymentStore(tmp_path / "coordinator.sqlite3")
    first = store.request_install(
        strategy_id="S10", version="v1", build_id="r1", manifest_sha256="abc",
        package_path="S10/v1/r1", target_host_id=".125",
    )
    again = store.request_install(
        strategy_id="S10", version="v1", build_id="r1", manifest_sha256="abc",
        package_path="S10/v1/r1", target_host_id=".125",
    )
    assert first["deployment_id"] == again["deployment_id"]
    assert store.pending_for_host(".125")[0]["status"] == "REQUESTED"
    updated = store.update_status(first["deployment_id"], ".125", "INSTALLED", {"run_after_install": False})
    assert updated["status"] == "INSTALLED"
    assert store.pending_for_host(".125") == []

