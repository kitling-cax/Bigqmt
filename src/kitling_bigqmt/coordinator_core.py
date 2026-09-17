"""Small, dependency-free Coordinator state machine.

This module deliberately contains no QMT, Redis, shell, or network code.  It
stores leases and order intents in SQLite and fails closed when a lease or
fencing token is not current.  HTTP/MCP adapters can be added on top later.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class CoordinatorError(RuntimeError):
    pass


class AuthorizationError(CoordinatorError):
    pass


class StaleLeaseError(AuthorizationError):
    pass


@dataclass(frozen=True)
class Lease:
    account_id: str
    host_id: str
    mode: str
    token: int
    epoch: int
    expires_at: float


class CoordinatorStore:
    """Authoritative local store for coordinator control-plane state."""

    def __init__(self, database_path: str | Path):
        self.database_path = Path(database_path)

    def connect(self) -> sqlite3.Connection:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.database_path)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
        db.execute("PRAGMA foreign_keys=ON")
        return db

    def initialize(self) -> None:
        with self.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS coordinator_meta (
              key TEXT PRIMARY KEY, value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS hosts (
              host_id TEXT PRIMARY KEY, role TEXT NOT NULL, state TEXT NOT NULL,
              last_seen TEXT NOT NULL, payload_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS account_leases (
              account_id TEXT PRIMARY KEY, host_id TEXT NOT NULL,
              mode TEXT NOT NULL, fencing_token INTEGER NOT NULL,
              coordinator_epoch INTEGER NOT NULL, expires_at REAL NOT NULL,
              updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS intents (
              request_id TEXT PRIMARY KEY, account_id TEXT NOT NULL,
              strategy_id TEXT NOT NULL, host_id TEXT NOT NULL,
              fencing_token INTEGER NOT NULL, coordinator_epoch INTEGER NOT NULL,
              state TEXT NOT NULL, payload_hash TEXT NOT NULL,
              payload_json TEXT NOT NULL, created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS audit_events (
              event_id TEXT PRIMARY KEY, event_type TEXT NOT NULL,
              account_id TEXT, host_id TEXT, payload_json TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
            """)
            db.execute("INSERT OR IGNORE INTO coordinator_meta VALUES ('epoch', '1')")

    def epoch(self) -> int:
        self.initialize()
        with self.connect() as db:
            return self._epoch_db(db)

    @staticmethod
    def _epoch_db(db: sqlite3.Connection) -> int:
        return int(db.execute("SELECT value FROM coordinator_meta WHERE key='epoch'").fetchone()[0])

    def bump_epoch(self) -> int:
        self.initialize()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            value = self._epoch_db(db) + 1
            db.execute("UPDATE coordinator_meta SET value=? WHERE key='epoch'", (str(value),))
            db.execute("UPDATE account_leases SET expires_at=0, updated_at=?", (now(),))
            self._audit(db, "coordinator_epoch_bumped", None, None, {"epoch": value})
            return value

    def heartbeat(self, host_id: str, role: str, state: str, payload: dict[str, Any] | None = None) -> None:
        self.initialize()
        with self.connect() as db:
            db.execute("""INSERT INTO hosts(host_id,role,state,last_seen,payload_json)
              VALUES(?,?,?,?,?) ON CONFLICT(host_id) DO UPDATE SET role=excluded.role,
              state=excluded.state,last_seen=excluded.last_seen,payload_json=excluded.payload_json""",
              (host_id, role, state, now(), json.dumps(payload or {}, sort_keys=True)))

    def grant_lease(self, account_id: str, host_id: str, *, mode: str = "ACTIVE_EXECUTOR",
                    ttl_seconds: float = 30.0) -> Lease:
        if mode not in {"ACTIVE_EXECUTOR", "STANDBY_READONLY", "READ_ONLY"}:
            raise AuthorizationError("invalid lease mode")
        self.initialize()
        with self.connect() as db:
            # Serialize read/increment/write so two hosts cannot receive the
            # same fencing token during a takeover race.
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT fencing_token FROM account_leases WHERE account_id=?", (account_id,)).fetchone()
            token = int(row[0]) + 1 if row else 1
            epoch = self._epoch_db(db)
            expiry = datetime.now(timezone.utc).timestamp() + ttl_seconds
            db.execute("""INSERT INTO account_leases VALUES(?,?,?,?,?,?,?)
              ON CONFLICT(account_id) DO UPDATE SET host_id=excluded.host_id,mode=excluded.mode,
              fencing_token=excluded.fencing_token,coordinator_epoch=excluded.coordinator_epoch,
              expires_at=excluded.expires_at,updated_at=excluded.updated_at""",
              (account_id, host_id, mode, token, epoch, expiry, now()))
            self._audit(db, "lease_granted", account_id, host_id,
                        {"mode": mode, "fencing_token": token, "epoch": epoch})
            return Lease(account_id, host_id, mode, token, epoch, expiry)

    def current_lease(self, account_id: str) -> Lease | None:
        self.initialize()
        with self.connect() as db:
            row = db.execute("SELECT * FROM account_leases WHERE account_id=?", (account_id,)).fetchone()
        if not row:
            return None
        return Lease(row["account_id"], row["host_id"], row["mode"], int(row["fencing_token"]),
                     int(row["coordinator_epoch"]), float(row["expires_at"]))

    def validate_lease(self, lease: Lease) -> None:
        self.initialize()
        with self.connect() as db:
            row = db.execute("SELECT * FROM account_leases WHERE account_id=?", (lease.account_id,)).fetchone()
        if not row or row["host_id"] != lease.host_id or row["mode"] != "ACTIVE_EXECUTOR":
            raise StaleLeaseError("no active executor lease")
        if int(row["fencing_token"]) != lease.token or int(row["coordinator_epoch"]) != lease.epoch:
            raise StaleLeaseError("stale fencing token or coordinator epoch")
        if float(row["expires_at"]) <= datetime.now(timezone.utc).timestamp():
            raise StaleLeaseError("lease expired")

    def preview_intent(self, lease: Lease, payload: dict[str, Any]) -> str:
        self.validate_lease(lease)
        if payload.get("account_id") != lease.account_id:
            raise AuthorizationError("account mismatch")
        required = {"strategy_id", "symbol", "side", "quantity"}
        if not required.issubset(payload):
            raise AuthorizationError("incomplete order intent")
        request_id = str(uuid.uuid4())
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(encoded.encode()).hexdigest()
        with self.connect() as db:
            db.execute("""INSERT INTO intents VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
              (request_id, lease.account_id, str(payload["strategy_id"]), lease.host_id,
               lease.token, lease.epoch, "PREVIEW", digest, encoded, now(), now()))
            self._audit(db, "intent_previewed", lease.account_id, lease.host_id,
                        {"request_id": request_id, "payload_hash": digest})
        return request_id

    def confirm_intent(self, lease: Lease, request_id: str) -> None:
        self.validate_lease(lease)
        with self.connect() as db:
            row = db.execute("SELECT * FROM intents WHERE request_id=?", (request_id,)).fetchone()
            if not row or row["host_id"] != lease.host_id or row["fencing_token"] != lease.token:
                raise StaleLeaseError("intent is not owned by current lease")
            if row["state"] != "PREVIEW":
                raise AuthorizationError("intent is not confirmable")
            db.execute("UPDATE intents SET state='CONFIRMED',updated_at=? WHERE request_id=?", (now(), request_id))
            self._audit(db, "intent_confirmed", lease.account_id, lease.host_id, {"request_id": request_id})

    @staticmethod
    def _audit(db: sqlite3.Connection, event_type: str, account_id: str | None,
               host_id: str | None, payload: dict[str, Any]) -> None:
        db.execute("INSERT INTO audit_events VALUES(?,?,?,?,?,?)",
                   (str(uuid.uuid4()), event_type, account_id, host_id,
                    json.dumps(payload, sort_keys=True), now()))
