"""Print the local read-only operations alert projection."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kitling_bigqmt.dashboard_status import build_dashboard_status  # noqa: E402


def main() -> int:
    status = build_dashboard_status(ROOT)
    result = status.get("ops_alerts") or {"alerts": [], "alert_count": 0, "highest_severity": "INFO", "read_only": True}
    result["orders_enabled"] = False
    result["broker_call_made"] = False
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
