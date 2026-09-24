"""Validate the strategy registry without contacting QMT, Redis, or SQLite."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def validate(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    errors: list[str] = []
    strategies = payload.get("strategies")
    if not isinstance(strategies, list) or not strategies:
        errors.append("strategies must be a non-empty list")
        strategies = []
    ids: set[str] = set()
    for index, strategy in enumerate(strategies):
        prefix = f"strategies[{index}]"
        strategy_id = strategy.get("strategy_id")
        if not strategy_id or strategy_id in ids:
            errors.append(f"{prefix}.strategy_id must be unique")
        ids.add(strategy_id)
        for field in ("source_project", "asset_class", "version", "status", "sleeve_id"):
            if not strategy.get(field):
                errors.append(f"{prefix}.{field} is required")
        if strategy.get("formal_account_allowed") is not False:
            errors.append(f"{prefix}.formal_account_allowed must be false")
        execution_enabled = strategy.get("execution_enabled")
        if execution_enabled not in (True, False):
            errors.append(f"{prefix}.execution_enabled must be boolean")
        if execution_enabled is True:
            if strategy_id != "S10_D1_U25_NO_ALCOHOL_5D_SIM_MAIN_V1_1_15":
                errors.append(f"{prefix}.only the approved v1.1.15 sleeve may enable simulation execution")
            if strategy.get("status") != "SIMULATION_ONLY":
                errors.append(f"{prefix}.execution_enabled requires SIMULATION_ONLY status")
            if strategy.get("allowed_accounts") != ["90000001"]:
                errors.append(f"{prefix}.execution_enabled requires the synthetic simulation account")
            if strategy.get("execution_mode") != "SIMULATION_AUTOMATED_QMT_BRIDGE":
                errors.append(f"{prefix}.execution_mode is not the approved simulation bridge mode")
            activation = strategy.get("activation_policy")
            if not isinstance(activation, dict) or activation.get("startup_mode") != "ISOLATE_NEW":
                errors.append(f"{prefix}.execution_enabled requires ISOLATE_NEW activation")
        if not isinstance(strategy.get("initial_capital"), (int, float)) or strategy["initial_capital"] <= 0:
            errors.append(f"{prefix}.initial_capital must be positive")
        if strategy.get("max_capital", 0) < strategy.get("initial_capital", 0):
            errors.append(f"{prefix}.max_capital cannot be below initial_capital")
        universe = strategy.get("universe")
        if not isinstance(universe, dict) or not isinstance(universe.get("qmt_codes"), list):
            errors.append(f"{prefix}.universe.qmt_codes must be a list")
        elif universe.get("status") == "FROZEN_BASELINE" and not universe["qmt_codes"]:
            errors.append(f"{prefix}.universe cannot be empty for FROZEN_BASELINE")
        signal_contract = strategy.get("signal_contract")
        if not isinstance(signal_contract, dict) or not signal_contract.get("completed_bar_frequency"):
            errors.append(f"{prefix}.signal_contract.completed_bar_frequency is required")
    if payload.get("default_policy", {}).get("formal_orders_allowed") is not False:
        errors.append("default_policy.formal_orders_allowed must be false")
    return {"valid": not errors, "strategy_count": len(strategies), "errors": errors}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", type=Path, default=ROOT / "config" / "strategy_registry.json")
    args = parser.parse_args()
    result = validate(args.path)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
