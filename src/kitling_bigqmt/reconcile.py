"""Read-only recovery reconciliation against the latest QMT broker facts."""

from __future__ import annotations

from typing import Any

from .readonly_rpc import ReadOnlyBigQmtClient
from .snapshot import collect_readonly_snapshot
from .state_store import RuntimeStateStore


def _position_volumes(bundle: dict[str, Any]) -> dict[str, float]:
    return {
        str(code): float((row or {}).get("volume") or 0)
        for code, row in dict(bundle["positions"].get("data") or {}).items()
    }


def reconcile_after_restart(
    client: ReadOnlyBigQmtClient,
    store: RuntimeStateStore,
    environment: str,
    quote_codes: list[str],
) -> dict[str, Any]:
    """Persist QMT's current facts and document differences from the last run.

    Broker facts are never overwritten by the old local snapshot.  A position
    change is reported for later attribution rather than treated as a failure.
    """
    previous = store.latest_snapshot_bundle()
    current_bundle = collect_readonly_snapshot(client, quote_codes)
    current_run_id = store.record_snapshot(environment, client.account_id, current_bundle)
    current_volumes = _position_volumes(current_bundle)
    previous_volumes = _position_volumes(previous[1]) if previous else {}
    all_codes = sorted(set(previous_volumes) | set(current_volumes))
    changes = [
        {"stock_code": code, "previous_volume": previous_volumes.get(code, 0.0),
         "current_volume": current_volumes.get(code, 0.0)}
        for code in all_codes
        if previous_volumes.get(code, 0.0) != current_volumes.get(code, 0.0)
    ]
    result = {
        "status": "PASSED",
        "policy": "QMT broker facts remain authoritative; differences require later strategy attribution.",
        "previous_run_id": previous[0] if previous else None,
        "current_run_id": current_run_id,
        "position_changes": changes,
        "orders": len(current_bundle["orders"].get("data") or []),
        "trades": len(current_bundle["trades"].get("data") or []),
        "orders_enabled": False,
    }
    result["reconciliation_id"] = store.record_reconciliation(
        environment, previous[0] if previous else None, current_run_id, result
    )
    return result
