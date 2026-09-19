"""Build an immutable, local strategy package for the NAS release channel.

This publisher is deliberately offline: it reads the validated strategy
registry and a caller-supplied source directory, then writes a new release
directory and ZIP.  It never reads QMT/Redis, never writes a broker order and
fails closed on files that could contain machine secrets or runtime state.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
_SAFE_ID = re.compile(r"^[A-Za-z0-9._+-]+$")
_SENSITIVE_PARTS = {
    ".env", ".env.local", "machine.local.json", "credentials.json",
    "secrets.json", "authorized_keys", "runtime_data", "logs", "outbox",
}
_SENSITIVE_WORDS = ("password", "passwd", "secret", "credential", "token", "private_key", "authorization_key")


class PackageError(ValueError):
    """Raised when a package cannot be safely published."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_relative(path: Path) -> str:
    rel = path.as_posix()
    if not rel or rel.startswith("/") or ".." in path.parts:
        raise PackageError(f"unsafe artifact path: {rel}")
    lowered = [part.lower() for part in path.parts]
    if any(part in _SENSITIVE_PARTS for part in lowered):
        raise PackageError(f"sensitive/runtime path is not publishable: {rel}")
    if any(word in path.name.lower() for word in _SENSITIVE_WORDS):
        raise PackageError(f"sensitive-looking filename is not publishable: {rel}")
    return rel


def _validate_registry_entry(registry: dict[str, Any], strategy_id: str) -> dict[str, Any]:
    strategies = registry.get("strategies")
    if not isinstance(strategies, list):
        raise PackageError("strategy registry has no strategies list")
    matches = [item for item in strategies if isinstance(item, dict) and item.get("strategy_id") == strategy_id]
    if len(matches) != 1:
        raise PackageError(f"strategy_id must resolve to exactly one registry entry: {strategy_id}")
    entry = matches[0]
    if entry.get("formal_account_allowed") is not False:
        raise PackageError("formal_account_allowed must be false")
    if entry.get("execution_enabled") is True and entry.get("allowed_accounts") != ["99022040"]:
        raise PackageError("enabled package is restricted to simulation account 99022040")
    return entry


def _git_head() -> str | None:
    try:
        result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
                                capture_output=True, text=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    value = result.stdout.strip()
    return value if re.fullmatch(r"[0-9a-fA-F]{40}", value) else None


def build_package(*, strategy_id: str, version: str, build_id: str, source: Path,
                  output_root: Path, registry_path: Path, bridge_rpc_version: str = "0.3.26",
                  publisher_commit: str | None = None) -> dict[str, Any]:
    for label, value in (("strategy_id", strategy_id), ("version", version), ("build_id", build_id)):
        if not _SAFE_ID.fullmatch(value):
            raise PackageError(f"invalid {label}: {value}")
    if not source.is_dir():
        raise PackageError(f"source directory does not exist: {source}")
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    entry = _validate_registry_entry(registry, strategy_id)
    if entry.get("version") != version:
        raise PackageError(f"registry version {entry.get('version')} does not match requested {version}")

    destination = output_root / strategy_id / version / build_id
    if destination.exists():
        raise PackageError(f"refusing to overwrite existing release: {destination}")
    payload = destination / "payload"
    payload.mkdir(parents=True, exist_ok=False)
    files: list[dict[str, Any]] = []
    for source_path in sorted(source.rglob("*")):
        if source_path.is_symlink():
            raise PackageError(f"symlinks are not allowed in a release: {source_path}")
        if not source_path.is_file():
            continue
        rel = _safe_relative(source_path.relative_to(source))
        target = payload / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target)
        files.append({"path": f"payload/{rel}", "sha256": _sha256(target), "size": target.stat().st_size})
    if not files:
        raise PackageError("source directory contains no publishable files")

    (destination / "registry_entry.json").write_text(
        json.dumps(entry, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    files.append({"path": "registry_entry.json", "sha256": _sha256(destination / "registry_entry.json"),
                  "size": (destination / "registry_entry.json").stat().st_size})
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "strategy_family_id": str(strategy_id).split("_V", 1)[0],
        "strategy_id": strategy_id,
        "version": version,
        "build_id": build_id,
        "exclusive_group": str(entry.get("sleeve_id") or strategy_id),
        "bridge_rpc_version": bridge_rpc_version,
        "runtime": {"python": "3.12", "platforms": ["windows-x64"]},
        "artifacts": files,
        "published_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "publisher_commit": publisher_commit or _git_head() or "0000000",
        "backtest_report_path": "registry_entry.json",
        "safety": {"orders_enabled": False, "formal_account_allowed": False,
                   "source": "local_offline_builder", "nas_runtime_dependency": False},
    }
    manifest_path = destination / "MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    checksums = [f"{item['sha256']}  {item['path']}" for item in files]
    checksums.append(f"{_sha256(manifest_path)}  MANIFEST.json")
    (destination / "checksums.sha256").write_text("\n".join(checksums) + "\n", encoding="utf-8", newline="\n")

    zip_path = destination.parent / f"{strategy_id}-{version}-{build_id}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for item in sorted(destination.rglob("*")):
            if item.is_file():
                archive.write(item, arcname=f"{destination.name}/{item.relative_to(destination).as_posix()}")
    result = {"strategy_id": strategy_id, "version": version, "build_id": build_id,
              "release_dir": str(destination), "zip": str(zip_path),
              "manifest_sha256": _sha256(manifest_path), "artifact_count": len(files),
              "orders_enabled": False, "formal_account_allowed": False}
    (destination / "release_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Build an immutable BigQMT strategy package")
    parser.add_argument("--strategy-id", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--build-id", required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=ROOT / "releases" / "strategies")
    parser.add_argument("--registry", type=Path, default=ROOT / "config" / "strategy_registry.json")
    parser.add_argument("--bridge-rpc-version", default="0.3.26")
    args = parser.parse_args()
    try:
        print(json.dumps(build_package(strategy_id=args.strategy_id, version=args.version, build_id=args.build_id,
                                       source=args.source, output_root=args.output_root, registry_path=args.registry,
                                       bridge_rpc_version=args.bridge_rpc_version), ensure_ascii=False, indent=2))
        return 0
    except (OSError, json.JSONDecodeError, PackageError) as exc:
        print(json.dumps({"error": str(exc), "orders_enabled": False}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
