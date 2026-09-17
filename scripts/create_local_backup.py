"""Create one immutable local BigQMT backup; no restore or deletion action."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from kitling_bigqmt.local_backup import create_local_backup  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=("simulation", "production_readonly"), required=True)
    parser.add_argument("--audit-days", type=int, default=14)
    parser.add_argument("--project-root", type=Path, default=ROOT)
    args = parser.parse_args()
    result = create_local_backup(args.project_root, args.profile, args.audit_days)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASSED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
