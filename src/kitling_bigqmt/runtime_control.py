"""Fail-closed, local runtime-control state for BigQMT Tray.

This is deliberately separate from broker connectivity.  It persists an
operator-visible order lock and contains no QMT/Redis/order API code.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .state_store import utc_now


def _atomic_json_write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


@dataclass(frozen=True)
class RuntimeControl:
    control_path: Path
    environment: str = "simulation"

    def status(self) -> dict[str, Any]:
        try:
            value = json.loads(self.control_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            value = {}
        if str(value.get("environment", "")).lower() != self.environment.lower():
            return self._default("missing, malformed, or wrong-environment control state")
        # Production never has a writable runtime mode.  Simulation can only
        # be armed through ``arm_simulation_strategy`` below, and only for a
        # short-lived, account-bound window.  A stale or partial file fails
        # closed rather than preserving an old ability to submit an order.
        if self.environment.lower() != "simulation":
            return self._locked(value, "production runtime is permanently read-only")
        if not self._is_valid_simulation_window(value):
            return self._locked(
                value,
                str(value.get("lock_reason") or "simulation execution window is missing, expired, or incomplete"),
            )
        return value

    def arm_simulation_strategy(
        self,
        *,
        account_id: str,
        strategy_id: str,
        approval_scope: str,
        valid_for_seconds: int = 120,
    ) -> dict[str, Any]:
        """Create one short, simulation-only QMT execution window.

        This does not contact Redis or QMT and it never works for the formal
        profile.  The caller must complete live quote/account/preflight checks
        *before* arming it, and must lock it again after a submit response or
        timeout.  The capped duration prevents a Tray restart from leaving an
        old order permission behind.
        """
        if self.environment.lower() != "simulation":
            raise PermissionError("only the simulation runtime can be armed")
        if not str(account_id).strip() or not str(strategy_id).strip():
            raise ValueError("account_id and strategy_id are required")
        duration = int(valid_for_seconds)
        if duration < 10 or duration > 300:
            raise ValueError("valid_for_seconds must be between 10 and 300")
        now = time.time()
        value = {
            "schema_version": 2,
            "environment": "SIMULATION",
            "account_id": str(account_id).strip(),
            "mode": "SIMULATION_STRATEGY_EXECUTION_WINDOW",
            "valid_until_epoch": now + duration,
            "orders_enabled": True,
            "execution_consumer_enabled": True,
            "preflight_admission": "ALLOWED",
            # This admits the separately approved QMT implementation boundary;
            # it does not claim PTrade tick/data parity.
            "parity_admission": "ALLOWED",
            "simulation_confirmation": "SIMULATION_ORDER_VALIDATED",
            "simulation_verified": False,
            "production_execution_approved": False,
            "production_confirmation": "",
            "strategy_id": str(strategy_id).strip(),
            "approval_scope": str(approval_scope).strip(),
            "armed_at_epoch": now,
        }
        _atomic_json_write(self.control_path, value)
        return value

    def lock_orders(self, reason: str) -> dict[str, Any]:
        value = {
            "schema_version": 1,
            "environment": self.environment,
            "mode": "READ_ONLY_LOCKED",
            "orders_enabled": False,
            "execution_consumer_enabled": False,
            "locked_at": utc_now(),
            "lock_reason": reason or "operator lock",
        }
        _atomic_json_write(self.control_path, value)
        return value

    @staticmethod
    def _is_valid_simulation_window(value: dict[str, Any]) -> bool:
        try:
            valid_until = float(value.get("valid_until_epoch") or 0)
        except (TypeError, ValueError):
            valid_until = 0
        return (
            str(value.get("environment") or "").upper() == "SIMULATION"
            and str(value.get("mode") or "") == "SIMULATION_STRATEGY_EXECUTION_WINDOW"
            and str(value.get("account_id") or "").strip() != ""
            and str(value.get("strategy_id") or "").strip() != ""
            and value.get("orders_enabled") is True
            and value.get("execution_consumer_enabled") is True
            and str(value.get("preflight_admission") or "").upper() == "ALLOWED"
            and str(value.get("parity_admission") or "").upper() == "ALLOWED"
            and str(value.get("simulation_confirmation") or "") == "SIMULATION_ORDER_VALIDATED"
            and valid_until > time.time()
        )

    @staticmethod
    def _locked(value: dict[str, Any], reason: str) -> dict[str, Any]:
        locked = dict(value)
        locked["orders_enabled"] = False
        locked["execution_consumer_enabled"] = False
        locked["mode"] = "READ_ONLY_LOCKED"
        locked["lock_reason"] = reason
        return locked

    def _default(self, reason: str) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "environment": self.environment,
            "mode": "READ_ONLY_LOCKED",
            "orders_enabled": False,
            "execution_consumer_enabled": False,
            "lock_reason": reason,
        }
