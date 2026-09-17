"""Profile-scoped, passwordless MiniQMT launcher for the native tray.

MiniQMT is kept as the primary data/trade baseline while the broker allows it.
It is launched only as ``XtMiniQmt.exe linkMini``: no password travels through
JSON, batch files, command-line arguments, logs, or the tray executable.

This utility never closes or restarts a terminal.  The tray may only request a
missing MiniQMT start, and records a process as *process evidence* rather than
claiming broker/account readiness.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kitling_bigqmt.qmt_launcher import QmtLauncherError, find_qmt_processes, open_qmt  # noqa: E402
from kitling_bigqmt.machine_config import load_tray_profiles  # noqa: E402


MINI_PROCESS_NAMES = ("XtMiniQmt.exe",)


def _profiles() -> dict[str, Any]:
    loaded = load_tray_profiles(ROOT)
    profiles = loaded.get("profiles")
    if not isinstance(profiles, dict):
        raise QmtLauncherError("tray_profiles.json has no profiles object")
    return profiles


def _profile(profile: str) -> dict[str, Any]:
    config = _profiles().get(profile)
    if not isinstance(config, dict) or not str(config.get("qmt_root") or "").strip():
        raise QmtLauncherError("unknown or incomplete tray profile: %s" % profile)
    mini = config.get("miniqmt_launch")
    if not isinstance(mini, dict) or not bool(mini.get("enabled")):
        raise QmtLauncherError("MiniQMT is disabled for profile: %s" % profile)
    return config


def _status(profile: str, config: dict[str, Any]) -> dict[str, Any]:
    processes = find_qmt_processes(str(config["qmt_root"]), names=MINI_PROCESS_NAMES)
    return {
        "profile": profile,
        "mode": "linkmini",
        "processes": [{"pid": pid, "name": name, "exe": exe} for pid, name, exe in processes],
        "status": "RUNNING" if processes else "STOPPED",
        "readiness": "PROCESS_ONLY" if processes else "STOPPED",
        "readiness_note": "MiniQMT process proof is not account/login or order-readiness proof.",
    }


def _emit(value: dict[str, Any], exit_code: int = 0) -> int:
    print(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
    return exit_code


def _close(profile: str, config: dict[str, Any]) -> dict[str, Any]:
    """Stop only this profile's MiniQMT process tree.

    The process list is already constrained to this exact installation path.
    ``/T`` includes MiniQMT-owned children such as ``miniquote.exe`` but never
    targets the separately-parented full-terminal ``XtItClient.exe``.  No
    force-kill fallback is used: an unexpected refusal remains visible to the
    operator instead of risking an unrelated terminal.
    """
    before = _status(profile, config)
    if before["status"] == "STOPPED":
        return {"result": "ALREADY_STOPPED", **before}
    stopped = []
    for process in before["processes"]:
        completed = subprocess.run(
            ["taskkill", "/PID", str(process["pid"]), "/T"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False,
        )
        if completed.returncode != 0:
            raise QmtLauncherError("MiniQMT stop refused: %s" % completed.stdout.strip())
        stopped.append(process["pid"])
    return {"result": "STOP_REQUESTED", "stopped_pids": stopped, **_status(profile, config)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="BigQMT tray MiniQMT passwordless launcher JSON API")
    parser.add_argument("action", choices=("status", "open", "close"))
    parser.add_argument("--profile", choices=("simulation", "production_readonly"), default="simulation")
    args = parser.parse_args(argv)
    try:
        config = _profile(args.profile)
        before = _status(args.profile, config)
        if args.action == "status":
            return _emit({"ok": True, "action": "status", **before})
        if args.action == "close":
            return _emit({"ok": True, "action": "close", **_close(args.profile, config)})
        if before["status"] == "RUNNING":
            return _emit({"ok": True, "action": "open", "result": "ALREADY_RUNNING", **before})
        # linkMini is the open-source, passwordless MiniQMT mode.  Do not wait
        # on FormulaServer here: that port is host-wide and can belong to a
        # BigQMT full terminal; only a MiniQMT process is claimed below.
        open_qmt(str(config["qmt_root"]), mode="linkmini", wait_ready=False)
        return _emit({"ok": True, "action": "open", "result": "SPAWNED", **_status(args.profile, config)})
    except (OSError, ValueError, json.JSONDecodeError, QmtLauncherError) as exc:
        return _emit({"ok": False, "action": args.action, "profile": args.profile, "error": str(exc)}, 2)


if __name__ == "__main__":
    raise SystemExit(main())
