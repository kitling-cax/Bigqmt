"""Fail-closed admission policy for BigQMT order and cancel capabilities.

This module intentionally contains no QMT calls.  It is shared by the RPC
entry and the in-process signal worker so that neither path can bypass the
same simulation-only release gates.  Keep syntax compatible with QMT Python
3.6.
"""

import json
import os
import time


_SIMULATION_CONFIRMATION = "SIMULATION_ORDER_VALIDATED"
_PRODUCTION_CONFIRMATION = "PRODUCTION_ORDER_APPROVED"


def _as_bool(value):
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in ("1", "true", "yes", "y", "on")


def _as_upper(value):
    return str(value or "").strip().upper()


class OrderAdmissionPolicy(object):
    """Explicit, auditable gates before a simulation order can leave QMT.

    A missing key is a rejection.  This is deliberately stricter than the
    RPC-method switch: opening ``rpc_allow_order_methods`` alone must never
    enable an order.  The release phrase makes an accidental boolean copy
    insufficient, while the strategy allowlist keeps one approved sleeve from
    submitting under another strategy name.
    """

    def __init__(self, config=None, expected_account_id=""):
        self.config = dict(config or {})
        self.expected_account_id = str(
            self.config.get("account_id") or expected_account_id or "").strip()

    def _effective_config(self):
        config = dict(self.config)
        if not _as_bool(config.get("runtime_control_required")):
            return config, ""
        path = str(config.get("runtime_control_path") or "").strip()
        if not path:
            return config, "runtime control path is missing"
        try:
            with open(path, "r") as stream:
                control = json.load(stream)
        except Exception as exc:
            return config, "runtime control unavailable: %s" % exc
        if not isinstance(control, dict):
            return config, "runtime control must be a JSON object"
        if _as_upper(control.get("environment")) != _as_upper(config.get("environment")):
            return config, "runtime control environment mismatch"
        control_account = str(control.get("account_id") or "").strip()
        if self.expected_account_id and control_account != self.expected_account_id:
            return config, "runtime control account mismatch"
        try:
            valid_until = float(control.get("valid_until_epoch") or 0)
        except (TypeError, ValueError):
            valid_until = 0
        if valid_until <= time.time():
            return config, "runtime control is missing or expired"
        # Only these dynamic gates can be supplied by Tray.  Installation
        # identity and strategy allowlists remain in the environment-specific
        # local QMT config and cannot be changed by a heartbeat file.
        dynamic_keys = (
            "orders_enabled", "execution_consumer_enabled",
            "preflight_admission", "parity_admission",
            "simulation_confirmation", "simulation_verified",
            "production_execution_approved", "production_confirmation",
        )
        for key in dynamic_keys:
            config[key] = control.get(key)
        return config, ""

    def evaluate(self, params=None, method=""):
        params = dict(params or {})
        config, control_error = self._effective_config()
        if control_error:
            return False, control_error
        environment = _as_upper(config.get("environment"))
        if environment not in ("SIMULATION", "PRODUCTION"):
            return False, "environment must be SIMULATION or PRODUCTION"
        expected_dir = str(config.get("expected_qmt_python_dir") or "").strip()
        detected_dir = str(config.get("detected_qmt_python_dir") or "").strip()
        if not expected_dir or not detected_dir:
            return False, "QMT installation identity is missing"
        if os.path.normcase(os.path.abspath(expected_dir)) != os.path.normcase(
                os.path.abspath(detected_dir)):
            return False, "QMT installation identity mismatch"
        if not _as_bool(config.get("orders_enabled")):
            return False, "execution_admission.orders_enabled is false"
        if not _as_bool(config.get("execution_consumer_enabled")):
            return False, "execution consumer is disabled"
        if _as_upper(config.get("preflight_admission")) != "ALLOWED":
            return False, "preflight admission is not ALLOWED"
        if _as_upper(config.get("parity_admission")) != "ALLOWED":
            return False, "strategy parity admission is not ALLOWED"
        if environment == "SIMULATION":
            if str(config.get("simulation_confirmation") or "").strip() != _SIMULATION_CONFIRMATION:
                return False, "simulation confirmation is missing"
        else:
            # Code capability is common to both environments, but a production
            # release is deliberately harder than a simulation release.  These
            # values belong only in the separately deployed production-local
            # config after the documented simulation acceptance and a separate
            # user approval; their defaults are all false/empty.
            if not _as_bool(config.get("simulation_verified")):
                return False, "simulation_verified is false"
            if not _as_bool(config.get("production_execution_approved")):
                return False, "production execution is not approved"
            if str(config.get("production_confirmation") or "").strip() != _PRODUCTION_CONFIRMATION:
                return False, "production confirmation is missing"

        account_id = str(params.get("account_id") or "").strip()
        if not account_id:
            account = params.get("account")
            if isinstance(account, dict):
                account_id = str(account.get("account_id") or account.get("accountID") or "").strip()
            elif account:
                account_id = str(account).strip()
        if not self.expected_account_id or not account_id:
            return False, "broker account identity is missing"
        if account_id != self.expected_account_id:
            return False, "request account does not match bridge account"

        allowed_names = config.get("allowed_strategy_names") or ()
        allowed_names = set(str(name).strip() for name in allowed_names if str(name).strip())
        strategy_name = str(params.get("strategy_name") or "").strip()
        if not allowed_names:
            return False, "no strategy is allowlisted for execution"
        if strategy_name not in allowed_names:
            return False, "strategy is not allowlisted for execution"
        return True, "ALLOWED"

    def status(self):
        """Safe diagnostic view.  Never echo an approval phrase or secrets."""
        config, control_error = self._effective_config()
        allowed, reason = self.evaluate({"account_id": self.expected_account_id,
                                         "strategy_name": ""})
        return {
            "environment": _as_upper(config.get("environment")),
            "orders_enabled": _as_bool(config.get("orders_enabled")),
            "execution_consumer_enabled": _as_bool(
                config.get("execution_consumer_enabled")),
            "preflight_admission": _as_upper(config.get("preflight_admission")),
            "parity_admission": _as_upper(config.get("parity_admission")),
            "allowlisted_strategy_count": len(
                config.get("allowed_strategy_names") or ()),
            "simulation_verified": _as_bool(config.get("simulation_verified")),
            "production_execution_approved": _as_bool(
                config.get("production_execution_approved")),
            "runtime_control_required": _as_bool(
                config.get("runtime_control_required")),
            "runtime_control_error": control_error,
            "allowed": allowed,
            "reason": reason,
        }
