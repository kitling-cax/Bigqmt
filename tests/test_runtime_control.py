from pathlib import Path
import time

from kitling_bigqmt.runtime_control import RuntimeControl


def test_runtime_control_defaults_to_fail_closed_and_persists_lock(tmp_path: Path):
    control = RuntimeControl(tmp_path / "control.json")
    assert control.status()["orders_enabled"] is False
    locked = control.lock_orders("test lock")
    assert locked["execution_consumer_enabled"] is False
    assert control.status()["lock_reason"] == "test lock"


def test_runtime_control_rejects_wrong_environment_state(tmp_path: Path):
    target = tmp_path / "control.json"
    target.write_text('{"environment":"production","orders_enabled":true}', encoding="utf-8")
    state = RuntimeControl(target).status()
    assert state["orders_enabled"] is False
    assert state["mode"] == "READ_ONLY_LOCKED"


def test_runtime_control_accepts_legacy_uppercase_environment(tmp_path: Path):
    target = tmp_path / "control.json"
    target.write_text(
        '{"environment":"SIMULATION","orders_enabled":true,"execution_consumer_enabled":true}',
        encoding="utf-8",
    )
    state = RuntimeControl(target, environment="simulation").status()
    assert state["orders_enabled"] is False
    assert state["execution_consumer_enabled"] is False
    assert state["environment"] == "SIMULATION"


def test_runtime_control_enables_persistent_simulation_execution(tmp_path: Path):
    target = tmp_path / "control.json"
    control = RuntimeControl(target, environment="simulation")
    armed = control.arm_simulation_strategy(
        account_id="90000001", strategy_id="S10", approval_scope="test", valid_for_seconds=30,
    )
    assert armed["orders_enabled"] is True
    assert control.status()["mode"] == "SIMULATION_STRATEGY_EXECUTION_ENABLED"
    assert control.status()["orders_enabled"] is True
    time.sleep(0.01)
    assert control.status()["orders_enabled"] is True


def test_runtime_control_never_arms_production(tmp_path: Path):
    control = RuntimeControl(tmp_path / "control.json", environment="production")
    try:
        control.arm_simulation_strategy(
            account_id="90000002", strategy_id="S10", approval_scope="test", valid_for_seconds=30,
        )
    except PermissionError:
        pass
    else:
        raise AssertionError("production control must not arm")
