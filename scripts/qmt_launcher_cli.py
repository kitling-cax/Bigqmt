"""Profile-scoped JSON command line interface for the BigQMT tray.

It starts only the terminal beneath the profile's configured QMT root.  It
never sends an order and deliberately defaults to the full-terminal ``exe``
mode: BigQMT Bridge strategies need ``XtItClient.exe``, not MiniQMT's
``linkMini`` mode.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kitling_bigqmt.qmt_launcher import (  # noqa: E402
    DEFAULT_READY_PORT,
    QmtLauncherError,
    close_qmt,
    find_qmt_processes,
    login_existing_qmt,
    open_qmt,
    port_is_listening,
    qmt_window_state,
    restart_qmt,
    session_is_locked,
)
from kitling_bigqmt.machine_config import load_tray_profiles  # noqa: E402
from kitling_bigqmt.qmt_credentials import QmtCredentialError, is_available as credential_available, read as read_credential  # noqa: E402


def _profiles() -> dict[str, Any]:
    loaded = load_tray_profiles(ROOT)
    profiles = loaded.get("profiles")
    if not isinstance(profiles, dict):
        raise QmtLauncherError("tray_profiles.json has no profiles object")
    return profiles


def _profile_config(profile: str) -> dict[str, Any]:
    config = _profiles().get(profile)
    if not isinstance(config, dict):
        raise QmtLauncherError("unknown tray profile: %s" % profile)
    if not str(config.get("qmt_root") or "").strip():
        raise QmtLauncherError("profile has no qmt_root: %s" % profile)
    return config


def _status(profile: str, config: dict[str, Any]) -> dict[str, Any]:
    root = str(config["qmt_root"])
    port = int((config.get("qmt_launch") or {}).get("ready_port") or DEFAULT_READY_PORT)
    # ``find_qmt_processes`` intentionally includes MiniQMT and its child
    # services for safe shutdown.  A BigQMT profile's readiness indicator must
    # not mistake a running ``XtMiniQmt.exe`` for a full terminal that can host
    # the embedded Bridge, so this status view is deliberately narrower.
    processes = find_qmt_processes(root, names=("XtItClient.exe",))
    port_listening = port_is_listening(port)
    locked = session_is_locked()
    qmt_options = config.get("qmt_launch") if isinstance(config.get("qmt_launch"), dict) else {}
    window_prefix = qmt_options.get("window_title_prefix")
    # FormulaServer is a host-wide QMT port.  When two QMT installations are
    # present it is useful corroborating evidence, but Bridge health remains
    # the profile-specific readiness authority in the tray.
    return {
        "profile": profile,
        "qmt_root": root,
        "process_running": bool(processes),
        "processes": [
            {"pid": pid, "name": name, "exe": exe}
            for pid, name, exe in processes
        ],
        "formula_server_port": port,
        "formula_server_listening": port_listening,
        "window_state": qmt_window_state(window_prefix),
        "session_locked": locked,
        "credential_available": credential_available(profile),
        # A process and FormulaServer listener are deliberately only process
        # evidence.  They both exist before a broker login has completed, and
        # 58600 is shared by full QMT installations on this machine.  The
        # tray must never represent this as a tradable or even account-ready
        # session; only a fresh profile-local Bridge RPC/snapshot may do that.
        "readiness": "PROCESS_ONLY" if processes else "STOPPED",
        "readiness_note": "Process/FormulaServer are not login evidence. Confirm this profile with a fresh Bridge RPC snapshot before treating the account as ready.",
        "status": "RUNNING" if processes else "STOPPED",
    }


def _credentials_for_login(profile: str) -> dict[str, str]:
    """Prefer an explicitly inherited environment only for this process.

    The regular tray path uses Windows Credential Manager.  Environment
    variables remain useful for a one-off manual diagnostic and are never
    echoed to stdout.
    """
    user = os.environ.get("BIGQMT_LOGIN_USER", "")
    password = os.environ.get("BIGQMT_LOGIN_PASSWORD", "")
    if user and password:
        return {"user": user, "password": password}
    return read_credential(profile)


def _print(value: dict[str, Any], exit_code: int = 0) -> int:
    print(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
    return exit_code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="BigQMT tray QMT launcher JSON API")
    parser.add_argument("action", choices=("status", "open", "close", "restart"))
    parser.add_argument("--profile", choices=("simulation", "production_readonly"), default="simulation")
    parser.add_argument("--mode", choices=("exe", "login", "bat"), default=None)
    parser.add_argument("--bat", default=None)
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--wait-ready", action="store_true", help="wait for FormulaServer instead of returning after spawn")
    args = parser.parse_args(argv)
    try:
        config = _profile_config(args.profile)
        qmt_options = config.get("qmt_launch") if isinstance(config.get("qmt_launch"), dict) else {}
        target = str(qmt_options.get("terminal_target") or "bigqmt_unchecked_independent_trading")
        if target != "bigqmt_unchecked_independent_trading":
            raise QmtLauncherError("full QMT launcher refuses non-BigQMT terminal_target: %s" % target)
        mode = args.mode or str(qmt_options.get("mode") or "exe")
        bat_path = args.bat or qmt_options.get("bat_path")
        window_title_prefix = qmt_options.get("window_title_prefix")
        root = str(config["qmt_root"])
        if args.action == "status":
            return _print({"ok": True, "action": "status", **_status(args.profile, config)})
        if args.action == "open":
            before = _status(args.profile, config)
            if before["process_running"]:
                # A previous safe attempt can leave the full terminal at its
                # login dialog.  Complete that existing dialog instead of
                # declaring it healthy merely because XtItClient.exe exists.
                if mode == "login":
                    login_existing_qmt(_credentials_for_login(args.profile), window_title_prefix)
                    return _print({"ok": True, "action": "open", "result": "LOGIN_EXISTING_TERMINAL", **_status(args.profile, config)})
                return _print({"ok": True, "action": "open", "result": "ALREADY_RUNNING", **before})
            credentials = None
            if mode == "login":
                credentials = _credentials_for_login(args.profile)
            open_qmt(
                root, mode=mode, bat_path=bat_path,
                ready_port=int(qmt_options.get("ready_port") or DEFAULT_READY_PORT),
                ready_timeout_seconds=args.timeout, wait_ready=args.wait_ready,
                credentials=credentials,
                window_title_prefix=window_title_prefix,
            )
            return _print({"ok": True, "action": "open", "result": "SPAWNED", **_status(args.profile, config)})
        if args.action == "close":
            closed = close_qmt(root)
            return _print({"ok": True, "action": "close", "closed_processes": closed, **_status(args.profile, config)})
        if args.action == "restart":
            credentials = None
            if mode == "login":
                credentials = _credentials_for_login(args.profile)
            restart_qmt(
                root, mode=mode, bat_path=bat_path,
                ready_port=int(qmt_options.get("ready_port") or DEFAULT_READY_PORT),
                ready_timeout_seconds=args.timeout, wait_ready=args.wait_ready,
                credentials=credentials,
                window_title_prefix=window_title_prefix,
            )
            return _print({"ok": True, "action": "restart", "result": "SPAWNED", **_status(args.profile, config)})
    except (OSError, ValueError, json.JSONDecodeError, QmtLauncherError, QmtCredentialError) as exc:
        return _print({"ok": False, "action": args.action, "profile": args.profile, "error": str(exc)}, 2)
    raise AssertionError("unreachable")


if __name__ == "__main__":
    raise SystemExit(main())
