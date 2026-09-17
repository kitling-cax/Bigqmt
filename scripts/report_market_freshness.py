"""Report recent QMT full-tick freshness from the SQLite authority store."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kitling_bigqmt.state_store import RuntimeStateStore
from kitling_bigqmt.machine_config import load_gateway


def main() -> int:
    parser = argparse.ArgumentParser(description="Report persisted QMT quote freshness.")
    parser.add_argument("--config", default=None)
    parser.add_argument("--latest-runs", type=int, default=3)
    arguments = parser.parse_args()
    config = load_gateway(ROOT, "simulation") if arguments.config is None else json.loads(Path(arguments.config).read_text(encoding="utf-8"))
    store = RuntimeStateStore(Path(config["state_db"]), Path(config["audit_dir"]))
    summary = store.quote_freshness_summary(arguments.latest_runs)
    summary["status"] = "PASSED" if summary["samples"] and not summary["states"]["STALE"] and not summary["states"]["UNKNOWN"] else "ATTENTION"
    summary["orders_enabled"] = False
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
