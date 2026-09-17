import pytest

from kitling_bigqmt.coordinator_lease_projection import project_local_lease


def _preview():
    return {"mode": "readonly-preview", "accounts": [
        {"account_id": "90000001", "lease_state": "UNASSIGNED_READONLY", "current_executor": None,
         "fencing_token": None, "coordinator_epoch": 1,
         "candidates": [{"host_id": "192.0.2.105", "eligible": True, "health_reason": "HEALTHY_READONLY"}]},
        {"account_id": "90000002", "lease_state": "UNASSIGNED_READONLY", "current_executor": None,
         "fencing_token": None, "coordinator_epoch": 1,
         "candidates": [{"host_id": "192.0.2.105", "eligible": False, "health_reason": "HEALTHY_READONLY"}]},
    ]}


def test_projects_simulation_candidate_without_order_capability():
    result = project_local_lease(_preview(), "simulation", "192.0.2.105")
    assert result["candidate_eligible"] is True
    assert result["lease_state"] == "UNASSIGNED_READONLY"
    assert result["orders_enabled"] is False


def test_formal_candidate_is_never_reported_eligible():
    result = project_local_lease(_preview(), "production_readonly", "192.0.2.105")
    assert result["candidate_eligible"] is False


def test_rejects_non_preview_response():
    with pytest.raises(ValueError, match="unexpected"):
        project_local_lease({}, "simulation", "192.0.2.105")
