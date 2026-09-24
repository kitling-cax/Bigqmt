"""Local, atomic installer for immutable strategy packages.

The installer stages a verified package under a host-local directory.  It does
not import the strategy into QMT, start a process, change a tray policy, or
enable orders.  Starting a strategy remains a separate local tray action.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_rel(value: object) -> Path:
    rel = Path(str(value or ""))
    if not rel.parts or rel.is_absolute() or ".." in rel.parts:
        raise ValueError("unsafe package artifact path")
    if any(part.lower() in {".env", "runtime_data", "logs", "outbox", ".git", "__pycache__"}
               for part in rel.parts):
        raise ValueError("runtime or secret path is not installable")
    return rel


def verify_package(package_dir: Path) -> dict[str, Any]:
    package_dir = Path(package_dir).resolve()
    manifest_path = package_dir / "MANIFEST.json"
    if not manifest_path.is_file():
        raise ValueError("MANIFEST.json is missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("manifest must be an object")
    safety = manifest.get("safety") or {}
    if safety.get("orders_enabled") is not False or safety.get("formal_account_allowed") is not False:
        raise ValueError("unsafe package flags")
    required = ("strategy_id", "version", "build_id", "artifacts")
    if any(not str(manifest.get(key) or "").strip() for key in required):
        raise ValueError("manifest missing required fields")
    if any(path.is_symlink() for path in package_dir.rglob("*")):
        raise ValueError("symlinks are not installable")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise ValueError("manifest artifacts are empty")
    for item in artifacts:
        if not isinstance(item, dict):
            raise ValueError("invalid manifest artifact")
        rel = _safe_rel(item.get("path"))
        artifact = (package_dir / rel).resolve()
        try:
            artifact.relative_to(package_dir)
        except ValueError as exc:
            raise ValueError("artifact escapes package directory") from exc
        if not artifact.is_file() or _sha256(artifact).lower() != str(item.get("sha256") or "").lower():
            raise ValueError(f"artifact checksum mismatch: {rel.as_posix()}")
    return {
        "strategy_id": str(manifest["strategy_id"]),
        "version": str(manifest["version"]),
        "build_id": str(manifest["build_id"]),
        "manifest_sha256": _sha256(manifest_path),
        "artifact_count": len(artifacts),
        "orders_enabled": False,
        "formal_account_allowed": False,
    }


def install_package(package_dir: Path, install_root: Path) -> dict[str, Any]:
    """Verify and atomically install one package, idempotently."""
    package_dir = Path(package_dir).resolve()
    install_root = Path(install_root).resolve()
    verified = verify_package(package_dir)
    destination = install_root / verified["strategy_id"] / verified["version"] / verified["build_id"]
    existing_manifest = destination / "MANIFEST.json"
    if existing_manifest.is_file() and _sha256(existing_manifest) == verified["manifest_sha256"]:
        return {**verified, "status": "ALREADY_INSTALLED", "install_dir": str(destination)}
    if destination.exists():
        raise ValueError("refusing to overwrite a different installed build")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{verified['build_id']}-staging-", dir=destination.parent))
    try:
        shutil.copytree(package_dir, staging / "package", symlinks=False)
        staged = staging / "package"
        os.replace(staged, destination)
        result = {
            **verified,
            "status": "INSTALLED",
            "install_dir": str(destination),
            "run_after_install": False,
        }
        (destination / "INSTALL_RESULT.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return result
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        if destination.exists():
            shutil.rmtree(destination, ignore_errors=True)
        raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)
