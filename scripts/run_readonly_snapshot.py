"""Collect one read-only simulation QMT snapshot and persist it on F:."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kitling_bigqmt.redis_resp import RedisRespClient
from kitling_bigqmt.readonly_rpc import ReadOnlyBigQmtClient
from kitling_bigqmt.snapshot import collect_readonly_snapshot
from kitling_bigqmt.state_store import RuntimeStateStore
from kitling_bigqmt.machine_config import apply_gateway_overrides, load_gateway


def main() -> int:
    parser = argparse.ArgumentParser(description="Persist one BigQMT read-only simulation snapshot.")
    parser.add_argument("--config", default=None)
    arguments = parser.parse_args()

    # machine.local.json is authoritative for account/redis.  An explicit
    # --config gateway file may carry a stale ported account_id (legacy
    # residue) and must never shadow it, otherwise the read-only RPC request
    # goes to a queue no bridge listens on and every ping times out.
    if arguments.config is None:
        profile = "simulation"
        config = load_gateway(ROOT, profile)
    else:
        config_path = Path(arguments.config)
        match = re.search(r"host_gateway\.([A-Za-z0-9_]+)\.json$", config_path.name)
        profile = match.group(1) if match else "simulation"
        raw = json.loads(config_path.read_text(encoding="utf-8"))
        config = apply_gateway_overrides(ROOT, profile, raw)

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
    state_db = Path(str(effective.get("state_db") or ROOT / "runtime_data" / "state" / profile / "qmt_runtime.sqlite3"))
    audit_dir = Path(str(effective.get("audit_dir") or ROOT / "runtime_data" / "audit" / profile))
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
