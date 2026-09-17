"""Perform one read-only host-restart recovery reconciliation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kitling_bigqmt.reconcile import reconcile_after_restart
from kitling_bigqmt.redis_resp import RedisRespClient
from kitling_bigqmt.readonly_rpc import ReadOnlyBigQmtClient
from kitling_bigqmt.state_store import RuntimeStateStore
from kitling_bigqmt.machine_config import load_gateway


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only BigQMT recovery reconciliation.")
    parser.add_argument("--config", default=None)
    arguments = parser.parse_args()
    config = load_gateway(ROOT, "simulation") if arguments.config is None else json.loads(Path(arguments.config).read_text(encoding="utf-8"))
    client = ReadOnlyBigQmtClient(
        redis=RedisRespClient(**dict(config["redis"])), account_id=str(config["account_id"]),
        timeout_seconds=float(config.get("rpc_timeout_seconds", 12)),
    )
    store = RuntimeStateStore(Path(config["state_db"]), Path(config["audit_dir"]))
    result = reconcile_after_restart(
        client, store, str(config["environment"]), list(config.get("quote_codes") or []),
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
