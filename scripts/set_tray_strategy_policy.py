"""Fail-closed policy switches used by the native one-account tray EXEs."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "config" / "strategy_runtime_policy.json"


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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=("simulation", "production_readonly"), required=True)
    parser.add_argument("--enabled", choices=("true", "false"), required=True)
    args = parser.parse_args()
    enabled = args.enabled == "true"
    value = _load()
    value.setdefault("schema_version", 1)
    value.setdefault("simulation", {})
    value.setdefault("production", {})
    if args.profile == "simulation":
        value["simulation"]["v1_1_15_auto_run_enabled"] = enabled
        value["simulation"].setdefault("v1_1_15_preflight_only_dates", [])
        value["simulation"]["policy_note"] = "Native tray master switch; it does not itself submit an order."
    else:
        value["production"]["strategy_recovery_enabled"] = enabled
        value["production"]["policy_note"] = "Recovery intent only; production order capability remains permanently locked."
    _write(value)
    print(json.dumps({"ok": True, "profile": args.profile, "enabled": enabled, "orders_enabled": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
