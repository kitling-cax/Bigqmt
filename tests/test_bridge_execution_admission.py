import importlib.util
import importlib
import sys
import types
from pathlib import Path

import pytest


BRIDGE_ROOT = Path(__file__).resolve().parents[1] / "staging" / "qmt_bridge_simulation"
MODULE_PATH = BRIDGE_ROOT / "bigqmt_signal_trader" / "execution_admission.py"
SPEC = importlib.util.spec_from_file_location("bridge_execution_admission", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
OrderAdmissionPolicy = MODULE.OrderAdmissionPolicy


def _released_policy():
    return OrderAdmissionPolicy({
        "environment": "simulation",
        "expected_qmt_python_dir": r"F:\sim\python",
        "detected_qmt_python_dir": r"F:\sim\python",
        "orders_enabled": True,
        "execution_consumer_enabled": True,
        "preflight_admission": "ALLOWED",
        "parity_admission": "ALLOWED",
        "simulation_confirmation": "SIMULATION_ORDER_VALIDATED",
        "allowed_strategy_names": ["v1_1_15"],
    }, expected_account_id="90000001")


def test_missing_or_partial_policy_is_fail_closed():
    allowed, reason = OrderAdmissionPolicy().evaluate({"account_id": "90000001"})
    assert allowed is False
    assert "environment" in reason

    config = _released_policy().config
    config["parity_admission"] = "BLOCKED"
    allowed, reason = OrderAdmissionPolicy(config, "90000001").evaluate(
        {"account_id": "90000001", "strategy_name": "v1_1_15"})
    assert allowed is False
    assert "parity" in reason


def test_simulation_release_requires_matching_account_and_strategy():
    policy = _released_policy()
    assert policy.evaluate({"account_id": "90000001", "strategy_name": "v1_1_15"}) == (True, "ALLOWED")
    assert policy.evaluate({"account_id": "99022041", "strategy_name": "v1_1_15"})[0] is False
    assert policy.evaluate({"account_id": "90000001", "strategy_name": "other"})[0] is False


def test_terminal_identity_mismatch_is_fail_closed():
    config = dict(_released_policy().config)
    config["detected_qmt_python_dir"] = r"F:\formal\python"
    allowed, reason = OrderAdmissionPolicy(config, "90000001").evaluate(
        {"account_id": "90000001", "strategy_name": "v1_1_15"})
    assert allowed is False
    assert "installation identity mismatch" in reason


def test_required_runtime_control_must_be_fresh_and_match_environment(tmp_path):
    config = dict(_released_policy().config)
    control_path = tmp_path / "runtime_control.json"
    config.update({
        "runtime_control_required": True,
        "runtime_control_path": str(control_path),
    })
    policy = OrderAdmissionPolicy(config, "90000001")
    assert policy.evaluate(
        {"account_id": "90000001", "strategy_name": "v1_1_15"})[0] is False

    import json
    import time
    control_path.write_text(json.dumps({
        "environment": "SIMULATION",
        "account_id": "90000001",
        "valid_until_epoch": time.time() + 30,
        "orders_enabled": True,
        "execution_consumer_enabled": True,
        "preflight_admission": "ALLOWED",
        "parity_admission": "ALLOWED",
        "simulation_confirmation": "SIMULATION_ORDER_VALIDATED",
    }), encoding="utf-8")
    assert policy.evaluate(
        {"account_id": "90000001", "strategy_name": "v1_1_15"}) == (True, "ALLOWED")


def test_production_capability_is_present_but_stays_fail_closed_without_separate_approval():
    production = _released_policy().config
    production.update({
        "environment": "PRODUCTION",
        "simulation_confirmation": "",
        "simulation_verified": False,
        "production_execution_approved": False,
        "production_confirmation": "",
    })
    policy = OrderAdmissionPolicy(production, "90000001")
    assert policy.evaluate({"account_id": "90000001", "strategy_name": "v1_1_15"})[0] is False

    production.update({
        "simulation_verified": True,
        "production_execution_approved": True,
        "production_confirmation": "PRODUCTION_ORDER_APPROVED",
    })
    policy = OrderAdmissionPolicy(production, "90000001")
    assert policy.evaluate({"account_id": "90000001", "strategy_name": "v1_1_15"}) == (True, "ALLOWED")


def test_formal_profile_is_account_bound_and_read_only_whitelisted():
    profile_path = (Path(__file__).resolve().parents[1] / "deploy" / "profiles" /
                    "production_readonly" / "bigqmt_signal_trader_local_config.py")
    spec = importlib.util.spec_from_file_location("formal_rc3_profile", profile_path)
    profile = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(profile)
    config = profile.BIGQMT_REDIS_CONFIG
    admission = config["execution_admission"]
    assert profile.BIGQMT_ACCOUNT_ID == "90000002"
    assert config["rpc_allow_order_methods"] is False
    assert "submit_order" not in config["rpc_allowed_methods"]
    assert "cancel_order" not in config["rpc_allowed_methods"]
    assert admission["orders_enabled"] is False
    assert admission["execution_consumer_enabled"] is False
    assert admission["preflight_admission"] == "BLOCKED"
    assert admission["parity_admission"] == "BLOCKED"


def test_simulation_profile_exposes_only_the_dynamically_guarded_v1_1_15_route():
    profile_path = (Path(__file__).resolve().parents[1] / "deploy" / "profiles" /
                    "simulation" / "bigqmt_signal_trader_local_config.py")
    spec = importlib.util.spec_from_file_location("simulation_exec_profile", profile_path)
    profile = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(profile)
    config = profile.BIGQMT_REDIS_CONFIG
    admission = config["execution_admission"]
    assert profile.BIGQMT_ACCOUNT_ID == "90000001"
    assert config["rpc_allow_order_methods"] is True
    assert admission["orders_enabled"] is False
    assert admission["execution_consumer_enabled"] is False
    assert admission["allowed_strategy_names"] == ("S10_D1_U25_NO_ALCOHOL_5D_SIM_MAIN_V1_1_15",)


def _load_bridge_submodule(name):
    package_name = "bigqmt_signal_trader"
    old_modules = {
        key: value for key, value in sys.modules.items()
        if key == package_name or key.startswith(package_name + ".")
    }
    for key in list(old_modules):
        sys.modules.pop(key, None)
    package = types.ModuleType(package_name)
    package.__path__ = [str(BRIDGE_ROOT / package_name)]
    package.__package__ = package_name
    sys.modules[package_name] = package
    try:
        return importlib.import_module(package_name + "." + name), old_modules
    except Exception:
        for key in list(sys.modules):
            if key == package_name or key.startswith(package_name + "."):
                sys.modules.pop(key, None)
        sys.modules.update(old_modules)
        raise


def _restore_bridge_modules(old_modules):
    for key in list(sys.modules):
        if key == "bigqmt_signal_trader" or key.startswith("bigqmt_signal_trader."):
            sys.modules.pop(key, None)
    sys.modules.update(old_modules)


def test_adapter_factory_receives_released_policy_without_code_change():
    module, old_modules = _load_bridge_submodule("adapter_factory")
    try:
        config = {
            "mode": "bigqmt",
            "account_id": "90000001",
            "account_type": "STOCK",
            "qmt_api": {},
            "execution_admission": dict(_released_policy().config),
        }
        app = module.build_app(context_info=object(), config=config)
        assert app.order_gateway.admission.evaluate(
            {"account_id": "90000001", "strategy_name": "v1_1_15"},
            method="submit_order",
        ) == (True, "ALLOWED")
    finally:
        _restore_bridge_modules(old_modules)


def test_cancel_second_gate_keeps_strategy_identity():
    module, old_modules = _load_bridge_submodule("adapters.order_guarded")
    try:
        class Gateway(object):
            def __init__(self):
                self.cancelled = False
                self.account_type = "STOCK"
                self.combo_type = 1101
                self.price_type = 11
                self.quick_trade = 2
                self.get_trade_detail_data = None

            def cancel(self, order_ref, account_id=None):
                self.cancelled = True
                return "cancel-requested"

        gateway = Gateway()
        guarded = module.GuardedOrderGateway(gateway, _released_policy())
        result = guarded.cancel(object(), account_id="90000001", strategy_name="v1_1_15")
        assert result == "cancel-requested"
        assert gateway.cancelled is True
        assert not hasattr(guarded, "gateway")
    finally:
        _restore_bridge_modules(old_modules)


def test_rpc_rejects_every_order_route_before_gateway_call():
    rpc_module, old_modules = _load_bridge_submodule("redis_rpc")
    try:
        blocked_config = dict(_released_policy().config)
        blocked_config["parity_admission"] = "BLOCKED"
        policy = OrderAdmissionPolicy(blocked_config, "90000001")

        class Gateway(object):
            def __init__(self):
                self.admission = policy
                self.calls = 0
                self.account_type = "STOCK"

            def submit(self, request):
                self.calls += 1

            def cancel(self, order_ref, account_id=None, strategy_name=None):
                self.calls += 1

            def passorder_passthrough(self, **kwargs):
                self.calls += 1

        gateway = Gateway()
        handlers = rpc_module.BigQmtRpcHandlers(
            account_id="90000001",
            market_data=object(),
            position_provider=object(),
            order_gateway=gateway,
            allow_order_methods=True,
        )
        cases = (
            ("submit_order", {"account_id": "90000001", "strategy_name": "v1_1_15"}),
            ("submit_orders_batch", {"account_id": "90000001", "strategy_name": "v1_1_15"}),
            ("passorder", {"account_id": "90000001", "strategy_name": "v1_1_15"}),
            ("cancel_order", {"account_id": "90000001", "strategy_name": "v1_1_15"}),
        )
        for method, params in cases:
            with pytest.raises(PermissionError, match="parity"):
                handlers.handle(method, params)
        assert gateway.calls == 0
    finally:
        _restore_bridge_modules(old_modules)


def test_cancel_requires_broker_attribution_to_requested_strategy():
    rpc_module, old_modules = _load_bridge_submodule("redis_rpc")
    try:
        policy = _released_policy()

        class OtherOrder(object):
            order_sys_id = "ORDER-1"
            strategy_name = "manual"
            user_order_id = ""

        class Gateway(object):
            def __init__(self):
                self.admission = policy
                self.cancel_calls = 0
                self.account_type = "STOCK"

            def query_orders_strict(self, account_id, strategy_name):
                return [OtherOrder()]

            def cancel(self, order_ref, account_id=None, strategy_name=None):
                self.cancel_calls += 1

        gateway = Gateway()
        handlers = rpc_module.BigQmtRpcHandlers(
            account_id="90000001",
            market_data=object(),
            position_provider=object(),
            order_gateway=gateway,
            allow_order_methods=True,
        )
        with pytest.raises(PermissionError, match="not attributable"):
            handlers.handle("cancel_order", {
                "account_id": "90000001",
                "strategy_name": "v1_1_15",
                "order_sys_id": "ORDER-1",
            })
        assert gateway.cancel_calls == 0
    finally:
        _restore_bridge_modules(old_modules)
