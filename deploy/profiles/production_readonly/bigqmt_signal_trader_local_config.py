# coding: utf-8
"""Formal QMT profile: full Bridge capability, runtime execution hard-locked."""

# This file is local-deployment material, not a shareable source configuration.
# Account binding makes a wrong QMT login fail closed; it does not authorize orders.
BIGQMT_ACCOUNT_ID = "90000002"
BIGQMT_ACCOUNT_TYPE = "STOCK"

BIGQMT_REDIS_CONFIG = {
    "transport": "redis",
    "host": "127.0.0.1",
    "port": 6380,
    "db": 5,
    "username": "",
    "password": "",
    "rpc_allow_order_methods": False,
    "rpc_allowed_methods": (
        "ping", "get_deployment_info", "probe_capabilities", "get_asset",
        "get_positions", "get_position_statistics", "query_stock_position",
        "query_orders", "query_trades", "get_ticks", "get_instrument",
        "get_instrument_type", "get_market_data", "get_market_data_ex",
        "get_local_data", "get_trading_dates", "get_holidays",
    ),
    "rpc_process_in_listener": True,
    "rpc_listener_methods": ("*",),
    "rpc_background_threads": False,
    "schedule_adjust": True,
    "schedule_adjust_interval": "100nMilliSecond",
    "full_tick_cache_enabled": False,
    "download_jobs_enabled": False,
    "exec_events_enabled": True,
    "execution_admission": {
        "environment": "PRODUCTION",
        "expected_qmt_python_dir": r"qmt\production_readonly\python",
        "runtime_control_required": True,
        "runtime_control_path": r"runtime_data\control\production\runtime_control.json",
        "orders_enabled": False,
        "execution_consumer_enabled": False,
        "preflight_admission": "BLOCKED",
        "parity_admission": "BLOCKED",
        "simulation_confirmation": "",
        "simulation_verified": False,
        "production_execution_approved": False,
        "production_confirmation": "",
        "allowed_strategy_names": (),
    },
}

# The two local QMTs contend for FormulaServer 58600.  The formal host client
# must use this Redis Bridge and keep its FormulaServer fast path disabled.
BIGQMT_FORMULA_SERVER_CONFIG = {"enabled": False}
