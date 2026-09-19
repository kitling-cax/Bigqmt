import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from kitling_bigqmt.strategy_installer import install_package  # noqa: E402

import uninstall_strategy_package as uninstaller  # noqa: E402


def _package(root: Path, strategy_id: str = "S10", version: str = "v1", build_id: str = "r1") -> Path:
    package = root / strategy_id / version / build_id
    payload = package / "payload"
    payload.mkdir(parents=True)
    file = payload / "strategy.py"
    file.write_text("print('safe')\n", encoding="utf-8")
    manifest = {
        "strategy_id": strategy_id, "version": version, "build_id": build_id,
        "artifacts": [{"path": "payload/strategy.py", "sha256": hashlib.sha256(file.read_bytes()).hexdigest()}],
        "safety": {"orders_enabled": False, "formal_account_allowed": False},
    }
    (package / "MANIFEST.json").write_text(json.dumps(manifest), encoding="utf-8")
    return package


def test_list_installed_reports_each_build(tmp_path: Path):
    library = tmp_path / "library"
    install_root = tmp_path / "installed"
    install_package(_package(library, "S10", "v1", "r1"), install_root)
    install_package(_package(library, "S10", "v1", "r2"), install_root)
    install_package(_package(library, "S11", "v2", "r1"), install_root)
    installed = uninstaller.list_installed(install_root)
    ids = {(item["strategy_id"], item["version"], item["build_id"]) for item in installed}
    assert ids == {("S10", "v1", "r1"), ("S10", "v1", "r2"), ("S11", "v2", "r1")}


def test_uninstall_removes_only_targeted_build(tmp_path: Path):
    library = tmp_path / "library"
    install_root = tmp_path / "installed"
    install_package(_package(library, "S10", "v1", "r1"), install_root)
    install_package(_package(library, "S10", "v1", "r2"), install_root)
    result = uninstaller.uninstall("S10", "v1", "r1", install_root)
    assert result["status"] == "uninstalled"
    assert not (install_root / "S10" / "v1" / "r1").exists()
    assert (install_root / "S10" / "v1" / "r2" / "INSTALL_RESULT.json").is_file()


def test_uninstall_returns_not_found_for_missing_build(tmp_path: Path):
    install_root = tmp_path / "installed"
    install_root.mkdir()
    result = uninstaller.uninstall("S99", "v9", "r9", install_root)
    assert result["status"] == "not_found"


def test_uninstall_rejects_path_traversal(tmp_path: Path):
    install_root = tmp_path / "installed"
    install_root.mkdir()
    for bad in ("../escape", "with/slash", "with\\backslash", ".."):
        try:
            uninstaller.uninstall(bad, "v1", "r1", install_root)
        except ValueError:
            continue
        raise AssertionError("expected ValueError for %r" % bad)


def test_uninstall_refuses_to_touch_paths_outside_install_root(tmp_path: Path):
    install_root = tmp_path / "installed"
    install_root.mkdir()
    decoy = tmp_path / "elsewhere"
    decoy.mkdir()
    (decoy / "INSTALL_RESULT.json").write_text("{}", encoding="utf-8")
    try:
        uninstaller.uninstall("..", str(decoy.name), "r1", install_root)
    except ValueError:
        return
    raise AssertionError("expected ValueError when path escapes install_root")
