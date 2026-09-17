import importlib.util
from pathlib import Path


def _load_builder():
    path = Path(__file__).resolve().parents[1] / "scripts" / "build_tray_manifest.py"
    spec = importlib.util.spec_from_file_location("build_tray_manifest", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_tray_manifest_contains_only_fail_closed_release_files(tmp_path: Path):
    module = _load_builder()
    output = tmp_path / "manifest.json"
    manifest = module.build(output, "test-tray")
    assert manifest["orders_enabled"] is False
    assert manifest["execution_consumer_enabled"] is False
    assert manifest["auto_login_secrets_embedded"] is False
    assert manifest["supports_windows_credential_auto_login"] is True
    assert manifest["supports_miniqmt_linkmini_passwordless"] is True
    assert len(manifest["files"]) == 22
    assert all(len(item["sha256"]) == 64 for item in manifest["files"])
