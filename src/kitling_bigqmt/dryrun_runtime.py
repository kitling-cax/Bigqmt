"""Project-gated entry point for local, non-broker Dry-run evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .dryrun_orders import DryRunOrderPlanner, DryRunRejected
from .state_store import RuntimeStateStore


@dataclass(frozen=True)
class DryRunRuntime:
    """Enforce project-level gates before a local intent can be persisted.

    Caller-supplied admissions are never an authority.  The project status is
    authoritative and defaults to BLOCKED when a field is missing.
    """

    store: RuntimeStateStore
    project_status: dict[str, Any]

    def evaluate(self, payload: dict[str, Any]) -> dict[str, Any]:
        environment = self.project_status.get("environment")
        if environment != "simulation":
            return self._blocked("project environment is not simulation")
        if bool(self.project_status.get("orders_enabled", True)):
            return self._blocked("project orders_enabled is not false")
        gates = self.project_status.get("dryrun_admission") or {}
        preflight = gates.get("preflight", "BLOCKED")
        parity = gates.get("parity", "BLOCKED")
        if preflight != "ALLOWED":
            return self._blocked("project preflight admission is %s" % preflight)
        if parity != "ALLOWED":
            return self._blocked("project parity admission is %s" % parity)
        candidate = dict(payload)
        candidate["environment"] = "simulation"
        candidate["orders_enabled"] = False
        candidate["preflight_admission"] = "ALLOWED"
        candidate["parity_admission"] = "ALLOWED"
        try:
            return DryRunOrderPlanner(self.store).plan(candidate)
        except DryRunRejected as exc:
            return self._blocked(str(exc))

    @staticmethod
    def _blocked(reason: str) -> dict[str, Any]:
        return {
            "result": "BLOCKED",
            "state": "BLOCKED",
            "reason": reason,
            "orders_enabled": False,
            "broker_call_made": False,
        }
