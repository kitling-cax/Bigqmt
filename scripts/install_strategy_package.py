"""Verify and stage one immutable strategy package on a Windows host."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kitling_bigqmt.strategy_installer import install_package


def main() -> int:
    parser = argparse.ArgumentParser(description="Install a verified strategy package locally; never start it")
    parser.add_argument("--package-dir", type=Path, required=True)
    parser.add_argument("--install-root", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = install_package(args.package_dir, args.install_root)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "REJECTED", "reason": str(exc), "orders_enabled": False}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
