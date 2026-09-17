import json
from datetime import datetime, timezone
from pathlib import Path

from scripts.audit_lake_retention import audit_lake


def test_lake_retention_audit_is_read_only_and_marks_old_runs(tmp_path: Path):
    old = tmp_path / "simulation" / "2024-01-01" / "run-old"
    old.mkdir(parents=True)
    (old / "account_assets.parquet").write_bytes(b"abc")
    (old / "manifest.json").write_text(json.dumps({"status": "PASSED", "orders_enabled": False}), encoding="utf-8")
    report = audit_lake(tmp_path, retention_days=365, now=datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert report["read_only"] is True
    assert report["run_count"] == 1
    assert report["candidate_count"] == 1
    assert report["runs"][0]["orders_enabled"] is False
    assert old.exists()


def test_lake_retention_audit_reports_missing_manifest(tmp_path: Path):
    run = tmp_path / "simulation" / "2026-01-01" / "run-missing"
    run.mkdir(parents=True)
    report = audit_lake(tmp_path)
    assert report["run_count"] == 0
    assert report["missing_manifest_count"] == 1
