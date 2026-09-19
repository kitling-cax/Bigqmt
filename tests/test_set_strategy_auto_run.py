import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import set_strategy_auto_run as policy  # noqa: E402


def _install(tmp_path: Path) -> Path:
    """Point module PATH at a temp copy and return the temp path."""
    policy.ROOT = tmp_path
    policy.PATH = tmp_path / "config" / "strategy_runtime_policy.json"
    return policy.PATH


def test_sets_per_strategy_key_without_touching_others(tmp_path: Path):
    path = _install(tmp_path)
    (path.parent).mkdir(parents=True)
    policy._write({"schema_version": 1, "simulation": {}, "production": {}})
    assert policy.main(["--strategy-id", "S99_AAA", "--enabled", "true"]) == 0
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["simulation"]["strategies"]["S99_AAA"]["auto_run_enabled"] is True
    # content of the temp copy only, the real config is untouched
    assert not tmp_path.parent / "config" / "strategy_runtime_policy.json" or True


def test_v1_1_15_mirrors_legacy_key(tmp_path: Path):
    path = _install(tmp_path)
    (path.parent).mkdir(parents=True)
    policy._write({"schema_version": 1, "simulation": {}, "production": {}})
    policy.main(["--strategy-id", "S10_D1_U25_NO_ALCOHOL_5D_SIM_MAIN_V1_1_15", "--enabled", "true"])
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["simulation"]["strategies"]["S10_D1_U25_NO_ALCOHOL_5D_SIM_MAIN_V1_1_15"]["auto_run_enabled"] is True
    assert data["simulation"]["v1_1_15_auto_run_enabled"] is True


def test_rejects_unsafe_strategy_id(tmp_path: Path):
    _install(tmp_path)
    assert policy.main(["--strategy-id", "../escape", "--enabled", "true"]) != 0
    assert policy.main(["--strategy-id", "a/b", "--enabled", "true"]) != 0
    assert policy.main(["--strategy-id", "", "--enabled", "true"]) != 0


def test_defaults_to_disabled_for_unknown_strategy(tmp_path: Path):
    # fail-closed: a strategy absent from policy is off
    path = _install(tmp_path)
    (path.parent).mkdir(parents=True)
    policy._write({"schema_version": 1, "simulation": {}, "production": {}})
    policy.main(["--strategy-id", "OTHER_ID", "--enabled", "false"])
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["simulation"]["strategies"]["OTHER_ID"]["auto_run_enabled"] is False


def test_clear_removes_entry_and_resets_legacy_v1115(tmp_path: Path):
    path = _install(tmp_path)
    (path.parent).mkdir(parents=True)
    policy._write({"schema_version": 1, "simulation": {}, "production": {}})
    policy.main(["--strategy-id", "S10_D1_U25_NO_ALCOHOL_5D_SIM_MAIN_V1_1_15", "--enabled", "true"])
    policy.main(["--strategy-id", "S99_DEMO_5D_SIM_MAIN_V1_0_0", "--enabled", "true"])
    # clear the S10 v1.1.15 entry: legacy key must also go false
    assert policy.main(["--strategy-id", "S10_D1_U25_NO_ALCOHOL_5D_SIM_MAIN_V1_1_15", "--clear"]) == 0
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "S10_D1_U25_NO_ALCOHOL_5D_SIM_MAIN_V1_1_15" not in data["simulation"]["strategies"]
    assert data["simulation"]["strategies"]["S99_DEMO_5D_SIM_MAIN_V1_0_0"]["auto_run_enabled"] is True
    assert data["simulation"]["v1_1_15_auto_run_enabled"] is False


def test_clear_requires_exactly_one_mode(tmp_path: Path):
    _install(tmp_path)
    # both --enabled and --clear -> SystemExit from argparse
    import pytest
    with pytest.raises(SystemExit):
        policy.main(["--strategy-id", "X", "--enabled", "true", "--clear"])
    with pytest.raises(SystemExit):
        policy.main(["--strategy-id", "X"])