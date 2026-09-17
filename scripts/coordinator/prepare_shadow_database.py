"""Create a lease-invalidated shadow copy by SQLite online backup."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from kitling_bigqmt.coordinator_backup import prepare_shadow_database  # noqa: E402


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(prepare_shadow_database(args.source, args.destination), ensure_ascii=False))
