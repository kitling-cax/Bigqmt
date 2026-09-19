"""Per-strategy local run switch for the native tray.

Fail-closed: the default for any strategy is off.  Only an explicit tray
toggle writes ``true``, and nothing in this module grants order capability
or starts a process.  The write is atomic and only touches
``config/strategy_runtime_policy.json``.

For the v1.1.15 simulator strategy we also mirror the value into the legacy
``simulation.v1_1_15_auto_run_enabled`` key so older consumers that still
search for that string keep seeing a consistent value.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "config" / "strategy_runtime_policy.json"
LEGACY_V1_1_15 = "S10_D1_U25_NO_ALCOHOL_5D_SIM_MAIN_V1_1_15"


def _load() -> dict:
    try:
        value = json.loads(PATH.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _write(value: dict) -> None:
    PATH.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=".strategy_runtime_policy.", suffix=".tmp", dir=str(PATH.parent))
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary, PATH)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _safe_strategy_id(value: str) -> str:
    stripped = str(value or "").strip()
    if not stripped or "/" in stripped or "\\" in stripped or stripped in {".", ".."}:
        raise ValueError("unsafe strategy_id: %r" % value)
    return stripped


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Toggle one strategy's local auto-run switch")
    parser.add_argument("--strategy-id", required=True)
    parser.add_argument("--enabled", choices=("true", "false"), required=True)
    parser.add_argument("--profile", choices=("simulation",), default="simulation",
                        help="per-strategy auto-run toggles are simulation-only")
    args = parser.parse_args(argv)
    enabled = args.enabled == "true"
    try:
        strategy_id = _safe_strategy_id(args.strategy_id)
    except ValueError as exc:
        print(json.dumps({"ok": False, "reason": str(exc), "orders_enabled": False}, ensure_ascii=False))
        return 2

    value = _load()
    value.setdefault("schema_version", 1)
    value.setdefault("simulation", {})
    value.setdefault("production", {})
    simulation = value["simulation"]
    strategies = simulation.setdefault("strategies", {})
    if not isinstance(strategies, dict):
        strategies = {}
    entry = strategies.get(strategy_id)
    if not isinstance(entry, dict):
        entry = {}
    entry["auto_run_enabled"] = enabled
    strategies[strategy_id] = entry
    simulation["strategies"] = strategies
    simulation["policy_note"] = "Per-strategy local run switches; none of them submits an order."
    if strategy_id == LEGACY_V1_1_15:
        simulation["v1_1_15_auto_run_enabled"] = enabled
        simulation.setdefault("v1_1_15_preflight_only_dates", [])
    _write(value)
    print(json.dumps({
        "ok": True,
        "profile": args.profile,
        "strategy_id": strategy_id,
        "enabled": enabled,
        "orders_enabled": False,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())