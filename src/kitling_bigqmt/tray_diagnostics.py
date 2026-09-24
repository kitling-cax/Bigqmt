"""Read-only diagnostics for a BigQMT Windows tray instance.

The diagnostic is deliberately independent of the notification-area icon.  It
is used when Explorer has not displayed an icon or a tray script has exited
before it can render one.  It never starts, stops, logs into, or sends any
command to QMT.
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .tray_health import check_profile


_PROFILES = {"simulation", "production_readonly"}


def _read_json_lines(path: Path, limit: int = 20) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    output: list[dict[str, Any]] = []
    for line in lines[-max(1, int(limit)):]:
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            output.append(value)
    return output


def _tail_text(path: Path, limit: int = 20) -> list[str]:
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()[-max(1, int(limit)):]
    except OSError:
        return []


def find_tray_processes(profile: str) -> list[dict[str, Any]]:
    """Return PowerShell-hosted or native EXE processes for this profile."""
    if os.name != "nt":
        return []
    exe_name = "BigQMT_Simulation.exe" if profile == "simulation" else "BigQMT_Production_ReadOnly.exe"
    command = (
        "$p=Get-CimInstance Win32_Process | Where-Object { $_.Name -in @('powershell.exe','pwsh.exe','%s') } "
        "| Select-Object ProcessId,Name,CommandLine,ExecutablePath; $p|ConvertTo-Json -Compress" % exe_name
    )
    try:
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
            text=True, capture_output=True, timeout=5, check=False,
        )
        raw = completed.stdout.strip()
        if completed.returncode != 0 or not raw:
            return []
        parsed = json.loads(raw)
        rows = parsed if isinstance(parsed, list) else [parsed]
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return []
    needle = "BigQMTTray.ps1"
    profile_needle = "-Profile " + profile
    result = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        line = str(row.get("CommandLine") or "")
        name = str(row.get("Name") or "")
        executable = str(row.get("ExecutablePath") or "")
        native_match = name.lower() == exe_name.lower() or executable.lower().endswith("\\" + exe_name.lower())
        powershell_match = needle.lower() in line.lower() and profile_needle.lower() in line.lower()
        if native_match or powershell_match:
            result.append({"pid": int(row.get("ProcessId") or 0), "name": name,
                           "command_line": line, "executable_path": executable})
    return result


def _diagnosis(processes: list[dict[str, Any]], launcher_events: list[dict[str, Any]],
               tray_events: list[dict[str, Any]], bootstrap_errors: list[str]) -> tuple[str, str]:
    if processes:
        return "TRAY_PROCESS_RUNNING", "托盘脚本进程仍在运行；若图标未出现，优先检查 Windows 通知区域隐藏图标与 Explorer。"
    if bootstrap_errors:
        return "TRAY_BOOTSTRAP_ERROR", "托盘脚本在界面初始化前报错；请查看 bootstrap_errors.log 的最后一条。"
    if any(str(row.get("event")) == "launcher_spawned" for row in launcher_events):
        return "TRAY_EXITED_AFTER_SPAWN", "启动器已创建托盘进程，但该进程当前不存在；请查看 tray_events.jsonl 的最后事件。"
    if any(str(row.get("event")) == "tray_started" for row in tray_events):
        return "TRAY_EXITED_AFTER_START", "托盘曾开始执行，但当前没有运行进程；请查看最后的 tray_stopped 或 PowerShell 异常记录。"
    return "NO_LAUNCH_ATTEMPT_RECORDED", "未发现本目录启动器审计记录；请确认双击的是本项目 tray 文件夹内对应的 CMD 启动器。"


def diagnose_tray(root: Path, profile: str, *, dashboard_port: int | None = None) -> dict[str, Any]:
    """Build and persist one read-only support report for a tray profile."""
    if profile not in _PROFILES:
        raise ValueError("unsupported profile")
    root = Path(root).resolve()
    audit = root / "runtime_data" / "audit" / profile
    events = _read_json_lines(audit / "tray_events.jsonl")
    launchers = _read_json_lines(audit / "tray_launcher.jsonl")
    bootstrap = _tail_text(audit / "tray_bootstrap_errors.log")
    child_stderr = _tail_text(audit / "tray_child_stderr.log")
    processes = find_tray_processes(profile)
    code, explanation = _diagnosis(processes, launchers, events, bootstrap)
    port = int(dashboard_port if dashboard_port is not None else (17890 if profile == "simulation" else 17891))
    report = {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "profile": profile,
        "safe_mode": "READ_ONLY_NO_QMT_ACTION",
        "diagnosis": {"code": code, "explanation": explanation},
        "tray_processes": processes,
        "recent_launcher_events": launchers,
        "recent_tray_events": events,
        "recent_bootstrap_errors": bootstrap,
        "recent_child_stderr": child_stderr,
        "service_health": check_profile(root, profile, dashboard_port=port, attempts=1),
    }
    try:
        audit.mkdir(parents=True, exist_ok=True)
        (audit / "tray_diagnostic_latest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        report["report_write_error"] = f"{type(exc).__name__}: {exc}"
    return report
