"""List or remove host-local immutable strategy installs.

This is intentionally a small local-management command used by the native
tray.  It never starts a strategy, changes an order lock, or touches the NAS
candidate library.  The tray performs the user/password confirmation before
calling the remove form of this command.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def install_root() -> Path:
    return ROOT / "runtime_data" / "strategies" / "installed"


def _entries() -> list[dict[str, str]]:
    root = install_root()
    result: list[dict[str, str]] = []
    if not root.is_dir():
        return result
    for manifest_path in sorted(root.glob("*/*/*/MANIFEST.json")):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if not isinstance(manifest, dict):
                continue
            strategy_id = str(manifest.get("strategy_id") or "").strip()
            version = str(manifest.get("version") or "").strip()
            build_id = str(manifest.get("build_id") or "").strip()
            if not strategy_id or not version or not build_id:
                continue
            if manifest.get("safety", {}).get("orders_enabled") is not False:
                continue
            result.append({
                "strategy_id": strategy_id,
                "version": version,
                "build_id": build_id,
                "artifact_count": str(len(manifest.get("artifacts") or [])),
                "install_dir": str(manifest_path.parent),
            })
        except (OSError, ValueError, json.JSONDecodeError, AttributeError):
            continue
    return result


def _safe_target(strategy_id: str, version: str, build_id: str) -> Path:
    values = (strategy_id, version, build_id)
    if any(not value or value in {".", ".."} or "/" in value or "\\" in value for value in values):
        raise ValueError("invalid strategy install identity")
    target = (install_root() / strategy_id / version / build_id).resolve()
    target.relative_to(install_root().resolve())
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description="List or remove local strategy installs")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--strategy-id")
    parser.add_argument("--version")
    parser.add_argument("--build-id")
    args = parser.parse_args()

    if args.list:
        print(json.dumps({"status": "ok", "installed": _entries(), "orders_enabled": False}, ensure_ascii=False))
        return 0
    if not all((args.strategy_id, args.version, args.build_id)):
        parser.error("--strategy-id, --version and --build-id are required unless --list is used")
    try:
        target = _safe_target(args.strategy_id, args.version, args.build_id)
    except ValueError as exc:
        print(json.dumps({"status": "rejected", "reason": str(exc), "orders_enabled": False}, ensure_ascii=False))
        return 2
    manifest = target / "MANIFEST.json"
    if not target.is_dir() or not manifest.is_file():
        print(json.dumps({"status": "not_found", "strategy_id": args.strategy_id,
                          "version": args.version, "build_id": args.build_id,
                          "orders_enabled": False}, ensure_ascii=False))
        return 0
    shutil.rmtree(target)
    # Clean only empty identity directories; never remove the install root or
    # another strategy's build.
    for parent in (target.parent, target.parent.parent):
        try:
            if parent != install_root() and parent.is_dir() and not any(parent.iterdir()):
                parent.rmdir()
        except OSError:
            pass
    print(json.dumps({"status": "uninstalled", "strategy_id": args.strategy_id,
                      "version": args.version, "build_id": args.build_id,
                      "orders_enabled": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
