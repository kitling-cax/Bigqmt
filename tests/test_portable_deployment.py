import json
from pathlib import Path

from kitling_bigqmt.portable_deployment import check_portable_deployment


def _write_profile(root: Path, *, formal: bool) -> None:
    qmt_root = root / "qmt"
    (qmt_root / "python").mkdir(parents=True)
    (qmt_root / "bin.x64").mkdir()
    (qmt_root / "bin.x64" / "XtItClient.exe").write_bytes(b"placeholder")
    (root / "tray").mkdir()
    (root / "tray" / "BigQMTTray.ps1").write_text("requires an STA PowerShell host", encoding="utf-8")
    (root / "tray" / "launch_simulation_tray.cmd").write_text("BigQMT_Simulation.exe", encoding="utf-8")
    (root / "tray" / "launch_production_readonly_tray.cmd").write_text("BigQMT_Production_ReadOnly.exe", encoding="utf-8")
    for name in ("BigQMT_Simulation.exe", "BigQMT_Production_ReadOnly.exe", "BigQMT_native_tray_checksums.sha256"):
        (root / "tray" / name).write_bytes(b"placeholder")
    (root / "scripts").mkdir()
    for name in ("qmt_launcher_cli.py", "manage_qmt_login_credential.py", "check_bridge_ping.py", "launch_tray_detached.py", "diagnose_tray.py"):
        (root / "scripts" / name).write_text("placeholder", encoding="utf-8")
    package = root / "src" / "kitling_bigqmt"
    package.mkdir(parents=True)
    for name in ("qmt_launcher.py", "qmt_credentials.py", "bridge_probe.py", "tray_diagnostics.py"):
        (package / name).write_text("placeholder", encoding="utf-8")
    (root / "requirements-tray.txt").write_text("psutil>=5.9\n", encoding="utf-8")
    (root / "config").mkdir()
    profile = "production_readonly" if formal else "simulation"
    environment = "production" if formal else "simulation"
    redis = {"host": "127.0.0.1", "port": 6380 if formal else 6379, "db": 5}
    (root / "config" / "tray_profiles.json").write_text(json.dumps({"profiles": {
        profile: {"qmt_root": str(qmt_root), "redis": redis, "orders_enabled": False,
                  "qmt_launch": {"mode": "exe"}}
    }}), encoding="utf-8")
    (root / "config" / "strategy_runtime_policy.json").write_text("{}", encoding="utf-8")
    (root / "config" / "formal_strategy_admissions.json").write_text("{}", encoding="utf-8")
    state_dir = root / "state"
    state_dir.mkdir()
    (root / "config" / ("host_gateway.production_readonly.json" if formal else "host_gateway.simulation.json")).write_text(json.dumps({
        "environment": environment, "state_db": str(state_dir / "runtime.sqlite3"), "redis": redis,
        **({"read_only": True} if formal else {}),
    }), encoding="utf-8")


def test_portable_preflight_accepts_fail_closed_profile(tmp_path: Path):
    _write_profile(tmp_path, formal=True)
    result = check_portable_deployment(tmp_path, "production_readonly")
    assert result["valid"] is True
    assert result["orders_enabled"] is False


def test_portable_preflight_rejects_unlocked_tray_profile(tmp_path: Path):
    _write_profile(tmp_path, formal=False)
    profile_path = tmp_path / "config" / "tray_profiles.json"
    content = json.loads(profile_path.read_text(encoding="utf-8"))
    content["profiles"]["simulation"]["orders_enabled"] = True
    profile_path.write_text(json.dumps(content), encoding="utf-8")
    result = check_portable_deployment(tmp_path, "simulation")
    assert result["valid"] is False
    assert any(item["name"] == "tray_order_lock" and item["status"] == "FAIL" for item in result["checks"])
