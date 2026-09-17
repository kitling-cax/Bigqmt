"""SQLite WAL authority store and append-only audit writer for read-only facts."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


@dataclass
class RuntimeStateStore:
    database_path: Path
    audit_directory: Path

    def connect(self) -> sqlite3.Connection:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(str(self.database_path))
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    @contextmanager
    def session(self):
        connection = self.connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.session() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS snapshot_runs (
                    run_id TEXT PRIMARY KEY,
                    environment TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    status TEXT NOT NULL,
                    bridge_version TEXT,
                    payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS account_assets (
                    run_id TEXT PRIMARY KEY REFERENCES snapshot_runs(run_id),
                    cash REAL, frozen_cash REAL, market_value REAL, total_asset REAL,
                    payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS positions (
                    run_id TEXT NOT NULL REFERENCES snapshot_runs(run_id),
                    stock_code TEXT NOT NULL, volume REAL, available REAL, cost REAL,
                    price REAL, market_value REAL, payload_json TEXT NOT NULL,
                    PRIMARY KEY (run_id, stock_code)
                );
                CREATE TABLE IF NOT EXISTS broker_orders (
                    run_id TEXT NOT NULL REFERENCES snapshot_runs(run_id),
                    row_number INTEGER NOT NULL, payload_json TEXT NOT NULL,
                    PRIMARY KEY (run_id, row_number)
                );
                CREATE TABLE IF NOT EXISTS broker_trades (
                    run_id TEXT NOT NULL REFERENCES snapshot_runs(run_id),
                    row_number INTEGER NOT NULL, payload_json TEXT NOT NULL,
                    PRIMARY KEY (run_id, row_number)
                );
                CREATE TABLE IF NOT EXISTS quote_snapshots (
                    run_id TEXT NOT NULL REFERENCES snapshot_runs(run_id),
                    stock_code TEXT NOT NULL, event_time TEXT, last_price REAL,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY (run_id, stock_code)
                );
                CREATE TABLE IF NOT EXISTS quote_quality (
                    run_id TEXT NOT NULL REFERENCES snapshot_runs(run_id),
                    stock_code TEXT NOT NULL,
                    source_event_time TEXT,
                    received_at TEXT NOT NULL,
                    age_seconds REAL,
                    freshness_state TEXT NOT NULL,
                    PRIMARY KEY (run_id, stock_code)
                );
                CREATE TABLE IF NOT EXISTS audit_events (
                    event_id TEXT PRIMARY KEY, run_id TEXT NOT NULL,
                    event_time TEXT NOT NULL, event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS reconciliation_runs (
                    reconciliation_id TEXT PRIMARY KEY,
                    environment TEXT NOT NULL,
                    previous_run_id TEXT,
                    current_run_id TEXT NOT NULL REFERENCES snapshot_runs(run_id),
                    completed_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS dryrun_order_intents (
                    request_id TEXT PRIMARY KEY,
                    environment TEXT NOT NULL,
                    strategy_id TEXT NOT NULL,
                    signal_id TEXT NOT NULL,
                    stock_code TEXT NOT NULL,
                    side TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    quote_run_id TEXT,
                    state TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS strategy_sleeves (
                    strategy_id TEXT PRIMARY KEY,
                    environment TEXT NOT NULL,
                    initial_capital REAL NOT NULL,
                    cash REAL NOT NULL,
                    frozen_cash REAL NOT NULL DEFAULT 0,
                    realized_pnl REAL NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sleeve_positions (
                    strategy_id TEXT NOT NULL REFERENCES strategy_sleeves(strategy_id),
                    stock_code TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    cost_amount REAL NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (strategy_id, stock_code)
                );
                CREATE TABLE IF NOT EXISTS sleeve_fills (
                    fill_id TEXT PRIMARY KEY,
                    strategy_id TEXT NOT NULL REFERENCES strategy_sleeves(strategy_id),
                    stock_code TEXT NOT NULL,
                    side TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    price REAL NOT NULL,
                    fee REAL NOT NULL,
                    fill_time TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sleeve_nav_snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    strategy_id TEXT NOT NULL REFERENCES strategy_sleeves(strategy_id),
                    valuation_run_id TEXT NOT NULL,
                    snapshot_time TEXT NOT NULL,
                    net_asset_value REAL NOT NULL,
                    cash REAL NOT NULL,
                    frozen_cash REAL NOT NULL,
                    market_value REAL NOT NULL,
                    realized_pnl REAL NOT NULL,
                    unrealized_pnl REAL NOT NULL,
                    total_pnl REAL NOT NULL,
                    return_rate REAL NOT NULL,
                    payload_hash TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    UNIQUE(strategy_id, valuation_run_id)
                );
                CREATE TABLE IF NOT EXISTS strategy_benchmark_snapshots (
                    strategy_id TEXT NOT NULL REFERENCES strategy_sleeves(strategy_id),
                    benchmark_code TEXT NOT NULL,
                    valuation_run_id TEXT NOT NULL,
                    snapshot_time TEXT NOT NULL,
                    price REAL NOT NULL,
                    base_price REAL NOT NULL,
                    net_asset_value REAL NOT NULL,
                    return_rate REAL NOT NULL,
                    payload_hash TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY (strategy_id, benchmark_code, valuation_run_id)
                );
                CREATE TABLE IF NOT EXISTS strategy_execution_attempts (
                    signal_id TEXT PRIMARY KEY,
                    strategy_id TEXT NOT NULL REFERENCES strategy_sleeves(strategy_id),
                    account_id TEXT NOT NULL,
                    signal_day TEXT NOT NULL,
                    stock_code TEXT NOT NULL,
                    side TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    state TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    response_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS strategy_order_attributions (
                    attribution_id TEXT PRIMARY KEY,
                    strategy_id TEXT NOT NULL REFERENCES strategy_sleeves(strategy_id),
                    account_id TEXT NOT NULL,
                    user_order_id TEXT NOT NULL,
                    order_sys_id TEXT NOT NULL,
                    stock_code TEXT NOT NULL,
                    side TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    source_evidence TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(account_id, user_order_id),
                    UNIQUE(account_id, order_sys_id)
                );
                CREATE TABLE IF NOT EXISTS strategy_shadow_events (
                    strategy_id TEXT NOT NULL,
                    signal_day TEXT NOT NULL,
                    event_id TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY (strategy_id, signal_day)
                );
            """)

    def record_snapshot(self, environment: str, account_id: str, bundle: dict[str, Any]) -> str:
        self.initialize()
        run_id = uuid4_hex()
        started_at = utc_now()
        ping_data = dict(bundle["ping"].get("data") or {})
        with self.session() as db:
            db.execute(
                "INSERT INTO snapshot_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (run_id, environment, account_id, started_at, utc_now(), "PASSED",
                 ping_data.get("version", ""), as_json(bundle)),
            )
            asset = dict(bundle["asset"].get("data") or {})
            db.execute(
                "INSERT INTO account_assets VALUES (?, ?, ?, ?, ?, ?)",
                (run_id, asset.get("cash"), asset.get("frozen_cash"), asset.get("market_value"),
                 asset.get("total_asset"), as_json(asset)),
            )
            for code, position in dict(bundle["positions"].get("data") or {}).items():
                row = dict(position or {})
                db.execute(
                    "INSERT INTO positions VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (run_id, code, row.get("volume"), row.get("available"), row.get("cost"),
                     row.get("price"), row.get("market_value"), as_json(row)),
                )
            for table, key in (("broker_orders", "orders"), ("broker_trades", "trades")):
                for index, row in enumerate(list(bundle[key].get("data") or [])):
                    db.execute("INSERT INTO %s VALUES (?, ?, ?)" % table, (run_id, index, as_json(row)))
            for code, quote in dict(bundle.get("quotes", {}).get("data") or {}).items():
                row = dict(quote or {})
                received_at = utc_now()
                age_seconds = quote_age_seconds(row.get("timetag"), received_at)
                freshness_state = "UNKNOWN" if age_seconds is None else (
                    "FRESH" if age_seconds <= 180 else "STALE")
                db.execute(
                    "INSERT INTO quote_snapshots VALUES (?, ?, ?, ?, ?)",
                    (run_id, code, row.get("timetag"), row.get("lastPrice"), as_json(row)),
                )
                db.execute(
                    "INSERT INTO quote_quality VALUES (?, ?, ?, ?, ?, ?)",
                    (run_id, code, row.get("timetag"), received_at, age_seconds, freshness_state),
                )
            db.execute(
                "INSERT INTO audit_events VALUES (?, ?, ?, ?, ?)",
                (uuid4_hex(), run_id, utc_now(), "readonly_snapshot", as_json({"run_id": run_id, "bundle": bundle})),
            )
        self._append_jsonl({"event_type": "readonly_snapshot", "run_id": run_id, "event_time": utc_now(), "bundle": bundle})
        return run_id

    def latest_snapshot_bundle(self) -> tuple[str, dict[str, Any]] | None:
        self.initialize()
        with self.session() as db:
            row = db.execute(
                "SELECT run_id, payload_json FROM snapshot_runs ORDER BY completed_at DESC LIMIT 1"
            ).fetchone()
        return None if row is None else (str(row[0]), json.loads(str(row[1])))

    def latest_snapshot_metadata(self) -> dict[str, Any] | None:
        """Return local capture metadata only; it never contacts QMT."""
        self.initialize()
        with self.session() as db:
            row = db.execute(
                "SELECT run_id, environment, account_id, completed_at, status, bridge_version "
                "FROM snapshot_runs ORDER BY completed_at DESC LIMIT 1"
            ).fetchone()
        if row is None:
            return None
        return {
            "run_id": str(row[0]), "environment": str(row[1]), "account_id": str(row[2]),
            "completed_at": str(row[3] or ""), "status": str(row[4]), "bridge_version": str(row[5] or ""),
        }

    def record_reconciliation(
        self,
        environment: str,
        previous_run_id: str | None,
        current_run_id: str,
        result: dict[str, Any],
    ) -> str:
        reconciliation_id = uuid4_hex()
        payload = as_json(result)
        with self.session() as db:
            db.execute(
                "INSERT INTO reconciliation_runs VALUES (?, ?, ?, ?, ?, ?, ?)",
                (reconciliation_id, environment, previous_run_id, current_run_id,
                 utc_now(), str(result["status"]), payload),
            )
            db.execute(
                "INSERT INTO audit_events VALUES (?, ?, ?, ?, ?)",
                (uuid4_hex(), current_run_id, utc_now(), "readonly_reconciliation", payload),
            )
        self._append_jsonl({
            "event_type": "readonly_reconciliation",
            "reconciliation_id": reconciliation_id,
            "previous_run_id": previous_run_id,
            "current_run_id": current_run_id,
            "event_time": utc_now(),
            "result": result,
        })
        return reconciliation_id

    def record_dryrun_intent(self, intent: dict[str, Any]) -> dict[str, Any]:
        """Durably record an order *plan*, never a broker order.

        The request id is the idempotency key. A retry with an identical
        payload returns DUPLICATE while preserving the original planned state;
        a changed payload under the same id fails closed.
        """
        self.initialize()
        payload_json = as_json(intent)
        payload_hash = sha256_hex(payload_json)
        now = utc_now()
        with self.session() as db:
            existing = db.execute(
                "SELECT payload_hash, state, created_at FROM dryrun_order_intents WHERE request_id = ?",
                (intent["request_id"],),
            ).fetchone()
            if existing is not None:
                if str(existing[0]) != payload_hash:
                    raise IdempotencyConflict("request_id was previously used with different payload")
                db.execute(
                    "UPDATE dryrun_order_intents SET last_seen_at = ? WHERE request_id = ?",
                    (now, intent["request_id"]),
                )
                return {
                    "result": "DUPLICATE", "request_id": intent["request_id"],
                    "state": str(existing[1]), "created_at": str(existing[2]), "last_seen_at": now,
                }
            db.execute(
                "INSERT INTO dryrun_order_intents VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (intent["request_id"], intent["environment"], intent["strategy_id"], intent["signal_id"],
                 intent["stock_code"], intent["side"], int(intent["quantity"]), intent.get("quote_run_id"),
                 intent["state"], payload_hash, now, now, payload_json),
            )
            db.execute(
                "INSERT INTO audit_events VALUES (?, ?, ?, ?, ?)",
                (uuid4_hex(), intent.get("quote_run_id") or "dryrun", now, "dryrun_order_intent", payload_json),
            )
        self._append_jsonl({"event_type": "dryrun_order_intent", "event_time": now, "intent": intent})
        return {"result": "RECORDED", "request_id": intent["request_id"], "state": intent["state"],
                "created_at": now, "last_seen_at": now}

    def record_strategy_shadow_event(self, event: dict[str, Any]) -> dict[str, Any]:
        """Persist one close-shadow result without creating a broker action.

        ``strategy_id`` plus ``signal_day`` is the idempotency key.  A changed
        signal for an already-recorded completed day fails closed instead of
        silently rewriting strategy history.
        """
        required = ("event_id", "strategy_id", "signal_day", "state_after", "signal")
        missing = [key for key in required if event.get(key) in (None, "")]
        if missing:
            raise ValueError("strategy shadow event missing: %s" % ", ".join(missing))
        if bool(event.get("orders_enabled", False)) or bool(event.get("broker_call_made", False)):
            raise ValueError("strategy shadow event must not have broker order capability")
        self.initialize()
        payload = dict(event)
        payload["orders_enabled"] = False
        payload["broker_call_made"] = False
        payload_json = as_json(payload)
        payload_hash = sha256_hex(payload_json)
        now = utc_now()
        with self.session() as db:
            existing = db.execute(
                "SELECT event_id, payload_hash, status, created_at FROM strategy_shadow_events "
                "WHERE strategy_id=? AND signal_day=?",
                (str(payload["strategy_id"]), str(payload["signal_day"])),
            ).fetchone()
            if existing:
                if str(existing[1]) != payload_hash:
                    raise IdempotencyConflict("strategy shadow day already exists with different payload")
                return {
                    "result": "DUPLICATE", "event_id": str(existing[0]), "status": str(existing[2]),
                    "created_at": str(existing[3]), "orders_enabled": False, "broker_call_made": False,
                }
            db.execute(
                "INSERT INTO strategy_shadow_events VALUES (?, ?, ?, ?, ?, ?, ?)",
                (str(payload["strategy_id"]), str(payload["signal_day"]), str(payload["event_id"]),
                 "RECORDED", payload_hash, now, payload_json),
            )
            db.execute(
                "INSERT INTO audit_events VALUES (?, ?, ?, ?, ?)",
                (uuid4_hex(), "shadow:" + str(payload["event_id"]), now,
                 "strategy_close_shadow", payload_json),
            )
        self._append_jsonl({"event_type": "strategy_close_shadow", "event_time": now, "event": payload})
        return {"result": "RECORDED", "event_id": str(payload["event_id"]), "status": "RECORDED",
                "created_at": now, "orders_enabled": False, "broker_call_made": False}

    def latest_strategy_shadow_events(self, limit: int = 20) -> list[dict[str, Any]]:
        """Read persisted shadow events in reverse signal-day order."""
        if int(limit) <= 0:
            return []
        self.initialize()
        with self.session() as db:
            rows = db.execute(
                "SELECT payload_json FROM strategy_shadow_events ORDER BY signal_day DESC, created_at DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
        return [json.loads(str(row[0])) for row in rows]

    def quote_freshness_summary(self, latest_runs: int = 3) -> dict[str, Any]:
        self.initialize()
        with self.session() as db:
            rows = db.execute("""
                SELECT q.freshness_state, q.age_seconds
                FROM quote_quality q
                JOIN snapshot_runs s ON s.run_id = q.run_id
                WHERE q.run_id IN (
                    SELECT run_id FROM snapshot_runs ORDER BY completed_at DESC LIMIT ?
                )
                ORDER BY s.completed_at DESC, q.stock_code
            """, (int(latest_runs),)).fetchall()
        states = {"FRESH": 0, "STALE": 0, "UNKNOWN": 0}
        ages = []
        for state, age in rows:
            states[str(state)] = states.get(str(state), 0) + 1
            if age is not None:
                ages.append(float(age))
        return {
            "samples": len(rows),
            "states": states,
            "max_age_seconds": max(ages) if ages else None,
            "latest_runs": int(latest_runs),
        }

    def latest_quote_gate(self, max_age_seconds: float = 180.0) -> dict[str, Any]:
        """Return per-symbol admission for downstream strategies and data lake jobs.

        This is intentionally a gate, not a fallback: a stale QMT quote must
        be visible and excluded until an explicitly recorded source decision is
        made in a later data-lake phase.
        """
        self.initialize()
        with self.session() as db:
            rows = db.execute("""
                SELECT q.stock_code, q.source_event_time, q.received_at,
                       q.age_seconds, q.freshness_state
                FROM quote_quality q
                WHERE q.run_id = (
                    SELECT run_id FROM snapshot_runs ORDER BY completed_at DESC LIMIT 1
                )
                ORDER BY q.stock_code
            """).fetchall()
        allowed, blocked = [], []
        for code, event_time, received_at, age_seconds, freshness_state in rows:
            row = {
                "stock_code": str(code), "source_event_time": event_time,
                "received_at": received_at, "age_seconds": age_seconds,
                "freshness_state": freshness_state,
            }
            if freshness_state == "FRESH" and age_seconds is not None and float(age_seconds) <= max_age_seconds:
                allowed.append(row)
            else:
                blocked.append(row)
        return {
            "max_age_seconds": float(max_age_seconds),
            "allowed": allowed,
            "blocked": blocked,
            "status": "PASSED" if rows and not blocked else "BLOCKED",
        }

    def claim_strategy_execution_attempt(self, attempt: dict[str, Any]) -> dict[str, Any]:
        """Durably claim one broker submission before it can be sent.

        A process crash after this claim must be reconciled rather than retried:
        duplicate claims are returned as-is, including an ``UNKNOWN`` state.
        This method has no broker or Redis dependency.
        """
        required = ("signal_id", "strategy_id", "account_id", "signal_day", "stock_code", "side", "quantity")
        missing = [key for key in required if attempt.get(key) in (None, "")]
        if missing:
            raise ValueError("strategy execution attempt missing: %s" % ", ".join(missing))
        side = str(attempt["side"]).upper()
        quantity = int(attempt["quantity"])
        if side not in ("BUY", "SELL") or quantity <= 0:
            raise ValueError("strategy execution attempt side/quantity is invalid")
        self.initialize()
        payload = {key: attempt[key] for key in required}
        payload["side"] = side
        payload["quantity"] = quantity
        payload_json = as_json(payload)
        payload_hash = sha256_hex(payload_json)
        now = utc_now()
        with self.session() as db:
            existing = db.execute(
                "SELECT state, payload_hash, created_at, updated_at, response_json "
                "FROM strategy_execution_attempts WHERE signal_id=?", (str(payload["signal_id"]),)
            ).fetchone()
            if existing:
                if str(existing[1]) != payload_hash:
                    raise IdempotencyConflict("strategy execution signal_id was previously used with different payload")
                return {
                    "result": "DUPLICATE", "signal_id": str(payload["signal_id"]), "state": str(existing[0]),
                    "created_at": str(existing[2]), "updated_at": str(existing[3]),
                    "response": json.loads(str(existing[4])) if existing[4] else None,
                }
            db.execute(
                "INSERT INTO strategy_execution_attempts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (str(payload["signal_id"]), str(payload["strategy_id"]), str(payload["account_id"]),
                 str(payload["signal_day"]), str(payload["stock_code"]), side, quantity, "SUBMITTING",
                 payload_hash, payload_json, None, now, now),
            )
        self._append_jsonl({"event_type": "strategy_execution_claim", "event_time": now, "attempt": payload})
        return {"result": "CLAIMED", "signal_id": str(payload["signal_id"]), "state": "SUBMITTING", "created_at": now}

    def finish_strategy_execution_attempt(self, signal_id: str, state: str, response: dict[str, Any] | None = None) -> dict[str, Any]:
        """Finish a previously claimed attempt without creating a broker action."""
        allowed = {"SUBMITTED", "UNKNOWN_TIMEOUT", "REJECTED"}
        if state not in allowed:
            raise ValueError("strategy execution final state is invalid")
        self.initialize()
        now = utc_now()
        response_json = as_json(response or {})
        with self.session() as db:
            row = db.execute("SELECT state FROM strategy_execution_attempts WHERE signal_id=?", (str(signal_id),)).fetchone()
            if row is None:
                raise ValueError("strategy execution attempt is not claimed")
            if str(row[0]) != "SUBMITTING":
                raise IdempotencyConflict("strategy execution attempt is already finalized")
            db.execute(
                "UPDATE strategy_execution_attempts SET state=?, response_json=?, updated_at=? WHERE signal_id=?",
                (state, response_json, now, str(signal_id)),
            )
        self._append_jsonl({"event_type": "strategy_execution_finished", "event_time": now,
                            "signal_id": str(signal_id), "state": state, "response": response or {}})
        return {"result": "RECORDED", "signal_id": str(signal_id), "state": state, "updated_at": now}

    def register_strategy_order_attribution(self, attribution: dict[str, Any]) -> dict[str, Any]:
        """Persist the durable proof that a broker order belongs to one sleeve.

        A Redis-resident bridge identity is deliberately *not* sufficient: it
        disappears on a Redis restart.  The caller must provide both immutable
        identifiers returned by QMT and the exact planned instrument, side and
        quantity.  This function never talks to a broker.
        """
        required = (
            "strategy_id", "account_id", "user_order_id", "order_sys_id",
            "stock_code", "side", "quantity", "source_evidence",
        )
        missing = [key for key in required if attribution.get(key) in (None, "")]
        if missing:
            raise ValueError("strategy order attribution missing: %s" % ", ".join(missing))
        side = str(attribution["side"]).upper()
        quantity = int(attribution["quantity"])
        if side not in ("BUY", "SELL") or quantity <= 0:
            raise ValueError("strategy order attribution side/quantity is invalid")
        self.initialize()
        payload = {
            "strategy_id": str(attribution["strategy_id"]),
            "account_id": str(attribution["account_id"]),
            "user_order_id": str(attribution["user_order_id"]),
            "order_sys_id": str(attribution["order_sys_id"]),
            "stock_code": str(attribution["stock_code"]),
            "side": side,
            "quantity": quantity,
            "source_evidence": str(attribution["source_evidence"]),
        }
        payload_json = as_json(payload)
        payload_hash = sha256_hex(payload_json)
        now = utc_now()
        with self.session() as db:
            rows = db.execute(
                "SELECT attribution_id, payload_hash FROM strategy_order_attributions "
                "WHERE account_id=? AND (user_order_id=? OR order_sys_id=?)",
                (payload["account_id"], payload["user_order_id"], payload["order_sys_id"]),
            ).fetchall()
            if rows:
                if len(rows) != 1 or str(rows[0][1]) != payload_hash:
                    raise IdempotencyConflict("broker order identity was previously attributed differently")
                return {
                    "result": "DUPLICATE", "attribution_id": str(rows[0][0]),
                    "user_order_id": payload["user_order_id"], "order_sys_id": payload["order_sys_id"],
                }
            attribution_id = uuid4_hex()
            db.execute(
                "INSERT INTO strategy_order_attributions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (attribution_id, payload["strategy_id"], payload["account_id"], payload["user_order_id"],
                 payload["order_sys_id"], payload["stock_code"], payload["side"], payload["quantity"],
                 payload["source_evidence"], payload_hash, payload_json, now),
            )
        self._append_jsonl({"event_type": "strategy_order_attribution", "event_time": now,
                            "attribution_id": attribution_id, "attribution": payload})
        return {"result": "RECORDED", "attribution_id": attribution_id,
                "user_order_id": payload["user_order_id"], "order_sys_id": payload["order_sys_id"]}

    def strategy_order_attributions(self, strategy_id: str) -> list[dict[str, Any]]:
        """Read local order-ownership proofs; this has no Redis/QMT dependency."""
        self.initialize()
        with self.session() as db:
            rows = db.execute(
                "SELECT attribution_id, payload_json, created_at FROM strategy_order_attributions "
                "WHERE strategy_id=? ORDER BY created_at, attribution_id", (str(strategy_id),)
            ).fetchall()
        result = []
        for attribution_id, payload_json, created_at in rows:
            payload = json.loads(str(payload_json))
            result.append({"attribution_id": str(attribution_id), "created_at": str(created_at), **payload})
        return result

    def _append_jsonl(self, event: dict[str, Any]) -> None:
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        target = self.audit_directory / day / "readonly_snapshot.jsonl"
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(as_json(event) + "\n")


def as_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))


def uuid4_hex() -> str:
    import uuid
    return uuid.uuid4().hex


class IdempotencyConflict(RuntimeError):
    pass


def sha256_hex(value: str) -> str:
    import hashlib
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def quote_age_seconds(timetag: Any, received_at: str) -> float | None:
    """Calculate QMT tick age, preserving UNKNOWN for unparseable timestamps."""
    if not timetag:
        return None
    try:
        source = datetime.strptime(str(timetag), "%Y%m%d %H:%M:%S").replace(
            tzinfo=ZoneInfo("Asia/Shanghai"))
        received = datetime.fromisoformat(received_at)
        return max(0.0, (received - source.astimezone(timezone.utc)).total_seconds())
    except (TypeError, ValueError):
        return None
