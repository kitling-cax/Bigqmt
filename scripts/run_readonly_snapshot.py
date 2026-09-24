"""Collect one read-only simulation QMT snapshot and persist it on F:."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kitling_bigqmt.redis_resp import RedisRespClient
from kitling_bigqmt.readonly_rpc import ReadOnlyBigQmtClient
from kitling_bigqmt.snapshot import collect_readonly_snapshot
from kitling_bigqmt.state_store import RuntimeStateStore
from kitling_bigqmt.machine_config import load_gateway


def main() -> int:
    parser = argparse.ArgumentParser(description="Persist one BigQMT read-only account snapshot.")
    parser.add_argument("--profile", choices=("simulation", "production_readonly"), default="simulation")
    parser.add_argument("--config", default=None)
    arguments = parser.parse_args()
    profile = arguments.profile
    config = load_gateway(ROOT, profile) if arguments.config is None else json.loads(Path(arguments.config).read_text(encoding="utf-8"))
    redis_config = dict(config["redis"])
    client = ReadOnlyBigQmtClient(
        redis=RedisRespClient(**redis_config),
        account_id=str(config["account_id"]),
        timeout_seconds=float(config.get("rpc_timeout_seconds", 12)),
    )
    bundle = collect_readonly_snapshot(client, list(config.get("quote_codes") or []))
    # The explicit gateway file carries portable defaults, while
    # machine.local.json is authoritative for the host's relocated data root.
    # Use the effective loader for persistence paths so an explicit `--config`
    # cannot accidentally write a second stale state/ tree beside the project.
    effective = load_gateway(ROOT, profile)
    state_db = Path(str(effective.get("state_db") or ROOT / "runtime_data" / "state" / "simulation" / "qmt_runtime.sqlite3"))
    audit_dir = Path(str(effective.get("audit_dir") or ROOT / "runtime_data" / "audit" / "simulation"))
    store = RuntimeStateStore(state_db, audit_dir)
    run_id = store.record_snapshot(str(config["environment"]), str(config["account_id"]), bundle)
    data = bundle["asset"].get("data") or {}
    print(json.dumps({
        "status": "PASSED",
        "run_id": run_id,
        "total_asset": data.get("total_asset"),
        "positions": len(bundle["positions"].get("data") or {}),
        "orders": len(bundle["orders"].get("data") or []),
        "trades": len(bundle["trades"].get("data") or []),
        "quotes": len(bundle["quotes"].get("data") or {}),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
