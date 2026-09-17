"""Run one bounded, read-only SQLite-WAL -> Parquet -> retention cycle.

This is intentionally a local operator action for BigQMT Tray.  It never
contacts QMT/Redis, never creates an order, and stops with BLOCKED when no
persisted snapshot exists for the selected profile.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from audit_lake_retention import audit_lake

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from kitling_bigqmt.machine_config import load_gateway, apply_data_lake_root  # noqa: E402


def _finish(result: dict, profile: str) -> int:
    evidence_dir = ROOT / "runtime_data" / "evidence" / profile / "lake_cycles"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    evidence_path = evidence_dir / f"lake_cycle_{stamp}.json"
    result["evidence_path"] = str(evidence_path)
    evidence_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") == "PASSED" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a read-only BigQMT data-lake cycle")
    parser.add_argument("--profile", choices=("simulation", "production_readonly"), default="simulation")
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--retention-days", type=int, default=365)
    args = parser.parse_args()
    config_obj = load_gateway(ROOT, args.profile)
    output_root = Path(apply_data_lake_root(ROOT, ""))
    export = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "export_readonly_snapshot_to_lake.py"),
         "--profile", args.profile, "--output-root", str(output_root)],
        capture_output=True, text=True, check=False,
    )
    result = {
        "schema_version": 1,
        "profile": args.profile,
        "environment": config_obj.get("environment"),
        "read_only": True,
        "orders_enabled": False,
        "broker_call_made": False,
        "export_returncode": export.returncode,
    }
    if export.stdout.strip():
        try:
            result["export"] = json.loads(export.stdout)
        except json.JSONDecodeError:
            result["export_stdout"] = export.stdout[-2000:]
    if export.stderr.strip():
        result["export_stderr"] = export.stderr[-2000:]
    if export.returncode != 0:
        result["status"] = "BLOCKED"
        return _finish(result, args.profile)
    result["retention_audit"] = audit_lake(output_root, args.retention_days)
    result["status"] = "PASSED"
    return _finish(result, args.profile)


if __name__ == "__main__":
    raise SystemExit(main())
