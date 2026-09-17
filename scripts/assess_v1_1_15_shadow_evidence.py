"""Assess v1.1.15 shadow evidence without QMT, Redis, or order calls."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from kitling_bigqmt.shadow_evidence import assess_shadow_events  # noqa: E402
from kitling_bigqmt.state_store import RuntimeStateStore  # noqa: E402
from kitling_bigqmt.machine_config import load_gateway  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--required-days", type=int, default=1,
                        help="informational continuity threshold; not an execution gate")
    parser.add_argument("--min-bar-count", type=int, default=25)
    parser.add_argument("--config", type=Path, default=None)
    args = parser.parse_args()
    config = load_gateway(ROOT, "simulation") if args.config is None else json.loads(args.config.read_text(encoding="utf-8"))
    if config.get("environment") != "simulation":
        raise SystemExit("shadow evidence assessment is simulation-only")
    store = RuntimeStateStore(Path(config["state_db"]), Path(config["audit_dir"]))
    events = store.latest_strategy_shadow_events(limit=200)
    print(json.dumps(assess_shadow_events(events, args.required_days, args.min_bar_count), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
