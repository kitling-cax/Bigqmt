"""Create a verified SQLite online backup; no Coordinator service control."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from kitling_bigqmt.coordinator_backup import create_online_backup  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    print(json.dumps(create_online_backup(args.source, args.destination, overwrite=args.overwrite), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
