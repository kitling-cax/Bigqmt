"""Pure validation helpers for the simulation-account daily operating record."""

from __future__ import annotations

from typing import Any


def reconcile_daily_positions(
    broker_quantities: dict[str, int],
    external_baseline: dict[str, int],
    strategy_owned: dict[str, int],
) -> dict[str, Any]:
    """Ensure broker holdings have a complete non-overlapping attribution."""
    differences: list[dict[str, Any]] = []
    for code in sorted(set(broker_quantities) | set(external_baseline) | set(strategy_owned)):
        broker = int(broker_quantities.get(code, 0))
        external = int(external_baseline.get(code, 0))
        owned = int(strategy_owned.get(code, 0))
        if broker != external + owned:
            differences.append({
                "stock_code": code,
                "broker_quantity": broker,
                "external_baseline": external,
                "strategy_owned": owned,
                "difference": broker - external - owned,
            })
    return {
        "status": "PASSED" if not differences else "BLOCKED",
        "broker_quantities": dict(broker_quantities),
        "external_baseline": dict(external_baseline),
        "strategy_owned": dict(strategy_owned),
        "differences": differences,
    }
