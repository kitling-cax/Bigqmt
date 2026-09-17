"""Generate a read-only BigQMT Tray diagnostic report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from kitling_bigqmt.tray_diagnostics import diagnose_tray  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only BigQMT Tray diagnostics")
    parser.add_argument("--profile", choices=("simulation", "production_readonly"), default="simulation")
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args()
    print(json.dumps(diagnose_tray(ROOT, args.profile, dashboard_port=args.port), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
