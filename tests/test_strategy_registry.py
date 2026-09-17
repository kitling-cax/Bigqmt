import json
from pathlib import Path

from scripts.validate_strategy_registry import validate


def test_project_strategy_registry_is_valid():
    path = Path(__file__).resolve().parents[1] / "config" / "strategy_registry.json"
    result = validate(path)
    assert result == {"valid": True, "strategy_count": 2, "errors": []}


def test_strategy_registry_rejects_formal_execution(tmp_path: Path):
    path = tmp_path / "registry.json"
    path.write_text(
        json.dumps(
            {
                "default_policy": {"formal_orders_allowed": False},
                "strategies": [
                    {
                        "strategy_id": "A",
                        "source_project": "review",
                        "asset_class": "ETF",
                        "version": "1",
                        "status": "SIMULATION_ONLY",
                        "sleeve_id": "A",
                        "initial_capital": 100,
                        "max_capital": 100,
                        "formal_account_allowed": True,
                        "execution_enabled": True,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    result = validate(path)
    assert result["valid"] is False
    assert any("formal_account_allowed" in error for error in result["errors"])
