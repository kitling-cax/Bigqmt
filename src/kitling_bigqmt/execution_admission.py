"""Single fail-closed admission gate in front of every local order path.

Every script that can reach a broker order method must obtain a verdict from
this module immediately before it writes an RPC request.  The gate is
deliberately narrow:

  * a formal (production) account is denied unconditionally,
  * the local runtime control must already be armed for this exact
    environment/account/strategy and still be inside its short window,
  * the Coordinator (read-only preview) must designate this host as the
    eligible executor for the account; an unreachable Coordinator denies,
  * a lease envelope cannot open execution yet, because leased execution is
    not part of the current milestone.

Nothing here talks to Redis, QMT, or a broker.  The gate can only deny; the
caller keeps ownership of the actual submit, its idempotency claim, and the
finally re-lock.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Mapping
from urllib.request import urlopen

from .coordinator_endpoint import resolve_coordinator
from .coordinator_lease_projection import project_local_lease
from .machine_config import load_gateway
from .machine_config import load_gateway, load_machine_local
from .order_authorization_key import status as order_authorization_key_status
from .host_agent_account_policy import (
    AccountPolicyRejected,
    evaluate_local_execution,
    resolve_account_policy,
)


SIMULATION_ENVIRONMENT = "SIMULATION"
SIMULATION_WINDOW_MODE = "SIMULATION_STRATEGY_EXECUTION_WINDOW"
ADMITTED_REASON = "ADMITTED_SIMULATION_SINGLE_WRITER"


class ExecutionAdmissionDenied(RuntimeError):
    """Raised when a local order path must not proceed."""

    def __init__(self, verdict: Mapping[str, Any]):
        self.verdict = dict(verdict)
        self.reason = str(self.verdict.get("reason", "DENIED"))
        super().__init__("execution admission denied: %s" % self.reason)


def _deny(reason: str, **extra: Any) -> dict[str, Any]:
    verdict: dict[str, Any] = {"allowed": False, "orders_enabled": False, "reason": reason}
    verdict.update(extra)
    return verdict


def coordinator_designation(
    endpoint: str,
    profile: str,
    host_id: str,
    *,
    timeout: float = 3.0,
) -> dict[str, Any]:
    """Read the Coordinator executor preview; any failure denies the host.

    The preview is a read-only projection, so this never requests or renews a
    lease.  An unreachable or malformed response is reported as
    reachable=False rather than raising, because the caller decision is
    always the same: no new order.
    """
    try:
        with urlopen(
            endpoint.rstrip("/") + "/api/v1/executor-preview",
            timeout=max(0.1, float(timeout)),
        ) as response:
            preview = json.loads(response.read().decode("utf-8"))
        projected = project_local_lease(preview, profile, host_id)
    except Exception as exc:  # noqa: BLE001 - every failure denies
        return {
            "reachable": False,
            "eligible": False,
            "lease_state": "UNKNOWN",
            "reason": type(exc).__name__,
        }
    return {
        "reachable": True,
        "eligible": bool(projected.get("candidate_eligible", False)),
        "lease_state": str(projected.get("lease_state", "UNKNOWN")),
        "reason": str(projected.get("candidate_reason", "NOT_REPORTED")),
    }


def _authorization_denial(
    authorization: Mapping[str, Any] | None,
    *,
    account_id: str,
    strategy_id: str | None,
    now_epoch: float,
) -> str | None:
    """Return the denial reason for the local runtime control, or None."""
    if not isinstance(authorization, Mapping):
        return "LOCAL_AUTHORIZATION_MISSING"
    if str(authorization.get("environment") or "").upper() != SIMULATION_ENVIRONMENT:
        return "LOCAL_AUTHORIZATION_ENVIRONMENT_MISMATCH"
    if str(authorization.get("mode") or "") != SIMULATION_WINDOW_MODE:
        return "LOCAL_AUTHORIZATION_NOT_ARMED"
    if authorization.get("orders_enabled") is not True:
        return "LOCAL_AUTHORIZATION_NOT_ARMED"
    if authorization.get("execution_consumer_enabled") is not True:
        return "LOCAL_AUTHORIZATION_NOT_ARMED"
    try:
        valid_until = float(authorization.get("valid_until_epoch") or 0)
    except (TypeError, ValueError):
        return "LOCAL_AUTHORIZATION_NOT_ARMED"
    if valid_until <= now_epoch:
        return "LOCAL_AUTHORIZATION_EXPIRED"
    # Account and strategy binding are checked only once a real armed window
    # exists, so a locked control file reports the truthful NOT_ARMED state.
    if str(authorization.get("account_id") or "").strip() != account_id:
        return "LOCAL_AUTHORIZATION_ACCOUNT_MISMATCH"
    armed_strategy = str(authorization.get("strategy_id") or "").strip()
    if strategy_id and armed_strategy and armed_strategy != strategy_id:
        return "LOCAL_AUTHORIZATION_STRATEGY_MISMATCH"
    return None


def _order_key_denial(
    key_status: Mapping[str, Any] | None,
    *,
    account_id: str,
) -> str | None:
    """Return the fail-closed denial reason for the persistent local Key."""
    if not isinstance(key_status, Mapping) or not key_status.get("installed"):
        return "LOCAL_ORDER_KEY_MISSING"
    if str(key_status.get("account_id") or "").strip() != account_id:
        return "LOCAL_ORDER_KEY_ACCOUNT_MISMATCH"
    if key_status.get("valid") is not True:
        return "LOCAL_ORDER_KEY_INVALID:%s" % str(key_status.get("state") or "INVALID")
    return None


def evaluate_execution_admission(
    profile: str,
    *,
    account_id: str | None = None,
    host_id: str | None = None,
    strategy_id: str | None = None,
    configured_account_id: str | None = None,
    order_key_status: Mapping[str, Any] | None = None,
    authorization: Mapping[str, Any] | None = None,
    designation: Mapping[str, Any] | None = None,
    lease_envelope: Mapping[str, Any] | None = None,
    trusted_transport: bool = False,
    now_epoch: float | None = None,
) -> dict[str, Any]:
    """Decide whether one local order attempt may proceed.

    Policy problems never raise here; the caller inspects allowed, or calls
    require_execution_admission for an exception.
    """
    moment = time.time() if now_epoch is None else float(now_epoch)
    try:
        policy = resolve_account_policy(
            profile, account_id, configured_account_id=configured_account_id
        )
    except AccountPolicyRejected as exc:
        return _deny("ACCOUNT_POLICY_REJECTED:%s" % exc, profile=profile, account_id=account_id)

    base = {
        "profile": policy.profile,
        "account_id": policy.account_id,
        "host_id": host_id,
        "strategy_id": strategy_id,
    }
    if policy.production_readonly:
        return _deny("PRODUCTION_READ_ONLY", **base)

    key_denial = _order_key_denial(order_key_status, account_id=policy.account_id)
    if key_denial is not None:
        return _deny(key_denial, **base)

    denial = _authorization_denial(
        authorization, account_id=policy.account_id, strategy_id=strategy_id, now_epoch=moment
    )
    if denial is not None:
        return _deny(denial, **base)

    if not isinstance(designation, Mapping) or not designation.get("reachable"):
        return _deny(
            "COORDINATOR_UNREACHABLE",
            coordinator_reason=str((designation or {}).get("reason", "NOT_CONTACTED")),
            **base,
        )
    if not designation.get("eligible"):
        return _deny(
            "COORDINATOR_DENIES_HOST",
            coordinator_reason=str(designation.get("reason", "NOT_ELIGIBLE")),
            coordinator_lease_state=str(designation.get("lease_state", "UNKNOWN")),
            **base,
        )

    if lease_envelope is not None:
        # A lease is only audited here: leased execution is a later milestone,
        # so even a syntactically valid lease cannot open an order path today.
        leased = evaluate_local_execution(
            profile,
            account_id,
            host_id=host_id,
            lease_envelope=dict(lease_envelope),
            trusted_transport=trusted_transport,
            now_epoch=moment,
        )
        return _deny(
            str(leased.get("reason", "LEASED_EXECUTION_NOT_ENABLED")),
            lease_evaluated=True,
            **base,
        )

    verdict = {
        "allowed": True,
        "orders_enabled": False,
        "standing_order_switch_open": False,
        "reason": ADMITTED_REASON,
        "coordinator_lease_state": str(designation.get("lease_state", "UNKNOWN")),
        "coordinator_candidate_reason": str(designation.get("reason", "NOT_REPORTED")),
        "checked_at_epoch": moment,
    }
    verdict.update(base)
    return verdict


def require_execution_admission(profile: str, **kwargs: Any) -> dict[str, Any]:
    """Return the admission verdict or raise ExecutionAdmissionDenied."""
    verdict = evaluate_execution_admission(profile, **kwargs)
    if not verdict.get("allowed"):
        raise ExecutionAdmissionDenied(verdict)
    return verdict


def require_admission_for_root(
    root: Path,
    profile: str = "simulation",
    *,
    strategy_id: str | None = None,
    authorization: Mapping[str, Any] | None = None,
    timeout: float = 3.0,
    now_epoch: float | None = None,
) -> dict[str, Any]:
    """Resolve the local Coordinator identity and require an admission verdict.

    Scripts call this immediately before writing an order RPC request.
    """
    root = Path(root)
    endpoint, host_id = resolve_coordinator(root)
    # The account is deployment-local (machine.local.json), not the synthetic
    # repository default.  Passing it here keeps the armed control window and
    # the admission policy bound to the same real simulation account.
    gateway = load_gateway(root, profile)
    account_id = str(gateway.get("account_id") or "").strip() or None
    local_key = order_authorization_key_status(profile, account_id)
    designation = coordinator_designation(endpoint, profile, host_id, timeout=timeout)
    # The Coordinator is a coordination/observability service, not the Redis
    # order transport.  This deployment explicitly keeps it optional for the
    # single local simulation account.  All local gates above the RPC remain
    # mandatory; formal profiles never use this fallback.
    machine = load_machine_local(root)
    coordinator_config = machine.get("coordinator") if isinstance(machine, dict) else {}
    simulation_coordinator_optional = (
        profile == "simulation"
        and isinstance(coordinator_config, dict)
        and coordinator_config.get("simulation_execution_required") is False
    )
    if simulation_coordinator_optional and not bool(designation.get("eligible")):
        designation = dict(designation)
        designation.update({
            "reachable": True,
            "eligible": True,
            "lease_state": "LOCAL_SIMULATION_SINGLE_WRITER",
            "reason": "COORDINATOR_OPTIONAL_LOCAL_FALLBACK:%s" % str(designation.get("reason", "NOT_ELIGIBLE")),
            "fallback_used": True,
        })
    return require_execution_admission(
        profile,
        account_id=account_id,
        configured_account_id=account_id,
        host_id=host_id,
        strategy_id=strategy_id,
        order_key_status=local_key,
        authorization=authorization,
        designation=designation,
        now_epoch=now_epoch,
    )
