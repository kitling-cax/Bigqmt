"""Start one BigQMT Windows tray process outside the caller's job tree.

The Tray is a desktop-resident Windows Forms process.  Starting PowerShell as
a normal child of a terminal, service wrapper, or development host can cause
Windows to close it together with that parent.  This launcher uses the same
detached-process flags as the QMT terminal launcher, while preserving a
profile-specific STA PowerShell command.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
import subprocess
import sys
from pathlib import Path


def _powershell_exe() -> str:
    system_root = os.environ.get("SystemRoot", r"C:\\Windows")
    candidate = Path(system_root) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    return str(candidate) if candidate.is_file() else "powershell.exe"


def _audit(root: Path, profile: str, event: str, **detail: object) -> None:
    """Record launcher handoff before the detached child exists."""
    try:
        path = root / "runtime_data" / "audit" / profile / "tray_launcher.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {"event_time": datetime.now(timezone.utc).isoformat(), "event": event, "profile": profile, **detail}
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    except OSError:
        # A launch attempt must still return a useful process-level result if
        # its diagnostic directory is temporarily unavailable.
        pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Launch one detached BigQMT tray UI")
    parser.add_argument("--profile", choices=("simulation", "production_readonly"), required=True)
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    root = args.project_root.resolve()
    script = root / "tray" / "BigQMTTray.ps1"
    if not script.is_file():
        _audit(root, args.profile, "launcher_blocked", reason="missing tray script", path=str(script))
        print(json.dumps({"ok": False, "error": "missing tray script", "path": str(script)}))
        return 2
    command = [
        _powershell_exe(), "-STA", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden",
        "-File", str(script), "-Profile", args.profile, "-ProjectRoot", str(root),
    ]
    audit_dir = root / "runtime_data" / "audit" / args.profile
    audit_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = audit_dir / "tray_child_stdout.log"
    stderr_path = audit_dir / "tray_child_stderr.log"
    # ``DETACHED_PROCESS`` makes Windows PowerShell occasionally exit before
    # the NotifyIcon message loop is established (the launcher still reports
    # a PID, which is misleading for an unattended deployment).  A hidden
    # window plus a new process group is sufficient to detach the tray from
    # the caller while preserving the desktop window station required by
    # System.Windows.Forms.NotifyIcon.
    flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200) if os.name == "nt" else 0
    try:
        with stdout_path.open("a", encoding="utf-8") as stdout, stderr_path.open("a", encoding="utf-8") as stderr:
            stdout.write("\n--- tray launch %s ---\n" % datetime.now(timezone.utc).isoformat())
            stderr.write("\n--- tray launch %s ---\n" % datetime.now(timezone.utc).isoformat())
            stdout.flush()
            stderr.flush()
            process = subprocess.Popen(
                command,
                cwd=str(root),
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                creationflags=flags,
            )
    except OSError as exc:
        _audit(root, args.profile, "launcher_failed", error="%s: %s" % (type(exc).__name__, exc))
        print(json.dumps({"ok": False, "error": "%s: %s" % (type(exc).__name__, exc)}))
        return 2
    _audit(root, args.profile, "launcher_spawned", pid=process.pid, detached=os.name == "nt",
           stdout_log=str(stdout_path), stderr_log=str(stderr_path))
    print(json.dumps({"ok": True, "profile": args.profile, "pid": process.pid, "detached": os.name == "nt"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
