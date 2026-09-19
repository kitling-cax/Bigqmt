"""Coordinator-side strategy installation request queue.

This queue is intentionally narrower than an execution assignment.  It only
asks a Host Agent to copy and verify an immutable strategy package locally;
it never grants a lease, changes an order gate, or starts a QMT strategy.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


STATUSES = {"REQUESTED", "INSTALLING", "INSTALLED", "REJECTED", "FAILED"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class StrategyDeploymentStore:
    """Small WAL-backed idempotent queue for non-executable installs."""

    def __init__(self, database_path: str | Path):
        self.database_path = Path(database_path)

    def connect(self) -> sqlite3.Connection:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.database_path)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
        return db

    def initialize(self) -> None:
        with self.connect() as db:
            db.execute(
                """CREATE TABLE IF NOT EXISTS strategy_deployments (
                deployment_id TEXT PRIMARY KEY,
                idempotency_key TEXT NOT NULL UNIQUE,
                strategy_id TEXT NOT NULL,
                version TEXT NOT NULL,
                build_id TEXT NOT NULL,
                manifest_sha256 TEXT NOT NULL,
                package_path TEXT NOT NULL,
                target_host_id TEXT NOT NULL,
                desired_state TEXT NOT NULL,
                status TEXT NOT NULL,
                requested_by TEXT NOT NULL,
                result_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
                )"""
            )

    def request_install(
        self,
        *,
        strategy_id: str,
        version: str,
        build_id: str,
        manifest_sha256: str,
        package_path: str,
        target_host_id: str,
        requested_by: str = "dashboard",
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        values = (strategy_id, version, build_id, manifest_sha256, package_path, target_host_id, requested_by)
        if not all(isinstance(value, str) and value.strip() for value in values):
            raise ValueError("deployment fields must be non-empty strings")
        key = (idempotency_key or "").strip() or (
            f"{strategy_id}:{version}:{build_id}:{target_host_id}"
        )
        self.initialize()
        deployment_id = str(uuid.uuid4())
        timestamp = _now()
        with self.connect() as db:
            existing = db.execute(
                "SELECT * FROM strategy_deployments WHERE idempotency_key=?", (key,)
            ).fetchone()
            if existing:
                return self._row(existing)
            db.execute(
                """INSERT INTO strategy_deployments VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    deployment_id, key, strategy_id, version, build_id,
                    manifest_sha256, package_path, target_host_id, "DEPLOY",
                    "REQUESTED", requested_by, "{}", timestamp, timestamp,
                ),
            )
            row = db.execute(
                "SELECT * FROM strategy_deployments WHERE deployment_id=?", (deployment_id,)
            ).fetchone()
        return self._row(row)

    def pending_for_host(self, host_id: str, *, limit: int = 20) -> list[dict[str, Any]]:
        if not isinstance(host_id, str) or not host_id.strip():
            return []
        self.initialize()
        with self.connect() as db:
            rows = db.execute(
                """SELECT * FROM strategy_deployments
                WHERE target_host_id=? AND status IN ('REQUESTED','INSTALLING')
                ORDER BY created_at LIMIT ?""",
                (host_id.strip(), max(1, min(100, int(limit)))),
            ).fetchall()
        return [self._row(row) for row in rows]

    def update_status(
        self, deployment_id: str, host_id: str, status: str, result: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        if status not in STATUSES:
            raise ValueError("invalid deployment status")
        if not deployment_id.strip() or not host_id.strip():
            raise ValueError("deployment_id and host_id are required")
        self.initialize()
        encoded = json.dumps(result or {}, ensure_ascii=False, sort_keys=True)
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM strategy_deployments WHERE deployment_id=? AND target_host_id=?",
                (deployment_id, host_id),
            ).fetchone()
            if not row:
                raise ValueError("deployment not found for host")
            db.execute(
                "UPDATE strategy_deployments SET status=?,result_json=?,updated_at=? "
                "WHERE deployment_id=? AND target_host_id=?",
                (status, encoded, _now(), deployment_id, host_id),
            )
            row = db.execute(
                "SELECT * FROM strategy_deployments WHERE deployment_id=?", (deployment_id,)
            ).fetchone()
        return self._row(row)

    @staticmethod
    def _row(row: sqlite3.Row | None) -> dict[str, Any]:
        if row is None:
            raise ValueError("deployment row is missing")
        item = dict(row)
        try:
            item["result"] = json.loads(item.pop("result_json") or "{}")
        except json.JSONDecodeError:
            item["result"] = {"status": "INVALID_RESULT"}
        item["readonly"] = True
        item["orders_enabled"] = False
        item["run_after_install"] = False
        return item
