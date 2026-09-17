import json
from datetime import datetime, timezone
from pathlib import Path

from kitling_bigqmt.local_backup import create_local_backup
from kitling_bigqmt.state_store import RuntimeStateStore


def test_local_backup_creates_consistent_sqlite_manifest_and_bounded_audit(tmp_path: Path):
    root = tmp_path
    state = root / "state" / "simulation.sqlite3"
    audit = root / "audit" / "simulation"
    RuntimeStateStore(state, audit).record_snapshot("simulation", "account", {
        "ping": {"data": {"version": "test"}},
        "asset": {"data": {"cash": 1, "frozen_cash": 0, "market_value": 2, "total_asset": 3}},
        "positions": {"data": {}}, "orders": {"data": []}, "trades": {"data": []}, "quotes": {"data": {}},
    })
    (root / "config").mkdir()
    (root / "progress").mkdir()
    (root / "config" / "host_gateway.simulation.json").write_text(json.dumps({
        "state_db": str(state), "audit_dir": str(audit), "environment": "simulation",
    }), encoding="utf-8")
    for name in ("tray_profiles.json", "strategy_registry.json"):
        (root / "config" / name).write_text("{}", encoding="utf-8")
    (root / "progress" / "current_status.json").write_text("{}", encoding="utf-8")

    result = create_local_backup(root, "simulation", now=datetime(2026, 9, 10, tzinfo=timezone.utc))

    backup = Path(result["backup_dir"])
    assert result["status"] == "PASSED"
    assert result["orders_enabled"] is False
    assert (backup / "state.sqlite3").is_file()
    manifest = json.loads((backup / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["sqlite_integrity_check"] == "ok"
    assert all("/" in item["path"] or item["path"] == "state.sqlite3" for item in manifest["files"])
