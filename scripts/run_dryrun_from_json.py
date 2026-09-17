"""Evaluate one local Dry-run payload under the current project safety gates."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kitling_bigqmt.dryrun_runtime import DryRunRuntime  # noqa: E402
from kitling_bigqmt.state_store import RuntimeStateStore  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one non-broker BigQMT Dry-run evaluation.")
    parser.add_argument("--intent", type=Path, required=True, help="JSON candidate intent")
    parser.add_argument("--status", type=Path, default=ROOT / "progress" / "current_status.json")
    parser.add_argument("--state-db", type=Path, default=ROOT / "runtime_data" / "state" / "simulation" / "qmt_runtime.sqlite3")
    parser.add_argument("--audit-dir", type=Path, default=ROOT / "runtime_data" / "audit" / "simulation")
    args = parser.parse_args()
    payload = json.loads(args.intent.read_text(encoding="utf-8"))
    status = json.loads(args.status.read_text(encoding="utf-8"))
    result = DryRunRuntime(RuntimeStateStore(args.state_db, args.audit_dir), status).evaluate(payload)
    result["orders_enabled"] = False
    result["mode"] = "LOCAL_DRYRUN_NO_QMT_RPC"
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["result"] in ("RECORDED", "DUPLICATE", "BLOCKED") else 2


if __name__ == "__main__":
    raise SystemExit(main())
