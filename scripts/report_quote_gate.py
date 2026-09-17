"""Print the latest per-symbol QMT quote admission gate."""

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
    parser = argparse.ArgumentParser(description="Show safe and blocked QMT quote symbols.")
    parser.add_argument("--config", default=None)
    parser.add_argument("--max-age-seconds", type=float, default=180.0)
    arguments = parser.parse_args()
    config = load_gateway(ROOT, "simulation") if arguments.config is None else json.loads(Path(arguments.config).read_text(encoding="utf-8"))
    store = RuntimeStateStore(Path(config["state_db"]), Path(config["audit_dir"]))
    result = store.latest_quote_gate(arguments.max_age_seconds)
    result["orders_enabled"] = False
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
