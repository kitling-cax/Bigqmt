"""Coordinator-side idempotent fact store; no HTTP or execution dependencies."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from .coordinator_outbox import EVENT_TYPES, OutboxError, canonical_json, payload_hash


class CoordinatorEventStore:
    """Persist Host Agent facts once and reject altered replay of an event ID."""

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
            db.execute("""CREATE TABLE IF NOT EXISTS coordinator_fact_events (
                event_id TEXT PRIMARY KEY, event_type TEXT NOT NULL, host_id TEXT NOT NULL,
                account_id TEXT NOT NULL, strategy_id TEXT, payload_sha256 TEXT NOT NULL,
                payload_json TEXT NOT NULL, received_at TEXT NOT NULL
            )""")

    def ingest(self, host_id: str, events: Iterable[dict[str, Any]], *, received_at: str) -> dict[str, list[str]]:
        """Store a batch atomically. Same ID+same hash is a safe duplicate."""
        if not host_id.strip():
            raise OutboxError("host_id is required")
        normalized: list[tuple[str, str, str, str, str | None, str, str]] = []
        for item in events:
            event_id, event_type = str(item.get("event_id") or "").strip(), str(item.get("event_type") or "").strip()
            payload = item.get("payload")
            if event_type not in EVENT_TYPES or not event_id or not isinstance(payload, dict):
                raise OutboxError("invalid fact event")
            account_id = str(payload.get("account_id") or "").strip()
            if not account_id:
                raise OutboxError("fact event account_id is required")
            digest = payload_hash(payload)
            supplied = str(item.get("payload_sha256") or "")
            if supplied and supplied != digest:
                raise OutboxError("fact event payload hash mismatch")
            normalized.append((event_id, event_type, host_id, account_id, str(payload.get("strategy_id") or "") or None, digest, canonical_json(payload)))
        self.initialize()
        accepted: list[str] = []
        duplicates: list[str] = []
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            for event_id, event_type, origin, account, strategy, digest, encoded in normalized:
                existing = db.execute("SELECT payload_sha256 FROM coordinator_fact_events WHERE event_id=?", (event_id,)).fetchone()
                if existing:
                    if str(existing[0]) != digest:
                        raise OutboxError("coordinator event_id collision with different payload")
                    duplicates.append(event_id)
                    continue
                db.execute("INSERT INTO coordinator_fact_events VALUES(?,?,?,?,?,?,?,?)", (
                    event_id, event_type, origin, account, strategy, digest, encoded, received_at,
                ))
                accepted.append(event_id)
        return {"accepted": accepted, "duplicates": duplicates}

    def count(self) -> int:
        self.initialize()
        with self._connect() as db:
            return int(db.execute("SELECT COUNT(*) FROM coordinator_fact_events").fetchone()[0])
