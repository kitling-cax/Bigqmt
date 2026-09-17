"""Read-only portability checks for a copied BigQMT project."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import machine_config


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _check(name: str, passed: bool, detail: str) -> dict[str, str]:
    return {"name": name, "status": "PASS" if passed else "FAIL", "detail": detail}


def check_portable_deployment(root: Path, profile: str) -> dict[str, Any]:
    """Validate paths and fail-closed defaults without starting any service."""
    if profile not in {"simulation", "production_readonly"}:
        raise ValueError("unsupported profile")
    root = Path(root).resolve()
    checks: list[dict[str, str]] = []
    checks.append(_check("project_root", root.is_dir(), str(root)))
    for relative in (
        "tray/BigQMTTray.ps1", "tray/launch_simulation_tray.cmd", "tray/launch_production_readonly_tray.cmd",
        "tray/BigQMT_Simulation_90000001.exe", "tray/BigQMT_Production_ReadOnly_90000002.exe", "tray/BigQMT_native_tray_checksums.sha256",
        "scripts/qmt_launcher_cli.py", "scripts/manage_qmt_login_credential.py", "scripts/check_bridge_ping.py", "scripts/launch_tray_detached.py", "scripts/diagnose_tray.py",
        "src/kitling_bigqmt/qmt_launcher.py", "src/kitling_bigqmt/qmt_credentials.py", "src/kitling_bigqmt/bridge_probe.py", "src/kitling_bigqmt/tray_diagnostics.py",
        "requirements-tray.txt",
        "config/strategy_runtime_policy.json", "config/formal_strategy_admissions.json",
    ):
        checks.append(_check(f"file:{relative}", (root / relative).is_file(), relative))

    profiles_path = root / "config" / "tray_profiles.json"
    profiles_data = machine_config.load_tray_profiles(root)
    profiles = profiles_data.get("profiles") if isinstance(profiles_data.get("profiles"), dict) else {}
    tray_profile = profiles.get(profile) if isinstance(profiles, dict) else None
    checks.append(_check("tray_profile", isinstance(tray_profile, dict), str(profiles_path)))
    tray_profile = tray_profile if isinstance(tray_profile, dict) else {}
    qmt_root_value = str(tray_profile.get("qmt_root") or "")
    qmt_root = Path(qmt_root_value) if qmt_root_value else None
    checks.append(_check("qmt_root", qmt_root is not None and qmt_root.is_dir(), str(qmt_root) if qmt_root else "missing qmt_root"))
    checks.append(_check("qmt_python", qmt_root is not None and (qmt_root / "python").is_dir(), str(qmt_root / "python") if qmt_root else "missing qmt_root"))
    checks.append(_check("qmt_terminal_exe", qmt_root is not None and (qmt_root / "bin.x64" / "XtItClient.exe").is_file(),
                         str(qmt_root / "bin.x64" / "XtItClient.exe") if qmt_root else "missing qmt_root"))
    qmt_launch = tray_profile.get("qmt_launch") if isinstance(tray_profile.get("qmt_launch"), dict) else {}
    checks.append(_check("qmt_launch_mode", qmt_launch.get("mode") in {"exe", "login", "bat"},
                         "mode must be exe/login/bat; auto is forbidden for full QMT Bridge"))
    checks.append(_check("tray_order_lock", tray_profile.get("orders_enabled") is False, "orders_enabled must remain false"))
    tray_script = root / "tray" / "BigQMTTray.ps1"
    simulation_launcher = root / "tray" / "launch_simulation_tray.cmd"
    production_launcher = root / "tray" / "launch_production_readonly_tray.cmd"
    launcher_for_profile = simulation_launcher if profile == "simulation" else production_launcher
    checks.append(_check("tray_sta_guard", "requires an STA PowerShell host" in tray_script.read_text(encoding="utf-8") if tray_script.is_file() else False,
                         "tray script must reject non-STA hosts"))
    native_exe = "BigQMT_Simulation_90000001.exe" if profile == "simulation" else "BigQMT_Production_ReadOnly_90000002.exe"
    checks.append(_check("native_account_launcher", native_exe in launcher_for_profile.read_text(encoding="utf-8") if launcher_for_profile.is_file() else False,
                         "profile launcher must start only its dedicated native account EXE"))

    config_file = "host_gateway.simulation.json" if profile == "simulation" else "host_gateway.production_readonly.json"
    gateway_path = root / "config" / config_file
    gateway = machine_config.load_gateway(root, profile)
    checks.append(_check("gateway_config", bool(gateway), str(gateway_path)))
    expected_environment = "simulation" if profile == "simulation" else "production"
    checks.append(_check("gateway_environment", gateway.get("environment") == expected_environment, expected_environment))
    checks.append(_check("gateway_order_boundary", gateway.get("read_only") is True if profile == "production_readonly" else True,
                         "formal profile requires read_only=true" if profile == "production_readonly" else "simulation order admission is controlled separately"))
    state_db_value = str(gateway.get("state_db") or "")
    state_db = Path(state_db_value) if state_db_value else None
    checks.append(_check("state_db_parent", state_db is not None and state_db.parent.is_dir(), str(state_db.parent) if state_db else "missing state_db"))
    redis = gateway.get("redis") if isinstance(gateway.get("redis"), dict) else {}
    expected_redis = tray_profile.get("redis") if isinstance(tray_profile.get("redis"), dict) else {}
    checks.append(_check("redis_profile_match", all(redis.get(key) == expected_redis.get(key) for key in ("host", "port", "db")),
                         "host/port/db must match tray profile"))

    failures = [row for row in checks if row["status"] == "FAIL"]
    return {
        "profile": profile,
        "valid": not failures,
        "orders_enabled": False,
        "checks": checks,
        "failure_count": len(failures),
        "note": "read-only path/configuration validation only; it does not start QMT, Redis, Bridge, or a Dashboard",
    }
