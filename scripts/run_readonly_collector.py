"""Run a bounded continuous read-only simulation collection test."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kitling_bigqmt.collector import collect_cycles
from kitling_bigqmt.redis_resp import RedisRespClient
from kitling_bigqmt.readonly_rpc import ReadOnlyBigQmtClient
from kitling_bigqmt.state_store import RuntimeStateStore
from kitling_bigqmt.machine_config import load_gateway


def main() -> int:
    parser = argparse.ArgumentParser(description="Bounded read-only BigQMT simulation collector.")
    parser.add_argument("--config", default=None)
    parser.add_argument("--cycles", type=int, default=3)
    parser.add_argument("--interval-seconds", type=float, default=3.0)
    arguments = parser.parse_args()
    config = load_gateway(ROOT, "simulation") if arguments.config is None else json.loads(Path(arguments.config).read_text(encoding="utf-8"))
    client = ReadOnlyBigQmtClient(
        redis=RedisRespClient(**dict(config["redis"])),
        account_id=str(config["account_id"]),
        timeout_seconds=float(config.get("rpc_timeout_seconds", 12)),
    )
    store = RuntimeStateStore(Path(config["state_db"]), Path(config["audit_dir"]))
    results = collect_cycles(
        client, store, str(config["environment"]),
        list(config.get("quote_codes") or []), arguments.cycles, arguments.interval_seconds,
    )
    print(json.dumps({
        "status": "PASSED",
        "orders_enabled": False,
        "cycles": [result.__dict__ for result in results],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
