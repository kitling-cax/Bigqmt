import json
from pathlib import Path

from kitling_bigqmt import tray_health
from kitling_bigqmt.state_store import RuntimeStateStore


def _snapshot_bundle() -> dict:
    return {
        "ping": {"data": {"version": "0.3.26", "rpc_revision": "20260715-execution-snapshot-v1"}},
        "asset": {"data": {"cash": 1, "frozen_cash": 0, "market_value": 2, "total_asset": 3}},
        "positions": {"data": {"510300.SH": {"volume": 100, "available": 100, "cost": 4, "price": 5, "market_value": 500}}},
        "orders": {"data": []},
        "trades": {"data": []},
        "quotes": {"data": {"510300.SH": {"timetag": "20260908 09:30:00", "lastPrice": 5}}},
    }


def _record_snapshot(tmp_path: Path) -> str:
    state_db = tmp_path / "state.db"
    store = RuntimeStateStore(state_db, tmp_path / "audit")
    return store.record_snapshot("simulation", "90000001", _snapshot_bundle())


def test_snapshot_freshness_is_deferred_without_state_db():
    result = tray_health.snapshot_freshness({})
    assert result["status"] == "DEFERRED"
    assert "state_db" in result["detail"]


def test_snapshot_freshness_reports_degraded_when_no_snapshot_recorded(tmp_path: Path):
    result = tray_health.snapshot_freshness({"state_db": str(tmp_path / "state.db"), "audit_dir": str(tmp_path / "audit")})
    assert result["status"] == "DEGRADED"
    assert "no persisted Bridge snapshot" in result["detail"]


def test_snapshot_freshness_passes_within_threshold_and_exposes_age(tmp_path: Path):
    run_id = _record_snapshot(tmp_path)
    result = tray_health.snapshot_freshness({"state_db": str(tmp_path / "state.db"), "audit_dir": str(tmp_path / "audit")})
    assert result["status"] == "PASS"
    assert result["fresh"] is True
    assert result["latest_run_id"] == run_id
    assert result["age_seconds"] < result["max_age_seconds"]
    assert result["max_age_seconds"] == 4500.0
    assert "max_age_seconds=4500" in result["detail"]


def test_snapshot_freshness_degrades_when_snapshot_exceeds_threshold(tmp_path: Path):
    _record_snapshot(tmp_path)
    result = tray_health.snapshot_freshness({
        "state_db": str(tmp_path / "state.db"),
        "audit_dir": str(tmp_path / "audit"),
        "bridge_snapshot_max_age_seconds": 0,
    })
    assert result["status"] == "DEGRADED"
    assert result["fresh"] is False
    assert result["max_age_seconds"] == 0.0


def test_tray_health_is_fail_closed_when_profile_config_is_missing(tmp_path: Path):
    result = tray_health.check_profile(tmp_path, "simulation")
    assert result["overall"] == "FAIL_CLOSED"
    assert result["orders_enabled"] is False
    assert result["execution_consumer_enabled"] is False


def test_tray_health_checks_formal_dashboard_and_keeps_lock_closed(tmp_path: Path, monkeypatch):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "host_gateway.production_readonly.json").write_text(
        json.dumps({"environment": "production", "redis": {"host": "127.0.0.1", "port": 6380, "db": 5}}),
        encoding="utf-8",
    )
    (tmp_path / "runtime_data" / "control" / "production_readonly").mkdir(parents=True)
    (tmp_path / "runtime_data" / "control" / "production_readonly" / "runtime_control.json").write_text(
        json.dumps({"environment": "production", "orders_enabled": False, "execution_consumer_enabled": False}),
        encoding="utf-8",
    )
    monkeypatch.setattr(tray_health, "_redis_health", lambda *_args: {"name": "redis", "status": "PASS"})
    monkeypatch.setattr(tray_health, "_bridge_snapshot_health", lambda *_args: {"name": "bridge_snapshot", "status": "PASS"})
    monkeypatch.setattr(tray_health, "_dashboard_health", lambda *_args: {"name": "dashboard", "status": "PASS"})
    result = tray_health.check_profile(tmp_path, "production_readonly")
    assert result["overall"] == "HEALTHY"
    assert result["orders_enabled"] is False
    assert all(item["status"] != "DEFERRED" for item in result["checks"])
