"""Account-scoped local authorization-Key observations.

The Coordinator receives only a SHA-256 fingerprint and local observation
metadata.  It never receives the Key's plaintext.  Two distinct hosts with a
currently valid Key for one account force an account-wide read-only lockdown.
This is an eligibility layer, not an order-authorisation bypass.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


SIMULATION_ACCOUNT = "90000001"
PRODUCTION_ACCOUNT = "90000002"
SIMULATION = "SIMULATION"
PRODUCTION = "PRODUCTION"


def _deployment_account_ids() -> dict[str, str]:
    """Real per-host accounts come from gitignored machine.local.json, never
    from the public repository.  Empty strings mean 'no local override'."""
    try:
        from . import machine_config

        machine = machine_config.load_machine_local(machine_config.project_root())
        return {
            "simulation": str(machine_config.machine_environment(machine, "simulation").get("account_id") or "").strip(),
            "production_readonly": str(machine_config.machine_environment(machine, "production_readonly").get("account_id") or "").strip(),
        }
    except Exception:
        return {}


@dataclass(frozen=True)
class KeyObservation:
    account_id: str
    host_id: str
    environment: str
    key_fingerprint: str
    observed_at: float
    expires_at: float
    valid: bool


@dataclass(frozen=True)
class AccountAuthority:
    account_id: str
    environment: str
    state: str
    eligible_host_id: str | None
    valid_host_ids: tuple[str, ...]
    execution_eligible: bool
    orders_enabled: bool = False


def expected_environment(account_id: str) -> str:
    deploy = _deployment_account_ids()
    if account_id in {SIMULATION_ACCOUNT, deploy.get("simulation", "")}:
        return SIMULATION
    if account_id in {PRODUCTION_ACCOUNT, deploy.get("production_readonly", "")}:
        return PRODUCTION
    raise ValueError("unknown account")


def reconcile_account_authority(
    account_id: str,
    observations: Iterable[KeyObservation],
    *,
    now_epoch: float,
    simulation_execution_policy: bool = False,
    production_execution_policy: bool = False,
) -> AccountAuthority:
    """Determine one account's safe authority state without granting a lease."""
    environment = expected_environment(account_id)
    valid_hosts = sorted({
        item.host_id
        for item in observations
        if item.account_id == account_id
        and item.environment == environment
        and item.valid
        and item.expires_at > now_epoch
        and item.host_id.strip()
        and item.key_fingerprint.strip()
    })
    if not valid_hosts:
        return AccountAuthority(account_id, environment, "NO_VALID_KEY_READONLY", None, (), False)
    if len(valid_hosts) > 1:
        return AccountAuthority(
            account_id, environment, "DUPLICATE_KEY_LOCKDOWN", None, tuple(valid_hosts), False
        )
    host_id = valid_hosts[0]
    policy_open = simulation_execution_policy if environment == SIMULATION else production_execution_policy
    if not policy_open:
        return AccountAuthority(
            account_id, environment, "SINGLE_KEY_POLICY_READONLY", host_id, (host_id,), False
        )
    # This flag marks a *candidate for a future lease*.  The public result
    # deliberately keeps orders_enabled false until lease + typed intent +
    # local QMT checks are all implemented and explicitly authorised.
    return AccountAuthority(
        account_id, environment, "SINGLE_KEY_LEASE_ELIGIBLE", host_id, (host_id,), True
    )
