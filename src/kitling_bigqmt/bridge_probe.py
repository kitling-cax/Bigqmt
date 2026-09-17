"""Bounded, read-only liveness probe for a profile-local QMT Bridge.

The probe deliberately calls only the Bridge ``ping`` RPC.  It never asks for
account data, market data, order data, or any execution method.  Its purpose is
to distinguish a running QMT process from an actually responsive Bridge after a
terminal restart.  A timeout is a degraded condition and never changes the
runtime order lock.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

from .readonly_rpc import ReadOnlyBigQmtClient
from .redis_resp import RedisRespClient


# Only these fields are copied out of the Bridge ``ping`` reply.  They are the
# durable identity/version evidence that the running BIGQMT_BRIDGE strategy is
# the expected build.  Copying them is read-only bookkeeping: nothing in this
# module reads a capability flag to enable an order path.
REPLY_EVIDENCE_FIELDS = (
    "account_id",
    "account_type",
    "version",
    "rpc_revision",
    "server_time",
    "allow_order_methods",
)


def reply_evidence(reply: dict[str, Any]) -> dict[str, Any]:
    """Return the whitelisted, non-secret subset of a Bridge ping reply."""
    # The Bridge puts its identity/version block inside ``data``; older builds
    # answered at the top level, so both shapes are accepted.
    source = reply.get("data")
    if not isinstance(source, dict):
        source = reply
    return {name: source[name] for name in REPLY_EVIDENCE_FIELDS if name in source}


def probe_bridge_ping(
    config: dict[str, Any],
    timeout_seconds: float = 3.0,
    client_factory: Callable[..., ReadOnlyBigQmtClient] = ReadOnlyBigQmtClient,
) -> dict[str, Any]:
    """Return a fail-closed status for exactly one read-only ``ping`` RPC."""

    account_id = str(config.get("account_id") or "").strip()
    redis = dict(config.get("redis") or {})
    timeout = max(0.5, min(float(timeout_seconds), 10.0))
    if not account_id or not redis:
        return {
            "status": "FAIL",
            "detail": "profile config lacks account_id or redis settings",
            "broker_call_made": False,
            "order_capability": False,
        }
    started = time.monotonic()
    try:
        client = client_factory(
            redis=RedisRespClient(timeout=min(timeout, 1.0), **redis),
            account_id=account_id,
            timeout_seconds=timeout,
        )
        reply = client.ping()
        elapsed_ms = (time.monotonic() - started) * 1000.0
        return {
            "status": "PASS",
            "detail": "read-only ping responded in %.0fms" % elapsed_ms,
            "latency_ms": round(elapsed_ms, 1),
            "bridge_reply_ok": bool(reply.get("ok", True)),
            "bridge_reply": reply_evidence(reply),
            "broker_call_made": False,
            "order_capability": False,
        }
    except (OSError, RuntimeError, TimeoutError, ValueError) as exc:
        elapsed_ms = (time.monotonic() - started) * 1000.0
        return {
            "status": "DEGRADED",
            "detail": "%s: %s; elapsed_ms=%.0f" % (type(exc).__name__, exc, elapsed_ms),
            "latency_ms": round(elapsed_ms, 1),
            "broker_call_made": False,
            "order_capability": False,
        }


def load_profile_config(project_root: Path, profile: str) -> dict[str, Any]:
    from . import machine_config

    return machine_config.load_gateway(project_root, profile)
