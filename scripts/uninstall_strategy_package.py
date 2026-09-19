"""Uninstall a locally installed strategy package.

This script is the local-only counterpart to ``strategy_installer``.  It never
touches the Coordinator SQLite queue, the NAS candidate library, the strategy
registry, or any QMT runtime configuration.  It only deletes the
``<install_root>/<strategy_id>/<version>/<build_id>/`` subtree that
``install_package`` previously created.

The tray gates invocations behind a password hash configured in
``machine.local.json::tray.delete_strategy_password_sha256``; this script does
not enforce that gate itself so the same uninstaller can be run from a future
maintenance task without bypassing the tray audit.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kitling_bigqmt.machine_config import load_machine_local  # noqa: E402


def _install_root() -> Path:
    machine = load_machine_local(ROOT)
    deploy = machine.get("strategy_deployment") if isinstance(machine.get("strategy_deployment"), dict) else {}
    raw = str(deploy.get("install_root") or "").strip()
    root = Path(raw) if raw else ROOT / "runtime_data" / "strategies" / "installed"
    return root.resolve()


def _safe_under(parent: Path, child: Path) -> Path:
    """Reject any path that escapes ``parent`` after symlink/relative resolution."""
    parent = parent.resolve()
    child_abs = child.resolve()
    try:
        child_abs.relative_to(parent)
    except ValueError as exc:
        raise ValueError("refusing to touch a path outside install_root: %s" % child) from exc
    return child_abs


def list_installed(install_root: Path | None = None) -> list[dict[str, str]]:
    """Return every installed build under ``install_root`` as a flat list."""
    root = (install_root or _install_root()).resolve()
    if not root.is_dir():
        return []
    out: list[dict[str, str]] = []
    for strategy_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        for version_dir in sorted(p for p in strategy_dir.iterdir() if p.is_dir()):
            for build_dir in sorted(p for p in version_dir.iterdir() if p.is_dir()):
                result_path = build_dir / "INSTALL_RESULT.json"
                if not result_path.is_file():
                    continue
                out.append({
                    "strategy_id": strategy_dir.name,
                    "version": version_dir.name,
                    "build_id": build_dir.name,
                    "install_dir": str(build_dir),
                })
    return out


def uninstall(strategy_id: str, version: str, build_id: str, install_root: Path | None = None) -> dict[str, Any]:
    root = (install_root or _install_root()).resolve()
    if not strategy_id or not version or not build_id:
        raise ValueError("strategy_id, version and build_id are all required")
    for component in (strategy_id, version, build_id):
        if "/" in component or "\\" in component or component in {".", ".."}:
            raise ValueError("unsafe identifier: %r" % component)
    target = _safe_under(root, root / strategy_id / version / build_id)
    if not target.exists():
        return {
            "status": "not_found",
            "strategy_id": strategy_id,
            "version": version,
            "build_id": build_id,
            "install_dir": str(target),
        }
    shutil.rmtree(target)
    # If the strategy_id and version parents are now empty, leave them as
    # breadcrumbs so the user can tell something was once installed there.
    return {
        "status": "uninstalled",
        "strategy_id": strategy_id,
        "version": version,
        "build_id": build_id,
        "install_dir": str(target),
        "orders_enabled": False,
        "run_after_install": False,
    }


def _emit(payload: dict[str, Any]) -> int:
    print(json.dumps(payload, ensure_ascii=False))
    return 0 if payload.get("status") in {"ok", "uninstalled", "not_found", "no_installed"} else 2


def main() -> int:
    parser = argparse.ArgumentParser(description="Uninstall a locally installed strategy build")
    parser.add_argument("--list", action="store_true", help="only list installed builds")
    parser.add_argument("--strategy-id", default="")
    parser.add_argument("--version", default="")
    parser.add_argument("--build-id", default="")
    parser.add_argument("--install-root", default="", help="override install_root (for tests)")
    args = parser.parse_args()

    install_root: Path | None = None
    if args.install_root:
        install_root = Path(args.install_root)

    try:
        if args.list:
            payload: dict[str, Any] = {
                "status": "ok",
                "install_root": str((install_root or _install_root()).resolve()),
                "installed": list_installed(install_root),
            }
            if not payload["installed"]:
                payload["status"] = "no_installed"
            return _emit(payload)
        if not args.strategy_id or not args.version or not args.build_id:
            return _emit({"status": "error", "reason": "strategy_id, version, build_id are required", "orders_enabled": False})
        return _emit(uninstall(args.strategy_id, args.version, args.build_id, install_root))
    except (OSError, ValueError) as exc:
        return _emit({"status": "error", "reason": str(exc), "orders_enabled": False})


if __name__ == "__main__":
    raise SystemExit(main())
