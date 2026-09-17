"""Print a fail-closed, read-only health snapshot for a Tray profile."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from kitling_bigqmt.tray_health import check_profile  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=("simulation", "production_readonly"), default="simulation")
    parser.add_argument("--port", type=int, default=17890)
    parser.add_argument("--attempts", type=int, default=2)
    args = parser.parse_args()
    result = check_profile(ROOT, args.profile, args.port, attempts=max(1, min(args.attempts, 3)))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["overall"] in {"HEALTHY", "DEGRADED"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
