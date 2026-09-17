"""Print a fail-closed, read-only integrity report for Tray JSONL audit logs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from kitling_bigqmt.audit_log_integrity import (  # noqa: E402
    DEFAULT_MAX_BAD,
    PROFILES,
    check_profiles,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=(*PROFILES, "all"), default="all")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument(
        "--max-bad",
        type=int,
        default=DEFAULT_MAX_BAD,
        help="tolerated malformed lines (legacy baseline); default 0",
    )
    args = parser.parse_args()
    profiles = PROFILES if args.profile == "all" else (args.profile,)
    result = check_profiles(Path(args.root), profiles, max_bad=args.max_bad)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["overall"] == "PASSED" else 2


if __name__ == "__main__":
    raise SystemExit(main())

