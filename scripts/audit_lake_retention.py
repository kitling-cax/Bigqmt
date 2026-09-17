"""Audit the local Parquet lake retention state without deleting anything.

The report is deliberately read-only.  It inventories immutable export runs,
checks their manifests, estimates bytes, and marks runs older than the
configured retention window as candidates for a separately approved cleanup.
No QMT/Redis call and no filesystem deletion is performed.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _size(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def audit_lake(root: Path, retention_days: int = 365, now: datetime | None = None) -> dict:
    if retention_days < 1:
        raise ValueError("retention_days must be positive")
    now = now or datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=retention_days)).date()
    runs: list[dict] = []
    missing_manifests: list[str] = []
    if root.exists():
        for manifest_path in sorted(root.glob("*/*/*/manifest.json")):
            run_dir = manifest_path.parent
            parts = run_dir.relative_to(root).parts
            if len(parts) != 3:
                continue
            environment, trading_date, source_run_id = parts
            try:
                date_value = datetime.strptime(trading_date, "%Y-%m-%d").date()
            except ValueError:
                date_value = None
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            runs.append({
                "environment": environment,
                "trading_date": trading_date,
                "source_run_id": source_run_id,
                "status": manifest.get("status", "UNKNOWN"),
                "orders_enabled": bool(manifest.get("orders_enabled", True)),
                "bytes": _size(run_dir),
                "retention_candidate": bool(date_value and date_value < cutoff),
            })
        for run_dir in sorted(root.glob("*/*/*")):
            if run_dir.is_dir() and not (run_dir / "manifest.json").exists():
                missing_manifests.append(str(run_dir))
    return {
        "schema_version": 1,
        "status": "PASSED",
        "read_only": True,
        "root": str(root),
        "retention_days": retention_days,
        "cutoff_date": cutoff.isoformat(),
        "run_count": len(runs),
        "candidate_count": sum(1 for run in runs if run["retention_candidate"]),
        "missing_manifest_count": len(missing_manifests),
        "total_bytes": sum(run["bytes"] for run in runs),
        "runs": runs,
        "missing_manifests": missing_manifests,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only audit of Parquet lake retention")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1] / "runtime_data" / "lake")
    parser.add_argument("--retention-days", type=int, default=365)
    args = parser.parse_args()
    print(json.dumps(audit_lake(args.root, args.retention_days), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
