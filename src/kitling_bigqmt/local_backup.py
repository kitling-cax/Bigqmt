"""Local, append-only backup creation for BigQMT runtime evidence."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _copy_file(source: Path, destination: Path, manifest_path: str) -> dict[str, Any]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return {"path": manifest_path, "bytes": destination.stat().st_size, "sha256": _sha256(destination)}


def create_local_backup(root: Path, profile: str, audit_days: int = 14, now: datetime | None = None) -> dict[str, Any]:
    """Create a consistent SQLite copy and bounded local evidence backup.

    The operation never deletes source or destination data, calls neither QMT
    nor Redis, and retains no order capability.
    """
    if profile not in {"simulation", "production_readonly"}:
        raise ValueError("unsupported profile")
    if audit_days < 1:
        raise ValueError("audit_days must be positive")
    root = Path(root).resolve()
    config_name = "host_gateway.simulation.json" if profile == "simulation" else "host_gateway.production_readonly.json"
    config_path = root / "config" / config_name
    from . import machine_config
    try:
        config = machine_config.load_gateway(root, profile)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid gateway config: {exc}") from exc
    state_path = Path(str(config.get("state_db") or ""))
    if not state_path.is_file():
        raise ValueError("state database is unavailable")

    now = now or datetime.now(timezone.utc)
    backup_id = now.strftime("%Y%m%dT%H%M%SZ")
    destination = root / "runtime_data" / "backups" / profile / backup_id
    if destination.exists():
        raise ValueError(f"backup destination already exists: {destination}")
    destination.mkdir(parents=True)
    files: list[dict[str, Any]] = []
    sqlite_destination = destination / "state.sqlite3"
    source_db = sqlite3.connect(str(state_path))
    try:
        target_db = sqlite3.connect(str(sqlite_destination))
        try:
            source_db.backup(target_db)
        finally:
            target_db.close()
    finally:
        source_db.close()
    files.append({"path": "state.sqlite3", "bytes": sqlite_destination.stat().st_size, "sha256": _sha256(sqlite_destination)})

    for source in (config_path, root / "config" / "tray_profiles.json", root / "config" / "strategy_registry.json", root / "progress" / "current_status.json"):
        if source.is_file():
            files.append(_copy_file(source, destination / "config_and_status" / source.name, f"config_and_status/{source.name}"))

    audit_root = Path(str(config.get("audit_dir") or ""))
    cutoff = now - timedelta(days=audit_days)
    audit_count = 0
    if audit_root.is_dir():
        for source in sorted(audit_root.rglob("*.jsonl")):
            modified = datetime.fromtimestamp(source.stat().st_mtime, tz=timezone.utc)
            if modified >= cutoff:
                relative = source.relative_to(audit_root)
                files.append(_copy_file(source, destination / "audit" / relative, f"audit/{relative.as_posix()}"))
                audit_count += 1

    verification = sqlite3.connect(str(sqlite_destination)).execute("PRAGMA integrity_check").fetchone()[0]
    manifest = {
        "schema_version": 1,
        "backup_id": backup_id,
        "profile": profile,
        "created_at": now.isoformat(),
        "read_only_source": True,
        "orders_enabled": False,
        "broker_call_made": False,
        "audit_days": audit_days,
        "audit_file_count": audit_count,
        "sqlite_integrity_check": verification,
        "files": files,
    }
    (destination / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"status": "PASSED" if verification == "ok" else "FAILED", "backup_dir": str(destination), **manifest}
