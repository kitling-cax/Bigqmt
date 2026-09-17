"""Bounded simulation collector with a Redis liveness heartbeat."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .readonly_rpc import ReadOnlyBigQmtClient
from .snapshot import collect_readonly_snapshot
from .state_store import RuntimeStateStore


@dataclass(frozen=True)
class CollectionResult:
    run_id: str
    elapsed_seconds: float
    positions: int
    quotes: int


def write_heartbeat(client: ReadOnlyBigQmtClient, environment: str, ttl_seconds: int) -> None:
    """Publish only host-process liveness; it is not a trading command."""
    payload = json.dumps({
        "schema_version": 1,
        "environment": environment,
        "component": "host_readonly_collector",
        "orders_enabled": False,
        "received_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }, ensure_ascii=False, separators=(",", ":"))
    client.redis.command(
        "SET", "kitling:bigqmt:%s:host_gateway:heartbeat" % environment,
        payload, "EX", max(30, int(ttl_seconds)),
    )


def collect_cycles(
    client: ReadOnlyBigQmtClient,
    store: RuntimeStateStore,
    environment: str,
    quote_codes: list[str],
    cycles: int,
    interval_seconds: float,
) -> list[CollectionResult]:
    if cycles < 1:
        raise ValueError("cycles must be at least 1")
    if interval_seconds <= 0:
        raise ValueError("interval_seconds must be positive")
    results = []
    for index in range(cycles):
        started = time.monotonic()
        write_heartbeat(client, environment, int(interval_seconds * 3))
        bundle = collect_readonly_snapshot(client, quote_codes)
        run_id = store.record_snapshot(environment, client.account_id, bundle)
        results.append(CollectionResult(
            run_id=run_id,
            elapsed_seconds=time.monotonic() - started,
            positions=len(bundle["positions"].get("data") or {}),
            quotes=len(bundle["quotes"].get("data") or {}),
        ))
        if index + 1 < cycles:
            time.sleep(interval_seconds)
    return results
