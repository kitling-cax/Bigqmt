"""Print how old the persisted Bridge snapshot is for a Tray profile.

The tray status line shows this age directly, so a stalled hourly snapshot
is visible in the notification menu instead of only being discovered by a
separate health check.

Read-only and fail-closed: no QMT call, no Redis call, no order path.  The
measurement itself is shared with the ``bridge_snapshot`` check in
``kitling_bigqmt.tray_health``; only the presentation is different.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kitling_bigqmt import machine_config  # noqa: E402
from kitling_bigqmt.tray_health import snapshot_freshness  # noqa: E402


def age_text(seconds: float) -> str:
    """Compact Chinese age label for the tray menu line."""
    if seconds < 90:
        return "%.0f 秒前" % seconds
    if seconds < 5400:
        return "%.0f 分钟前" % (seconds / 60.0)
    return "%.1f 小时前" % (seconds / 3600.0)


def main() -> int:
    parser = argparse.ArgumentParser(description="Report persisted Bridge snapshot freshness.")
    parser.add_argument("--profile", choices=("simulation", "production_readonly"), default="simulation")
    args = parser.parse_args()
    try:
        config = machine_config.load_gateway(ROOT, args.profile)
        result = snapshot_freshness(config)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        result = {"status": "FAIL", "detail": "%s: %s" % (type(exc).__name__, exc)}
    payload = {
        "profile": args.profile,
        "status": result["status"],
        "detail": result.get("detail", ""),
        "broker_call_made": False,
        "order_capability": False,
    }
    max_age = result.get("max_age_seconds")
    if isinstance(max_age, (int, float)):
        payload["max_age_seconds"] = max_age
        payload["max_age_text"] = age_text(float(max_age)).replace("前", "")
    age_seconds = result.get("age_seconds")
    if isinstance(age_seconds, (int, float)):
        payload["age_seconds"] = age_seconds
        payload["age_text"] = age_text(float(age_seconds))
        payload["latest_run_id"] = result.get("latest_run_id", "")
        payload["observed_at"] = result.get("observed_at", "")
        payload["fresh"] = bool(result.get("fresh"))
    print(json.dumps(payload, ensure_ascii=False))
    return 0 if result["status"] in {"PASS", "DEGRADED"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
