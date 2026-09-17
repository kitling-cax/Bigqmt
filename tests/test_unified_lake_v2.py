import json
from pathlib import Path

import pytest

from kitling_bigqmt.unified_lake_v2 import (
    UnifiedLakeV2Error,
    evaluate_release_gates,
    initialize,
    load_contract,
)


def _contract(path: Path) -> Path:
    payload = {
        "schema_version": 2,
        "release_policy": {"copy_on_write": True, "required_gates": [
            "stock_raw", "etf_raw", "pit_adjustment", "universe_pit",
            "source_freshness", "service_health", "manifest_hash",
        ]},
        "safety": {"legacy_catalog_latest_modified": False},
        "research_channels": {"U25_ETF_RESEARCH_PIT": {"current_release": "fixed", "global_default": False}},
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_v2_initialization_is_idempotent_and_never_creates_legacy_latest(tmp_path):
    contract = _contract(tmp_path / "contract.json")
    first = initialize(tmp_path / "lake", contract)
    assert first["status"] == "INITIALIZED"
    root = tmp_path / "lake"
    assert (root / "v2" / "catalog" / "LATEST_RESEARCH.json").is_file()
    assert not (root / "catalog" / "LATEST.json").exists()
    second = initialize(root, contract)
    assert second["status"] == "ALREADY_INITIALIZED"
    assert second["global_latest_updated"] is False


def test_v2_refuses_contract_drift_after_creation(tmp_path):
    contract = _contract(tmp_path / "contract.json")
    initialize(tmp_path / "lake", contract)
    changed = json.loads(contract.read_text(encoding="utf-8"))
    changed["research_channels"]["GLOBAL_PIT_V2"] = {"current_release": "unsafe"}
    contract.write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(UnifiedLakeV2Error, match="different contract"):
        initialize(tmp_path / "lake", contract)


def test_global_release_gate_is_fail_closed():
    result = evaluate_release_gates({"stock_raw": "PASSED", "etf_raw": "PASSED"})
    assert result["publishable"] is False
    assert result["decision"] == "CANDIDATE_ONLY"
    all_passed = evaluate_release_gates({
        "stock_raw": "PASSED", "etf_raw": "PASSED", "pit_adjustment": "PASSED",
        "universe_pit": "PASSED", "source_freshness": "PASSED", "service_health": "PASSED",
        "manifest_hash": "PASSED",
    })
    assert all_passed["publishable"] is True


def test_contract_requires_copy_on_write(tmp_path):
    contract = _contract(tmp_path / "contract.json")
    payload = json.loads(contract.read_text(encoding="utf-8"))
    payload["release_policy"]["copy_on_write"] = False
    contract.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(UnifiedLakeV2Error, match="copy-on-write"):
        load_contract(contract)
