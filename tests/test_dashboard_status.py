import json
import tempfile
from pathlib import Path

from kitling_bigqmt.dashboard_status import _sleeve_metrics, _with_security_names, build_dashboard_status
from kitling_bigqmt.sleeve_accounting import SleeveAccounting
from kitling_bigqmt.state_store import RuntimeStateStore
from kitling_bigqmt.strategy_shadow import build_close_shadow_event


def test_dashboard_is_read_only_and_surfaces_runtime_blocker():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        progress = root / "progress"
        progress.mkdir()
        (progress / "current_status.json").write_text(json.dumps({
            "environment": "simulation", "stage": "P06", "stage_status": "IN_PROGRESS",
            "bridge": "UNAVAILABLE_BROKER_DISCONNECTED", "runtime_ownership": {"production_runtime": "BIGQMT_TRAY_ONLY"},
            "next_gate": "reconnect QMT",
        }), encoding="utf-8")
        (progress / "blockers.json").write_text(json.dumps({"blockers": [{"id": "QMT", "status": "ACTIVE"}]}), encoding="utf-8")
        (progress / "latest_tests.json").write_text(json.dumps({"tests": [{"name": "snapshot", "status": "BLOCKED"}]}), encoding="utf-8")
        status = build_dashboard_status(root)
        assert status["read_only"] is True
        assert status["orders_enabled"] is False
        assert status["order_actions_exposed"] is False
        assert status["active_blockers"] == [{"id": "QMT", "status": "ACTIVE"}]
        assert status["strategy_sleeves"] == []
        assert status["strategy_registry"] == []


def test_dashboard_exposes_sleeve_summaries_and_nav_series_read_only():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        progress = root / "progress"
        progress.mkdir()
        state = root / "state.sqlite3"
        audit = root / "audit"
        ledger = SleeveAccounting(RuntimeStateStore(state, audit))
        ledger.register_sleeve("A", 100_000)
        ledger.record_nav_snapshot("A", {}, "run-1", "2026-09-09T10:00:00+08:00")
        (progress / "current_status.json").write_text(json.dumps({
            "environment": "simulation", "stage": "P10", "stage_status": "IN_PROGRESS",
            "bridge": "RUNNING_READ_ONLY", "next_gate": "dashboard",
        }), encoding="utf-8")
        (progress / "blockers.json").write_text(json.dumps({"blockers": []}), encoding="utf-8")
        (progress / "latest_tests.json").write_text(json.dumps({"tests": []}), encoding="utf-8")
        config = root / "config"
        config.mkdir()
        (config / "host_gateway.simulation.json").write_text(json.dumps({
            "environment": "simulation", "account_id": "90000001", "account_type": "STOCK",
            "state_db": str(state), "audit_dir": str(audit),
        }), encoding="utf-8")
        (config / "strategy_registry.json").write_text(json.dumps({
            "strategies": [{"strategy_id": "A", "display_name": "Strategy A", "status": "SIMULATION_ONLY"}]
        }), encoding="utf-8")
        status = build_dashboard_status(root)
        assert status["read_only"] is True
        assert len(status["strategy_sleeves"]) == 1
        assert status["strategy_sleeves"][0]["summary"]["net_asset_value"] == 100_000
        assert status["strategy_sleeves"][0]["nav_series"][0]["valuation_run_id"] == "run-1"
        assert status["strategy_registry"][0]["strategy_id"] == "A"


def test_dashboard_max_drawdown_uses_prior_running_peak_not_a_future_peak():
    metrics = _sleeve_metrics(
        {"initial_capital": 100_000, "net_asset_value": 102_000, "total_pnl": 2000, "return_rate": 0.02, "positions": []},
        [
            {"net_asset_value": 101_000}, {"net_asset_value": 100_000},
            {"net_asset_value": 102_000},
        ],
        [],
    )
    assert metrics["maximum_drawdown"] == 1000 / 101000


def test_dashboard_attaches_security_name_to_strategy_owned_position():
    summary = _with_security_names(
        {"positions": [{"stock_code": "160723.SZ", "quantity": 100}]},
        {"160723.SZ": "嘉实原油（LOF）"},
    )
    assert summary["positions"][0]["display_name"] == "嘉实原油（LOF）"


def test_dashboard_exposes_local_close_shadow_without_order_actions():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        config = root / "config"
        config.mkdir()
        (config / "host_gateway.simulation.json").write_text(json.dumps({
            "environment": "simulation", "state_db": str(root / "state.sqlite3"),
            "audit_dir": str(root / "audit"), "account_id": "90000001",
        }), encoding="utf-8")
        for name in ("current_status.json", "blockers.json", "latest_tests.json", "security_names.json", "strategy_registry.json"):
            target = root / ("progress" if name in {"current_status.json", "blockers.json", "latest_tests.json"} else "config") / name
            target.parent.mkdir(exist_ok=True)
            target.write_text("{}", encoding="utf-8")
        store = RuntimeStateStore(root / "state.sqlite3", root / "audit")
        market = {"518880.SS": {"adjusted": [100.0 + index for index in range(25)], "raw": [100.0]},
                  "511880.SS": {"adjusted": [], "raw": [100.0]}}
        store.record_strategy_shadow_event(build_close_shadow_event("A", "20260908", market))
        status = build_dashboard_status(root)
        assert status["strategy_shadows"][0]["strategy_id"] == "A"
        assert status["strategy_shadows"][0]["orders_enabled"] is False
        assert status["order_actions_exposed"] is False


def test_dashboard_exposes_latest_lake_cycle_evidence_read_only(tmp_path: Path):
    root = tmp_path
    progress = root / "progress"
    progress.mkdir()
    (progress / "current_status.json").write_text(json.dumps({"environment": "simulation"}), encoding="utf-8")
    (progress / "blockers.json").write_text(json.dumps({"blockers": []}), encoding="utf-8")
    (progress / "latest_tests.json").write_text(json.dumps({"tests": []}), encoding="utf-8")
    config = root / "config"
    config.mkdir()
    state = root / "state.sqlite3"
    audit = root / "audit"
    (config / "host_gateway.simulation.json").write_text(json.dumps({
        "environment": "simulation", "account_id": "90000001", "state_db": str(state), "audit_dir": str(audit)
    }), encoding="utf-8")
    evidence = root / "runtime_data" / "evidence" / "simulation" / "lake_cycles"
    evidence.mkdir(parents=True)
    (evidence / "lake_cycle_20260909T010203Z.json").write_text(json.dumps({
        "status": "PASSED", "export": {"source_run_id": "run-1"},
        "retention_audit": {"run_count": 3, "candidate_count": 0, "missing_manifest_count": 0}
    }), encoding="utf-8")
    status = build_dashboard_status(root)
    assert status["lake_cycle"]["status"] == "PASSED"
    assert status["lake_cycle"]["run_count"] == 3
    assert status["lake_cycle"]["orders_enabled"] is False


def test_dashboard_projects_isolated_research_pit_without_global_latest(tmp_path: Path):
    root = tmp_path
    progress = root / "progress"
    progress.mkdir()
    for name in ("current_status.json", "blockers.json", "latest_tests.json"):
        (progress / name).write_text(json.dumps({"environment": "simulation"}), encoding="utf-8")
    config = root / "config"
    config.mkdir()
    (config / "host_gateway.simulation.json").write_text(json.dumps({"environment": "simulation"}), encoding="utf-8")
    candidate = root / "runtime_data" / "candidates" / "bigqmt_etf_research_pit_test"
    candidate.mkdir(parents=True)
    (candidate / "manifest.json").write_text(json.dumps({
        "release_id": "bigqmt_etf_research_pit_test", "rows": 10,
        "scope": {"codes": ["510300.SH"]},
    }), encoding="utf-8")

    status = build_dashboard_status(root)

    research = status["bigqmt_research_pit_release"]
    assert research["release_id"] == "bigqmt_etf_research_pit_test"
    assert research["status"] == "CANDIDATE_ONLY"
    assert research["global_latest_updated"] is False
    assert research["orders_enabled"] is False


def test_formal_dashboard_reads_only_formal_state_and_hides_simulation_strategy_data(tmp_path: Path):
    root = tmp_path
    config = root / "config"
    config.mkdir()
    formal_state = root / "formal.sqlite3"
    formal_audit = root / "formal_audit"
    simulation_state = root / "simulation.sqlite3"
    simulation_audit = root / "simulation_audit"
    (config / "host_gateway.production_readonly.json").write_text(json.dumps({
        "environment": "production", "account_id": "90000002", "account_type": "STOCK",
        "state_db": str(formal_state), "audit_dir": str(formal_audit),
    }), encoding="utf-8")
    (config / "host_gateway.simulation.json").write_text(json.dumps({
        "environment": "simulation", "account_id": "90000001",
        "state_db": str(simulation_state), "audit_dir": str(simulation_audit),
    }), encoding="utf-8")
    progress = root / "progress"
    progress.mkdir()
    (progress / "current_status.json").write_text(json.dumps({"bridge": "SIMULATION_ONLY"}), encoding="utf-8")
    (progress / "blockers.json").write_text(json.dumps({"blockers": [{"id": "SIM", "status": "ACTIVE"}]}), encoding="utf-8")
    (progress / "latest_tests.json").write_text(json.dumps({"tests": [{"name": "simulation", "status": "PASS"}]}), encoding="utf-8")
    simulation_ledger = SleeveAccounting(RuntimeStateStore(simulation_state, simulation_audit))
    simulation_ledger.register_sleeve("SIM_STRATEGY", 100_000)
    formal_store = RuntimeStateStore(formal_state, formal_audit)
    formal_store.record_snapshot("production", "formal-account", {
        "ping": {"data": {"version": "test"}},
        "asset": {"data": {"total_asset": 123456, "cash": 100000}},
        "positions": {"data": {}}, "orders": {"data": []}, "trades": {"data": []},
    })

    status = build_dashboard_status(root, "production_readonly")

    assert status["profile"] == "production_readonly"
    assert status["environment"] == "production"
    assert status["snapshot"]["total_asset"] == 123456
    assert status["snapshot"]["captured_at"]
    assert status["snapshot"]["capture_status"] == "PASSED"
    assert status["strategy_sleeves"] == []
    assert status["strategy_shadows"] == []
    assert status["strategy_registry"] == []
    assert status["active_blockers"] == []
    assert status["orders_enabled"] is False
    assert status["order_actions_exposed"] is False
