"""Verify one Coordinator SQLite database without modifying it."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from kitling_bigqmt.coordinator_backup import verify_database  # noqa: E402


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(verify_database(args.database), ensure_ascii=False))
