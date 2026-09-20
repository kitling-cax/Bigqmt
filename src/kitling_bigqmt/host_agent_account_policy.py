"""Fail-closed account and environment policy for the Windows Host Agent.

This module is the single authority for:
  * profile -> account mapping,
  * simulation/production environment validation,
  * production read-only enforcement,
  * local fencing against a Coordinator execution lease.

During M03 the Host Agent is read-only: no profile may enable orders, and a
formal (production) account is permanently denied any executor role.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .execution_lease_guard import LeaseRejected, verify_execution_lease


ACCOUNT_BY_PROFILE = {
    "simulation": "90000001",
    "production_readonly": "90000002",
}
# The repository defaults remain synthetic for tests and clean-room builds.
# These deployment IDs are explicitly accepted when supplied by the local
# machine overlay; they are not interchangeable across profiles.
DEPLOYMENT_ACCOUNT_BY_PROFILE = {
    "simulation": "99022040",
    "production_readonly": "8890526688",
}
PRODUCTION_PROFILE = "production_readonly"
PRODUCTION_ACCOUNT_ID = ACCOUNT_BY_PROFILE[PRODUCTION_PROFILE]


class AccountPolicyRejected(ValueError):
    """Raised when a profile/account combination violates local policy."""


@dataclass(frozen=True)
class AccountPolicy:
    profile: str
    account_id: str
    environment: str
    orders_enabled: bool
    execution_allowed: bool
    production_readonly: bool


def resolve_account_policy(
    profile: str,
    account_id: str | None = None,
    *,
    configured_account_id: str | None = None,
) -> AccountPolicy:
    """Resolve and validate a profile without opening any execution path.

    orders_enabled and execution_allowed are always False in the current
    read-only Host Agent release.  A production profile is additionally marked
    production_readonly so downstream callers can reject it even if a future
    simulation flag were to change.
    """
    if profile not in ACCOUNT_BY_PROFILE:
        raise AccountPolicyRejected("unknown profile: %s" % profile)
    configured = str(configured_account_id or "").strip()
    expected_account_id = configured or ACCOUNT_BY_PROFILE[profile]
    accepted_ids = {expected_account_id, ACCOUNT_BY_PROFILE[profile], DEPLOYMENT_ACCOUNT_BY_PROFILE[profile]}
    if account_id is not None and str(account_id) not in accepted_ids:
        raise AccountPolicyRejected(
            "account %s does not match profile %s" % (account_id, profile)
        )
    resolved_account_id = str(account_id) if account_id is not None else expected_account_id
    production_readonly = profile == PRODUCTION_PROFILE
    return AccountPolicy(
        profile=profile,
        account_id=resolved_account_id,
        environment="production" if production_readonly else "simulation",
        orders_enabled=False,
        execution_allowed=False,
        production_readonly=production_readonly,
    )


def evaluate_local_execution(
    profile: str,
    account_id: str | None = None,
    *,
    host_id: str | None = None,
    lease_envelope: dict[str, Any] | None = None,
    trusted_transport: bool = False,
    now_epoch: float | None = None,
    configured_account_id: str | None = None,
) -> dict[str, Any]:
    """Evaluate one local execution decision and always fail closed in M03.

    The return value is a human-readable verdict, never an order entry point.
    allowed remains False even when a syntactically valid simulation lease is
    supplied, because M03 does not yet include leased execution.
    """
    policy = resolve_account_policy(
        profile, account_id, configured_account_id=configured_account_id
    )
    if policy.production_readonly:
        return {
            "profile": policy.profile,
            "account_id": policy.account_id,
            "allowed": False,
            "orders_enabled": False,
            "reason": "PRODUCTION_READ_ONLY",
        }
    if not trusted_transport:
        return {
            "profile": policy.profile,
            "account_id": policy.account_id,
            "allowed": False,
            "orders_enabled": False,
            "reason": "NO_TRUSTED_TRANSPORT",
        }
    if lease_envelope is None:
        return {
            "profile": policy.profile,
            "account_id": policy.account_id,
            "allowed": False,
            "orders_enabled": False,
            "reason": "LEASED_EXECUTION_NOT_ENABLED_IN_M03",
        }
    try:
        verify_execution_lease(
            lease_envelope,
            expected_account_id=policy.account_id,
            expected_host_id=host_id or "",
            trusted_transport=True,
            now_epoch=now_epoch,
        )
    except LeaseRejected as exc:
        return {
            "profile": policy.profile,
            "account_id": policy.account_id,
            "allowed": False,
            "orders_enabled": False,
            "reason": str(exc),
        }
    return {
        "profile": policy.profile,
        "account_id": policy.account_id,
        "allowed": False,
        "orders_enabled": False,
        "reason": "LEASED_EXECUTION_NOT_ENABLED_IN_M03",
    }
