import pytest

from pathlib import Path

from kitling_bigqmt.execution_admission import (
    ADMITTED_REASON,
    ExecutionAdmissionDenied,
    evaluate_execution_admission,
    require_execution_admission,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
STRATEGY_ID = "S10_D1_U25_TEST_V1_1_15"


def _armed(**overrides):
    value = {
        "environment": "SIMULATION",
        "mode": "SIMULATION_STRATEGY_EXECUTION_WINDOW",
        "account_id": "90000001",
        "strategy_id": STRATEGY_ID,
        "orders_enabled": True,
        "execution_consumer_enabled": True,
        "valid_until_epoch": 200.0,
    }
    value.update(overrides)
    return value


def _designation(**overrides):
    value = {
        "reachable": True,
        "eligible": True,
        "lease_state": "UNASSIGNED_READONLY",
        "reason": "HEALTHY_READONLY",
    }
    value.update(overrides)
    return value


def _admit(**overrides):
    kwargs = {
        "host_id": "192.0.2.105",
        "strategy_id": STRATEGY_ID,
        "authorization": _armed(),
        "designation": _designation(),
        "now_epoch": 100.0,
    }
    kwargs.update(overrides)
    return evaluate_execution_admission("simulation", **kwargs)


def test_simulation_with_all_signals_is_admitted_without_standing_switch():
    verdict = _admit()
    assert verdict["allowed"] is True
    assert verdict["reason"] == ADMITTED_REASON
    assert verdict["orders_enabled"] is False
    assert verdict["standing_order_switch_open"] is False
    assert verdict["account_id"] == "90000001"


def test_production_account_is_denied_before_any_other_signal():
    verdict = evaluate_execution_admission(
        "production_readonly",
        host_id="192.0.2.105",
        strategy_id=STRATEGY_ID,
        authorization=_armed(account_id="90000002"),
        designation=_designation(),
        now_epoch=100.0,
    )
    assert verdict["allowed"] is False
    assert verdict["reason"] == "PRODUCTION_READ_ONLY"


def test_unknown_profile_is_denied():
    verdict = evaluate_execution_admission("production", now_epoch=100.0)
    assert verdict["allowed"] is False
    assert verdict["reason"].startswith("ACCOUNT_POLICY_REJECTED")


def test_account_mismatch_between_profile_and_caller_is_denied():
    verdict = evaluate_execution_admission(
        "simulation", account_id="90000002", now_epoch=100.0
    )
    assert verdict["allowed"] is False
    assert verdict["reason"].startswith("ACCOUNT_POLICY_REJECTED")


def test_missing_local_window_is_denied():
    verdict = _admit(authorization=None)
    assert verdict["allowed"] is False
    assert verdict["reason"] == "LOCAL_AUTHORIZATION_MISSING"


def test_locked_local_control_is_denied():
    locked = {"environment": "simulation", "mode": "READ_ONLY_LOCKED",
              "orders_enabled": False, "execution_consumer_enabled": False}
    verdict = _admit(authorization=locked)
    assert verdict["allowed"] is False
    assert verdict["reason"] == "LOCAL_AUTHORIZATION_NOT_ARMED"


def test_expired_local_window_is_denied():
    verdict = _admit(authorization=_armed(valid_until_epoch=50.0))
    assert verdict["allowed"] is False
    assert verdict["reason"] == "LOCAL_AUTHORIZATION_EXPIRED"


def test_local_window_bound_to_another_account_is_denied():
    verdict = _admit(authorization=_armed(account_id="90000002"))
    assert verdict["allowed"] is False
    assert verdict["reason"] == "LOCAL_AUTHORIZATION_ACCOUNT_MISMATCH"


def test_local_window_bound_to_another_strategy_is_denied():
    verdict = _admit(authorization=_armed(strategy_id="S10_D1_OTHER_V1_1_15"))
    assert verdict["allowed"] is False
    assert verdict["reason"] == "LOCAL_AUTHORIZATION_STRATEGY_MISMATCH"


def test_unreachable_coordinator_denies_even_with_an_armed_window():
    verdict = _admit(designation={"reachable": False, "eligible": False, "reason": "URLError"})
    assert verdict["allowed"] is False
    assert verdict["reason"] == "COORDINATOR_UNREACHABLE"
    verdict_without_designation = _admit(designation=None)
    assert verdict_without_designation["allowed"] is False
    assert verdict_without_designation["reason"] == "COORDINATOR_UNREACHABLE"


def test_host_not_designated_as_executor_is_denied():
    verdict = _admit(designation=_designation(eligible=False, reason="HOST_NOT_ELIGIBLE"))
    assert verdict["allowed"] is False
    assert verdict["reason"] == "COORDINATOR_DENIES_HOST"
    assert verdict["coordinator_reason"] == "HOST_NOT_ELIGIBLE"


def test_valid_lease_still_cannot_open_execution_in_this_milestone():
    lease = {
        "schema_version": 1,
        "account_id": "90000001",
        "host_id": "192.0.2.105",
        "mode": "ACTIVE_EXECUTOR",
        "fencing_token": 7,
        "coordinator_epoch": 3,
        "expires_at": 200.0,
    }
    verdict = _admit(lease_envelope=lease, trusted_transport=True)
    assert verdict["allowed"] is False
    assert verdict["reason"] == "LEASED_EXECUTION_NOT_ENABLED_IN_M03"
    assert verdict["lease_evaluated"] is True


def test_require_execution_admission_raises_with_the_verdict():
    with pytest.raises(ExecutionAdmissionDenied) as caught:
        require_execution_admission(
            "simulation", host_id="192.0.2.105", authorization=_armed(),
            designation=_designation(), now_epoch=100.0, lease_envelope={}, trusted_transport=True,
        )
    assert caught.value.reason == "unsupported lease schema"
    assert caught.value.verdict["allowed"] is False


def test_require_execution_admission_passes_the_happy_path():
    verdict = require_execution_admission(
        "simulation", host_id="192.0.2.105", strategy_id=STRATEGY_ID,
        authorization=_armed(), designation=_designation(), now_epoch=100.0,
    )
    assert verdict["allowed"] is True


def test_every_local_order_entry_point_calls_the_admission_gate():
    entry_points = [
        PROJECT_ROOT / "scripts" / "run_v1_1_15_simulation_cycle.py",
        PROJECT_ROOT / "scripts" / "submit_v1_1_15_simulation_entry.py",
        PROJECT_ROOT / "scripts" / "run_one_time_510300_simulation_test.py",
    ]
    for path in entry_points:
        source = path.read_text(encoding="utf-8")
        assert "from kitling_bigqmt.execution_admission import" in source, path.name
        assert "require_admission_for_root(" in source, path.name
