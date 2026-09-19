import json
from pathlib import Path

import pytest

from scripts.publish_strategy_package import PackageError, build_package


ROOT = Path(__file__).resolve().parents[1]
STRATEGY_ID = "S10_D1_U25_NO_ALCOHOL_5D_SIM_MAIN_V1_1_15"


def _source(tmp_path: Path) -> Path:
    source = tmp_path / "source"
    source.mkdir()
    (source / "strategy.py").write_text("# deterministic test strategy\n", encoding="utf-8")
    return source


def test_build_strategy_package_is_immutable_and_locked(tmp_path: Path):
    result = build_package(strategy_id=STRATEGY_ID, version="v1.1.15", build_id="test001",
                           source=_source(tmp_path), output_root=tmp_path / "releases",
                           registry_path=ROOT / "config" / "strategy_registry.json")
    release = Path(result["release_dir"])
    manifest = json.loads((release / "MANIFEST.json").read_text(encoding="utf-8"))
    assert result["orders_enabled"] is False
    assert manifest["safety"]["formal_account_allowed"] is False
    assert (release / "checksums.sha256").exists()
    assert Path(result["zip"]).exists()
    assert manifest["artifacts"]


def test_publisher_rejects_sensitive_files(tmp_path: Path):
    source = _source(tmp_path)
    (source / "machine.local.json").write_text("{}", encoding="utf-8")
    with pytest.raises(PackageError, match="sensitive/runtime"):
        build_package(strategy_id=STRATEGY_ID, version="v1.1.15", build_id="test002",
                      source=source, output_root=tmp_path / "releases",
                      registry_path=ROOT / "config" / "strategy_registry.json")


def test_publisher_refuses_version_drift(tmp_path: Path):
    with pytest.raises(PackageError, match="does not match"):
        build_package(strategy_id=STRATEGY_ID, version="v9.9.9", build_id="test003",
                      source=_source(tmp_path), output_root=tmp_path / "releases",
                      registry_path=ROOT / "config" / "strategy_registry.json")
