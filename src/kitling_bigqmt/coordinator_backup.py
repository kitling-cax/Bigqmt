"""Safe SQLite online-backup helpers for Coordinator shadow preparation."""
from __future__ import annotations

import hashlib
import os
import sqlite3
from pathlib import Path


class CoordinatorBackupError(RuntimeError):
    pass


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_database(path: str | Path) -> dict[str, object]:
    database = Path(path)
    if not database.is_file():
        raise CoordinatorBackupError("database file is missing")
    try:
        with sqlite3.connect(f"file:{database.resolve().as_posix()}?mode=ro", uri=True) as db:
            integrity = str(db.execute("PRAGMA integrity_check").fetchone()[0])
            schema_version = int(db.execute("PRAGMA user_version").fetchone()[0])
    except sqlite3.Error as exc:
        raise CoordinatorBackupError("database cannot be read") from exc
    if integrity.lower() != "ok":
        raise CoordinatorBackupError("database integrity check failed")
    return {"database": str(database), "sha256": sha256_file(database), "integrity_check": integrity, "schema_version": schema_version}


def create_online_backup(source: str | Path, destination: str | Path, *, overwrite: bool = False) -> dict[str, object]:
    """Copy a consistent SQLite snapshot without copying a live WAL file."""
    source_path, destination_path = Path(source), Path(destination)
    if not source_path.is_file():
        raise CoordinatorBackupError("source database is missing")
    if destination_path.exists() and not overwrite:
        raise CoordinatorBackupError("destination already exists")
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    temp = destination_path.with_name(destination_path.name + ".partial")
    if temp.exists():
        temp.unlink()
    destination_db: sqlite3.Connection | None = None
    try:
        # Use explicit close calls before rename.  On Windows, a context
        # manager commits but can retain a SQLite handle long enough for
        # os.replace to fail with WinError 32.
        with sqlite3.connect(f"file:{source_path.resolve().as_posix()}?mode=ro", uri=True) as source_db:
            destination_db = sqlite3.connect(temp)
            source_db.backup(destination_db)
            destination_db.commit()
            destination_db.close()
            destination_db = None
    except sqlite3.Error as exc:
        if destination_db is not None:
            destination_db.close()
        if temp.exists():
            temp.unlink()
        raise CoordinatorBackupError("SQLite online backup failed") from exc
    os.replace(temp, destination_path)
    return verify_database(destination_path)


def prepare_shadow_database(source: str | Path, destination: str | Path) -> dict[str, object]:
    """Create a shadow database and invalidate every inherited lease.

    This intentionally does not alter the source database.  The shadow service
    remains unable to issue leases even after this cleanup.
    """
    result = create_online_backup(source, destination, overwrite=True)
    try:
        with sqlite3.connect(destination) as db:
            existing = db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='account_leases'"
            ).fetchone()
            invalidated = 0
            if existing:
                invalidated = int(db.execute("SELECT COUNT(*) FROM account_leases").fetchone()[0])
                db.execute("UPDATE account_leases SET expires_at=0")
                db.commit()
    except sqlite3.Error as exc:
        raise CoordinatorBackupError("cannot invalidate shadow leases") from exc
    result.update({"shadow_prepared": True, "inherited_leases_invalidated": invalidated})
    return result
