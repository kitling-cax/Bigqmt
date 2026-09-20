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
        # Production never has a writable runtime mode.  Simulation execution
        # is a persistent, local operator setting.  Coordinator is not part
        # of this gate; it only observes the resulting state.
        if self.environment.lower() != "simulation":
            return self._locked(value, "production runtime is permanently read-only")
        if not self._is_valid_simulation_enabled(value):
            return self._locked(
                value,
                str(value.get("lock_reason") or "simulation local execution authorization is missing or incomplete"),
            )
        return value

    def enable_simulation_strategy(
        self, *, account_id: str, strategy_id: str, approval_scope: str,
    ) -> dict[str, Any]:
        """Enable local simulation execution until an operator locks it.

        This writes local state only.  It has no expiry and never contacts the
        Coordinator, Redis, QMT, or a broker.  The persistent order Key,
        strategy switch, market-hours gate, reconciliation, and bridge checks
        remain mandatory at the actual order path.
        """
        if self.environment.lower() != "simulation":
            raise PermissionError("only the simulation runtime can be enabled")
        if not str(account_id).strip() or not str(strategy_id).strip():
            raise ValueError("account_id and strategy_id are required")
        now = time.time()
        value = {
            "schema_version": 3,
            "environment": "SIMULATION",
            "account_id": str(account_id).strip(),
            "mode": "SIMULATION_STRATEGY_EXECUTION_ENABLED",
            "orders_enabled": True,
            "execution_consumer_enabled": True,
            "preflight_admission": "ALLOWED",
            "parity_admission": "ALLOWED",
            "simulation_confirmation": "SIMULATION_ORDER_VALIDATED",
            "simulation_verified": False,
            "production_execution_approved": False,
            "production_confirmation": "",
            "strategy_id": str(strategy_id).strip(),
            "approval_scope": str(approval_scope).strip(),
            "enabled_at_epoch": now,
            "coordinator_mode": "MONITOR_ONLY",
        }
        _atomic_json_write(self.control_path, value)
        return value

    def arm_simulation_strategy(
        self,
        *,
        account_id: str,
        strategy_id: str,
        approval_scope: str,
        valid_for_seconds: int = 120,
    ) -> dict[str, Any]:
        """Backward-compatible alias; duration is intentionally ignored."""
        return self.enable_simulation_strategy(
            account_id=account_id, strategy_id=strategy_id, approval_scope=approval_scope
        )

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
    def _is_valid_simulation_enabled(value: dict[str, Any]) -> bool:
        persistent = (
            str(value.get("environment") or "").upper() == "SIMULATION"
            and str(value.get("mode") or "") == "SIMULATION_STRATEGY_EXECUTION_ENABLED"
            and str(value.get("account_id") or "").strip() != ""
            and str(value.get("strategy_id") or "").strip() != ""
            and value.get("orders_enabled") is True
            and value.get("execution_consumer_enabled") is True
            and str(value.get("preflight_admission") or "").upper() == "ALLOWED"
            and str(value.get("parity_admission") or "").upper() == "ALLOWED"
            and str(value.get("simulation_confirmation") or "") == "SIMULATION_ORDER_VALIDATED"
        )
        # Read old state files during migration, but never create new expiring
        # windows.  Existing operators can lock and re-enable to migrate.
        return persistent or RuntimeControl._is_valid_simulation_window(value)

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
