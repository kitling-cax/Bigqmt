"""Fail-closed validation of a Coordinator execution-lease envelope.

This module is intentionally local and side-effect free.  A valid lease is
only one prerequisite for a future simulation execution engine; it never
opens the runtime order switch or calls QMT.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any


class LeaseRejected(ValueError):
    """Raised when a lease cannot be used by this local Host Agent."""


@dataclass(frozen=True)
class VerifiedExecutionLease:
    account_id: str
    host_id: str
    mode: str
    fencing_token: int
    coordinator_epoch: int
    expires_at: float


def verify_execution_lease(
    envelope: dict[str, Any] | None,
    *,
    expected_account_id: str,
    expected_host_id: str,
    trusted_transport: bool,
    now_epoch: float | None = None,
) -> VerifiedExecutionLease:
    """Validate one lease for one account/host and otherwise reject it.

    ``trusted_transport`` is deliberately supplied by the network adapter,
    not inferred from JSON.  A local file or unauthenticated HTTP response
    must always pass ``False`` and is therefore unusable for execution.
    """
    if not trusted_transport:
        raise LeaseRejected("lease transport is not authenticated")
    if not isinstance(envelope, dict):
        raise LeaseRejected("lease is missing")
    if envelope.get("schema_version") != 1:
        raise LeaseRejected("unsupported lease schema")
    if str(envelope.get("account_id", "")) != expected_account_id:
        raise LeaseRejected("account does not match local profile")
    if str(envelope.get("host_id", "")) != expected_host_id:
        raise LeaseRejected("lease belongs to another host")
    mode = str(envelope.get("mode", ""))
    if mode != "ACTIVE_EXECUTOR":
        raise LeaseRejected("lease is not an active executor lease")
    if expected_account_id == "90000002":
        raise LeaseRejected("production readonly account cannot hold execution lease")
    try:
        token = int(envelope["fencing_token"])
        epoch = int(envelope["coordinator_epoch"])
        expires_at = float(envelope["expires_at"])
    except (KeyError, TypeError, ValueError) as exc:
        raise LeaseRejected("lease fields are invalid") from exc
    if token <= 0 or epoch <= 0:
        raise LeaseRejected("lease token or epoch is invalid")
    if expires_at <= (time.time() if now_epoch is None else now_epoch):
        raise LeaseRejected("lease has expired")
    return VerifiedExecutionLease(expected_account_id, expected_host_id, mode, token, epoch, expires_at)
