"""Local durable Host Agent outbox for non-executable Coordinator facts.

The outbox is deliberately a transport buffer, not an order queue.  It can
store only post-fact operational records and has no method that talks to QMT,
Redis, a broker, a lease service, or an order-intent endpoint.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


EVENT_TYPES = frozenset({"ORDER_EVENT", "TRADE_FILL", "STRATEGY_RUNTIME", "STRATEGY_NAV", "CHECKPOINT"})
SENSITIVE_FIELD_FRAGMENTS = ("password", "secret", "credential", "authorization_key", "access_token")


class OutboxError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def canonical_json(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def payload_hash(value: dict[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _assert_no_sensitive_fields(value: object) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            lowered = str(key).lower()
            if any(fragment in lowered for fragment in SENSITIVE_FIELD_FRAGMENTS):
                raise OutboxError("sensitive field is forbidden in Coordinator outbox")
            _assert_no_sensitive_fields(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _assert_no_sensitive_fields(child)


class LocalOutbox:
    """SQLite WAL outbox with immutable event IDs and idempotent acknowledgements."""

    def __init__(self, database_path: str | Path):
        self.database_path = Path(database_path)

    def _connect(self) -> sqlite3.Connection:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.database_path)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
        return db

    def initialize(self) -> None:
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS coordinator_outbox (
                event_id TEXT PRIMARY KEY, event_type TEXT NOT NULL, account_id TEXT NOT NULL,
                strategy_id TEXT, payload_json TEXT NOT NULL, payload_sha256 TEXT NOT NULL,
                created_at TEXT NOT NULL, status TEXT NOT NULL, attempts INTEGER NOT NULL,
                last_error TEXT, acknowledged_at TEXT
            )""")

    def enqueue(self, event_type: str, payload: dict[str, Any]) -> dict[str, str]:
        if event_type not in EVENT_TYPES:
            raise OutboxError("unsupported outbox event type")
        if not isinstance(payload, dict):
            raise OutboxError("outbox payload must be an object")
        _assert_no_sensitive_fields(payload)
        event_id, account_id = str(payload.get("event_id") or "").strip(), str(payload.get("account_id") or "").strip()
        if not event_id or not account_id:
            raise OutboxError("event_id and account_id are required")
        encoded, digest = canonical_json(payload), payload_hash(payload)
        self.initialize()
        with self._connect() as db:
            existing = db.execute("SELECT payload_sha256 FROM coordinator_outbox WHERE event_id=?", (event_id,)).fetchone()
            if existing:
                if str(existing[0]) != digest:
                    raise OutboxError("event_id collision with different payload")
                return {"status": "DUPLICATE", "event_id": event_id, "payload_sha256": digest}
            db.execute("INSERT INTO coordinator_outbox VALUES(?,?,?,?,?,?,?,?,?,?,?)", (
                event_id, event_type, account_id, str(payload.get("strategy_id") or "") or None,
                encoded, digest, _now(), "PENDING", 0, None, None,
            ))
        return {"status": "QUEUED", "event_id": event_id, "payload_sha256": digest}

    def pending(self, *, limit: int = 100) -> list[dict[str, Any]]:
        self.initialize()
        with self._connect() as db:
            rows = db.execute("""SELECT * FROM coordinator_outbox WHERE status='PENDING'
                              ORDER BY created_at,event_id LIMIT ?""", (max(1, min(int(limit), 1000)),)).fetchall()
        return [{
            "event_id": row["event_id"], "event_type": row["event_type"], "account_id": row["account_id"],
            "payload": json.loads(row["payload_json"]), "payload_sha256": row["payload_sha256"],
            "attempts": int(row["attempts"]),
        } for row in rows]

    def acknowledge(self, event_ids: Iterable[str]) -> int:
        ids = sorted({str(value).strip() for value in event_ids if str(value).strip()})
        if not ids:
            return 0
        self.initialize()
        marks = ",".join("?" for _ in ids)
        with self._connect() as db:
            result = db.execute(
                f"UPDATE coordinator_outbox SET status='ACKED', acknowledged_at=?, last_error=NULL "
                f"WHERE status='PENDING' AND event_id IN ({marks})", (_now(), *ids)
            )
        return int(result.rowcount)

    def record_delivery_failure(self, event_ids: Iterable[str], reason: str) -> int:
        ids = sorted({str(value).strip() for value in event_ids if str(value).strip()})
        if not ids:
            return 0
        self.initialize()
        marks = ",".join("?" for _ in ids)
        with self._connect() as db:
            result = db.execute(
                f"UPDATE coordinator_outbox SET attempts=attempts+1,last_error=? "
                f"WHERE status='PENDING' AND event_id IN ({marks})", (str(reason)[:512], *ids)
            )
        return int(result.rowcount)
