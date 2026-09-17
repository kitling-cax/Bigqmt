"""Authenticated, replay-protected fact ingress with no execution semantics."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .coordinator_event_store import CoordinatorEventStore
from .coordinator_fact_auth import FactAuthenticationError, TrustedFactHost, verify_signed_fact_envelope
from .coordinator_outbox import OutboxError


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class CoordinatorFactIngress:
    """Authenticated fact endpoint core; callers decide whether to expose HTTP."""

    def __init__(self, database_path: str | Path, trusted_hosts: Mapping[str, TrustedFactHost]):
        self.database_path = Path(database_path)
        self.trusted_hosts = dict(trusted_hosts)
        self.event_store = CoordinatorEventStore(self.database_path)

    def _connect(self) -> sqlite3.Connection:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.database_path)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
        return db

    def initialize(self) -> None:
        self.event_store.initialize()
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS coordinator_fact_request_replays (
                key_id TEXT NOT NULL, request_id TEXT NOT NULL, body_sha256 TEXT NOT NULL,
                received_at TEXT NOT NULL, PRIMARY KEY(key_id, request_id)
            )""")

    def ingest_signed(self, envelope: Mapping[str, Any], *, now_epoch: float | None = None) -> dict[str, Any]:
        identity = verify_signed_fact_envelope(envelope, self.trusted_hosts, now_epoch=now_epoch)
        self.initialize()
        request_id, body_hash = str(envelope["request_id"]), str(envelope["body_sha256"])
        with self._connect() as db:
            prior = db.execute(
                "SELECT body_sha256 FROM coordinator_fact_request_replays WHERE key_id=? AND request_id=?",
                (identity.key_id, request_id),
            ).fetchone()
            if prior:
                if str(prior[0]) != body_hash:
                    raise FactAuthenticationError("replayed request ID has different body")
                return {"status": "REPLAYED", "accepted": [], "duplicates": []}
        body = envelope["body"]
        events = body.get("events") if isinstance(body, dict) else None
        if not isinstance(events, list) or not events:
            raise OutboxError("signed fact body must contain non-empty events")
        result = self.event_store.ingest(identity.host_id, events, received_at=_now())
        try:
            with self._connect() as db:
                db.execute(
                    "INSERT INTO coordinator_fact_request_replays VALUES(?,?,?,?)",
                    (identity.key_id, request_id, body_hash, _now()),
                )
        except sqlite3.IntegrityError:
            # Concurrent duplicate delivery is safe because event IDs were
            # already deduplicated. It must never turn into an order retry.
            return {"status": "REPLAYED", "accepted": [], "duplicates": []}
        return {"status": "ACCEPTED", **result}
