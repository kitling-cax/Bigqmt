"""Read a local account's Coordinator lease preview; never requests a lease."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from kitling_bigqmt.coordinator_endpoint import resolve_coordinator  # noqa: E402
from kitling_bigqmt.coordinator_lease_projection import project_local_lease  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=("simulation", "production_readonly"), required=True)
    parser.add_argument("--timeout", type=float, default=3.0)
    args = parser.parse_args()
    endpoint, host_id = resolve_coordinator(ROOT)
    try:
        with urlopen(endpoint.rstrip("/") + "/api/v1/executor-preview", timeout=max(0.1, args.timeout)) as response:
            preview = json.loads(response.read().decode("utf-8"))
        projected = project_local_lease(preview, args.profile, host_id)
        projected["status"] = "PASS"
    except Exception as exc:
        projected = {"profile": args.profile, "status": "DEGRADED", "reason": type(exc).__name__,
                     "orders_enabled": False}
    print(json.dumps(projected, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
