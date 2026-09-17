# coding: utf-8
"""Simulation-only local configuration for account 90000001."""

BIGQMT_ACCOUNT_ID = "90000001"
BIGQMT_ACCOUNT_TYPE = "STOCK"

BIGQMT_REDIS_CONFIG = {
    "transport": "redis",
    "host": "127.0.0.1",
    "port": 6379,
    "db": 5,
    "username": "",
    "password": "",
    # RPC exposure alone is insufficient: the runtime-control file is the
    # short-lived second gate and starts locked.  This permits only the
    # allowlisted v1.1.15 simulation sleeve to reach that second gate.
    "rpc_allow_order_methods": True,
    "rpc_process_in_listener": True,
    "rpc_listener_methods": ("*",),
    "rpc_background_threads": False,
    "schedule_adjust": True,
    "schedule_adjust_interval": "100nMilliSecond",
    "full_tick_cache_enabled": False,
    "download_jobs_enabled": False,
    "exec_events_enabled": True,
    "execution_admission": {
        "environment": "SIMULATION",
        "expected_qmt_python_dir": r"C:\BigQMT\work\国金QMT交易端模拟\python",
        "runtime_control_required": True,
        "runtime_control_path": r"C:\BigQMT\work\kitling_bigqmt\runtime_data\control\simulation\runtime_control.json",
        "orders_enabled": False,
        "execution_consumer_enabled": False,
        "preflight_admission": "BLOCKED",
        "parity_admission": "BLOCKED",
        "simulation_confirmation": "",
        "simulation_verified": False,
        "production_execution_approved": False,
        "production_confirmation": "",
        "allowed_strategy_names": (
            "S10_D1_U25_NO_ALCOHOL_5D_SIM_MAIN_V1_1_15",
        ),
    },
}
