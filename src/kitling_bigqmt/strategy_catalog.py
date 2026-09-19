"""Read-only scanner for immutable private strategy packages."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def library_root(project_root: Path) -> Path:
    configured = os.environ.get("BIGQMT_STRATEGY_LIBRARY_ROOT", "").strip()
    if configured:
        return Path(configured)
    if os.name == "nt":
        return project_root / "releases" / "strategies"
    return Path("/var/lib/kitling-bigqmt-coordinator/strategy-library")


def _scan_manifest(path: Path, root: Path) -> dict[str, Any]:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise ValueError("manifest must be an object")
        required = ("strategy_id", "version", "build_id", "artifacts", "safety")
        if any(not manifest.get(key) for key in required):
            raise ValueError("manifest missing required fields")
        safety = manifest.get("safety") or {}
        if safety.get("orders_enabled") is not False or safety.get("formal_account_allowed") is not False:
            raise ValueError("unsafe package flags")
        artifacts = manifest.get("artifacts")
        if not isinstance(artifacts, list) or not artifacts:
            raise ValueError("manifest artifacts are empty")
        checked = 0
        for item in artifacts:
            rel = Path(str(item.get("path") or ""))
            if rel.is_absolute() or ".." in rel.parts:
                raise ValueError("unsafe artifact path")
            artifact = path.parent / rel
            if not artifact.is_file() or _sha256(artifact).lower() != str(item.get("sha256") or "").lower():
                raise ValueError(f"artifact checksum mismatch: {rel.as_posix()}")
            checked += 1
        return {
            "strategy_id": str(manifest["strategy_id"]),
            "version": str(manifest["version"]),
            "build_id": str(manifest["build_id"]),
            "bridge_rpc_version": str(manifest.get("bridge_rpc_version") or ""),
            "artifact_count": checked,
            "manifest_sha256": _sha256(path),
            "package_path": path.parent.relative_to(root).as_posix(),
            "status": "READY",
            "orders_enabled": False,
            "formal_account_allowed": False,
        }
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        return {"package_path": path.parent.relative_to(root).as_posix(), "status": "INVALID",
                "reason": str(exc), "orders_enabled": False, "formal_account_allowed": False}


def list_candidates(project_root: Path) -> dict[str, Any]:
    root = library_root(project_root)
    entries: list[dict[str, Any]] = []
    if root.is_dir():
        for manifest in sorted(root.rglob("MANIFEST.json")):
            if manifest.is_symlink():
                continue
            entries.append(_scan_manifest(manifest, root))
    return {
        "status": "ok", "readonly": True, "orders_enabled": False,
        "library_available": root.is_dir(), "library_root": str(root),
        "candidates": entries, "push_supported": False, "install_supported": False,
        "control": "CATALOG_ONLY_NO_INSTALL_OR_ASSIGNMENT_WRITE",
    }
