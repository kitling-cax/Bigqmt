"""Strategy-sleeve accounting backed by the local SQLite WAL authority store.

This module only accounts for already-attributable fills.  It cannot create a
broker order, and it deliberately will not claim pre-existing broker positions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .state_store import RuntimeStateStore, as_json, sha256_hex, utc_now, uuid4_hex


class SleeveAccountingError(ValueError):
    pass


@dataclass(frozen=True)
class SleeveAccounting:
    store: RuntimeStateStore

    def register_sleeve(self, strategy_id: str, initial_capital: float, environment: str = "simulation") -> dict[str, Any]:
        if environment != "simulation":
            raise SleeveAccountingError("sleeves are simulation-only until formal approval")
        if not strategy_id or initial_capital <= 0:
            raise SleeveAccountingError("strategy_id and positive initial_capital are required")
        self.store.initialize()
        now = utc_now()
        with self.store.session() as db:
            row = db.execute("SELECT initial_capital, environment FROM strategy_sleeves WHERE strategy_id=?", (strategy_id,)).fetchone()
            if row:
                if float(row[0]) != float(initial_capital) or str(row[1]) != environment:
                    raise SleeveAccountingError("strategy sleeve already exists with different capital or environment")
                return {"result": "DUPLICATE", "strategy_id": strategy_id}
            db.execute("INSERT INTO strategy_sleeves VALUES (?, ?, ?, ?, 0, 0, ?, ?)",
                       (strategy_id, environment, float(initial_capital), float(initial_capital), now, now))
        return {"result": "REGISTERED", "strategy_id": strategy_id, "orders_enabled": False}

    def record_fill(self, fill: dict[str, Any]) -> dict[str, Any]:
        required = ("fill_id", "strategy_id", "stock_code", "side", "quantity", "price")
        missing = [key for key in required if not fill.get(key)]
        if missing:
            raise SleeveAccountingError("missing fill fields: %s" % ", ".join(missing))
        side = str(fill["side"]).upper()
        quantity = int(fill["quantity"])
        price = float(fill["price"])
        fee = float(fill.get("fee", 0.0))
        if side not in ("BUY", "SELL") or quantity <= 0 or price <= 0 or fee < 0:
            raise SleeveAccountingError("invalid fill side, quantity, price, or fee")
        self.store.initialize()
        payload = {"fill_id": str(fill["fill_id"]), "strategy_id": str(fill["strategy_id"]),
                   "stock_code": str(fill["stock_code"]), "side": side, "quantity": quantity,
                   "price": price, "fee": fee, "fill_time": str(fill.get("fill_time") or utc_now())}
        payload_json = as_json(payload)
        payload_hash = sha256_hex(payload_json)
        now = utc_now()
        with self.store.session() as db:
            existing = db.execute("SELECT payload_hash FROM sleeve_fills WHERE fill_id=?", (payload["fill_id"],)).fetchone()
            if existing:
                if str(existing[0]) != payload_hash:
                    raise SleeveAccountingError("fill_id already exists with different payload")
                return {"result": "DUPLICATE", "fill_id": payload["fill_id"], "orders_enabled": False}
            sleeve = db.execute("SELECT cash, realized_pnl FROM strategy_sleeves WHERE strategy_id=?", (payload["strategy_id"],)).fetchone()
            if not sleeve:
                raise SleeveAccountingError("strategy sleeve is not registered")
            cash, realized = float(sleeve[0]), float(sleeve[1])
            position = db.execute("SELECT quantity, cost_amount FROM sleeve_positions WHERE strategy_id=? AND stock_code=?",
                                  (payload["strategy_id"], payload["stock_code"])).fetchone()
            old_quantity, old_cost = (int(position[0]), float(position[1])) if position else (0, 0.0)
            if side == "BUY":
                debit = quantity * price + fee
                if debit > cash + 1e-8:
                    raise SleeveAccountingError("fill exceeds strategy sleeve cash")
                new_quantity, new_cost, new_cash = old_quantity + quantity, old_cost + debit, cash - debit
            else:
                if quantity > old_quantity:
                    raise SleeveAccountingError("sell fill exceeds strategy-owned quantity")
                average_cost = old_cost / old_quantity if old_quantity else 0.0
                released_cost = average_cost * quantity
                proceeds = quantity * price - fee
                new_quantity, new_cost, new_cash = old_quantity - quantity, max(0.0, old_cost - released_cost), cash + proceeds
                realized += proceeds - released_cost
            db.execute("INSERT INTO sleeve_fills VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                       (payload["fill_id"], payload["strategy_id"], payload["stock_code"], side, quantity, price, fee,
                        payload["fill_time"], payload_hash, payload_json))
            if new_quantity:
                db.execute("INSERT INTO sleeve_positions VALUES (?, ?, ?, ?, ?) ON CONFLICT(strategy_id,stock_code) DO UPDATE SET quantity=excluded.quantity,cost_amount=excluded.cost_amount,updated_at=excluded.updated_at",
                           (payload["strategy_id"], payload["stock_code"], new_quantity, new_cost, now))
            else:
                db.execute("DELETE FROM sleeve_positions WHERE strategy_id=? AND stock_code=?", (payload["strategy_id"], payload["stock_code"]))
            db.execute("UPDATE strategy_sleeves SET cash=?, realized_pnl=?, updated_at=? WHERE strategy_id=?",
                       (new_cash, realized, now, payload["strategy_id"]))
        return {"result": "RECORDED", "fill_id": payload["fill_id"], "orders_enabled": False}

    def summary(self, strategy_id: str, prices: dict[str, float]) -> dict[str, Any]:
        self.store.initialize()
        with self.store.session() as db:
            sleeve = db.execute("SELECT environment, initial_capital, cash, frozen_cash, realized_pnl FROM strategy_sleeves WHERE strategy_id=?", (strategy_id,)).fetchone()
            if not sleeve:
                raise SleeveAccountingError("strategy sleeve is not registered")
            rows = db.execute("SELECT stock_code, quantity, cost_amount FROM sleeve_positions WHERE strategy_id=? ORDER BY stock_code", (strategy_id,)).fetchall()
        positions, market_value, cost_amount = [], 0.0, 0.0
        for code, quantity, cost in rows:
            if code not in prices or float(prices[code]) <= 0:
                raise SleeveAccountingError("missing positive valuation price for %s" % code)
            value = int(quantity) * float(prices[code])
            positions.append({"stock_code": code, "quantity": int(quantity), "cost_amount": float(cost),
                              "market_price": float(prices[code]), "market_value": value,
                              "unrealized_pnl": value - float(cost)})
            market_value += value
            cost_amount += float(cost)
        environment, initial, cash, frozen, realized = sleeve
        nav = float(cash) + float(frozen) + market_value
        return {"strategy_id": strategy_id, "environment": environment, "initial_capital": float(initial),
                "cash": float(cash), "frozen_cash": float(frozen), "market_value": market_value,
                "net_asset_value": nav, "total_pnl": nav - float(initial), "return_rate": nav / float(initial) - 1,
                "realized_pnl": float(realized), "unrealized_pnl": market_value - cost_amount,
                "positions": positions, "orders_enabled": False}

    def position_quantities(self, strategy_id: str) -> dict[str, int]:
        """Read sleeve-owned quantities without requiring a valuation price."""
        self.store.initialize()
        with self.store.session() as db:
            rows = db.execute(
                "SELECT stock_code, quantity FROM sleeve_positions WHERE strategy_id=? ORDER BY stock_code",
                (strategy_id,),
            ).fetchall()
        return {str(code): int(quantity) for code, quantity in rows}

    def fill_records(self, strategy_id: str) -> list[dict[str, Any]]:
        """Return attributable, deduplicated sleeve fills in ledger order."""
        self.store.initialize()
        with self.store.session() as db:
            rows = db.execute(
                """SELECT fill_id, stock_code, side, quantity, price, fee, fill_time
                   FROM sleeve_fills WHERE strategy_id=? ORDER BY fill_time, fill_id""",
                (strategy_id,),
            ).fetchall()
        keys = ("fill_id", "stock_code", "side", "quantity", "price", "fee", "fill_time")
        return [dict(zip(keys, row)) for row in rows]

    def record_nav_snapshot(
        self,
        strategy_id: str,
        prices: dict[str, float],
        valuation_run_id: str,
        snapshot_time: str | None = None,
    ) -> dict[str, Any]:
        """Persist one sleeve valuation without creating a fill or order.

        ``valuation_run_id`` is the idempotency key for a strategy valuation.
        The caller should reuse both the run id and timestamp when retrying a
        failed write; a changed payload under the same key fails closed.
        """
        if not valuation_run_id:
            raise SleeveAccountingError("valuation_run_id is required")
        summary = self.summary(strategy_id, prices)
        timestamp = str(snapshot_time or utc_now())
        payload = {
            "strategy_id": strategy_id,
            "valuation_run_id": str(valuation_run_id),
            "snapshot_time": timestamp,
            "net_asset_value": float(summary["net_asset_value"]),
            "cash": float(summary["cash"]),
            "frozen_cash": float(summary["frozen_cash"]),
            "market_value": float(summary["market_value"]),
            "realized_pnl": float(summary["realized_pnl"]),
            "unrealized_pnl": float(summary["unrealized_pnl"]),
            "total_pnl": float(summary["total_pnl"]),
            "return_rate": float(summary["return_rate"]),
        }
        payload_json = as_json(payload)
        payload_hash = sha256_hex(payload_json)
        self.store.initialize()
        with self.store.session() as db:
            existing = db.execute(
                "SELECT snapshot_id, payload_hash FROM sleeve_nav_snapshots WHERE strategy_id=? AND valuation_run_id=?",
                (strategy_id, str(valuation_run_id)),
            ).fetchone()
            if existing:
                if str(existing[1]) != payload_hash:
                    raise SleeveAccountingError("valuation_run_id already exists with different payload")
                return {"result": "DUPLICATE", "snapshot_id": str(existing[0]),
                        "strategy_id": strategy_id, "valuation_run_id": str(valuation_run_id),
                        "orders_enabled": False}
            snapshot_id = uuid4_hex()
            db.execute(
                "INSERT INTO sleeve_nav_snapshots VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (snapshot_id, strategy_id, str(valuation_run_id), timestamp,
                 payload["net_asset_value"], payload["cash"], payload["frozen_cash"],
                 payload["market_value"], payload["realized_pnl"], payload["unrealized_pnl"],
                 payload["total_pnl"], payload["return_rate"], payload_hash, payload_json),
            )
        return {"result": "RECORDED", "snapshot_id": snapshot_id,
                "strategy_id": strategy_id, "valuation_run_id": str(valuation_run_id),
                "orders_enabled": False}

    def nav_series(self, strategy_id: str, limit: int = 365) -> list[dict[str, Any]]:
        """Read the most recent persisted NAV points in chronological order."""
        if int(limit) <= 0:
            return []
        self.store.initialize()
        with self.store.session() as db:
            rows = db.execute(
                """SELECT valuation_run_id, snapshot_time, net_asset_value, cash,
                          frozen_cash, market_value, realized_pnl, unrealized_pnl,
                          total_pnl, return_rate
                   FROM sleeve_nav_snapshots
                   WHERE strategy_id=? ORDER BY snapshot_time DESC LIMIT ?""",
                (strategy_id, int(limit)),
            ).fetchall()
        keys = ("valuation_run_id", "snapshot_time", "net_asset_value", "cash",
                "frozen_cash", "market_value", "realized_pnl", "unrealized_pnl",
                "total_pnl", "return_rate")
        return [dict(zip(keys, row)) for row in reversed(rows)]

    def record_benchmark_snapshot(
        self,
        strategy_id: str,
        benchmark_code: str,
        price: float,
        valuation_run_id: str,
        snapshot_time: str | None = None,
    ) -> dict[str, Any]:
        """Store one rebased, price-only benchmark point for a strategy.

        The benchmark has no broker/strategy ownership and cannot alter a
        sleeve.  It is rebased to the sleeve's initial capital at its first
        durable observation, so its curve is directly comparable to strategy
        NAV without implying that the ETF was actually bought.
        """
        if not strategy_id or not benchmark_code or not valuation_run_id:
            raise SleeveAccountingError("strategy_id, benchmark_code, and valuation_run_id are required")
        price = float(price)
        if price <= 0:
            raise SleeveAccountingError("benchmark price must be positive")
        self.store.initialize()
        timestamp = str(snapshot_time or utc_now())
        with self.store.session() as db:
            sleeve = db.execute(
                "SELECT initial_capital FROM strategy_sleeves WHERE strategy_id=?", (strategy_id,)
            ).fetchone()
            if not sleeve:
                raise SleeveAccountingError("strategy sleeve is not registered")
            base = db.execute(
                """SELECT base_price FROM strategy_benchmark_snapshots
                   WHERE strategy_id=? AND benchmark_code=? ORDER BY snapshot_time LIMIT 1""",
                (strategy_id, benchmark_code),
            ).fetchone()
            base_price = float(base[0]) if base else price
            nav = float(sleeve[0]) * price / base_price
            payload = {
                "strategy_id": strategy_id, "benchmark_code": benchmark_code,
                "valuation_run_id": valuation_run_id, "snapshot_time": timestamp,
                "price": price, "base_price": base_price, "net_asset_value": nav,
                "return_rate": nav / float(sleeve[0]) - 1,
            }
            payload_json = as_json(payload)
            payload_hash = sha256_hex(payload_json)
            existing = db.execute(
                """SELECT payload_hash FROM strategy_benchmark_snapshots
                   WHERE strategy_id=? AND benchmark_code=? AND valuation_run_id=?""",
                (strategy_id, benchmark_code, valuation_run_id),
            ).fetchone()
            if existing:
                if str(existing[0]) != payload_hash:
                    raise SleeveAccountingError("benchmark valuation_run_id already exists with different payload")
                return {"result": "DUPLICATE", **payload, "orders_enabled": False}
            db.execute(
                "INSERT INTO strategy_benchmark_snapshots VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (strategy_id, benchmark_code, valuation_run_id, timestamp, price, base_price,
                 nav, payload["return_rate"], payload_hash, payload_json),
            )
        return {"result": "RECORDED", **payload, "orders_enabled": False}

    def benchmark_series(self, strategy_id: str, benchmark_code: str, limit: int = 365) -> list[dict[str, Any]]:
        self.store.initialize()
        with self.store.session() as db:
            rows = db.execute(
                """SELECT benchmark_code, valuation_run_id, snapshot_time, price, base_price,
                          net_asset_value, return_rate
                   FROM strategy_benchmark_snapshots
                   WHERE strategy_id=? AND benchmark_code=?
                   ORDER BY snapshot_time DESC LIMIT ?""",
                (strategy_id, benchmark_code, int(limit)),
            ).fetchall()
        keys = ("benchmark_code", "valuation_run_id", "snapshot_time", "price", "base_price", "net_asset_value", "return_rate")
        return [dict(zip(keys, row)) for row in reversed(rows)]

    def reconcile_broker_positions(self, broker_quantities: dict[str, int], external_baseline: dict[str, int]) -> dict[str, Any]:
        self.store.initialize()
        with self.store.session() as db:
            rows = db.execute("SELECT stock_code, SUM(quantity) FROM sleeve_positions GROUP BY stock_code").fetchall()
        owned = {str(code): int(quantity) for code, quantity in rows}
        differences = []
        for code in sorted(set(broker_quantities) | set(external_baseline) | set(owned)):
            broker = int(broker_quantities.get(code, 0))
            external = int(external_baseline.get(code, 0))
            sleeves = int(owned.get(code, 0))
            if broker != external + sleeves:
                differences.append({"stock_code": code, "broker_quantity": broker, "external_baseline": external,
                                    "strategy_owned": sleeves, "difference": broker - external - sleeves})
        return {"status": "PASSED" if not differences else "BLOCKED", "broker_quantities": dict(broker_quantities),
                "external_baseline": dict(external_baseline), "strategy_owned": owned,
                "differences": differences, "orders_enabled": False}
