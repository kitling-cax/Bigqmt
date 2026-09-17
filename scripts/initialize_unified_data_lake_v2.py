"""Create the safe catalog skeleton for the unified ETF/A-share lake v2.

This command is deliberately separate from data ingestion.  It cannot access
QMT, Redis, orders or the legacy catalog, and it never publishes a global
PIT/Silver release.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from kitling_bigqmt.unified_lake_v2 import initialize  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Initialize source-preserving unified lake v2")
    parser.add_argument("--lake-root", type=Path, default=Path(r"C:\BigQMT\research\quant_data_lake"))
    parser.add_argument("--contract", type=Path, default=ROOT / "config" / "unified_data_lake_v2_contract.json")
    parser.add_argument("--approve-create-v2", action="store_true")
    args = parser.parse_args()
    if not args.approve_create_v2:
        print(json.dumps({
            "status": "READY_FOR_EXPLICIT_V2_FOUNDATION_CREATE",
            "target": str((args.lake_root.resolve() / "v2")),
            "safety": {"global_latest_updated": False, "legacy_catalog_latest_modified": False,
                       "orders_enabled": False, "broker_calls": False},
        }, ensure_ascii=False, indent=2))
        return 0
    result = initialize(args.lake_root, args.contract)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
