import json
from pathlib import Path

from kitling_bigqmt import audit_log_integrity


def _write_log(root: Path, profile: str, rows: list) -> Path:
    path = audit_log_integrity.audit_log_path(root, profile)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\n".join(rows) + b"\n")
    return path


def _record(event: str, detail: str) -> bytes:
    return json.dumps(
        {"event_time": "2026-09-16T01:30:00.0000000Z", "event": event, "detail": detail},
        ensure_ascii=False,
    ).encode("utf-8")


def test_missing_log_is_reported_without_raising(tmp_path: Path):
    result = audit_log_integrity.scan_audit_log(audit_log_integrity.audit_log_path(tmp_path, "simulation"))
    assert result["exists"] is False
    assert result["total_records"] == 0
    assert result["bad"] == 0


def test_clean_log_with_escaped_newline_scores_no_bad_lines(tmp_path: Path):
    path = _write_log(tmp_path, "simulation", [_record("qmt_auto_start_login", "line1\nline2\ttab")])
    result = audit_log_integrity.scan_audit_log(path)
    assert result["ok"] == 1
    assert result["bad"] == 0
    assert result["last_event"] == "qmt_auto_start_login"


def test_unescaped_newline_is_detected_as_split_record(tmp_path: Path):
    head = b'{"event_time":"2026-09-16T01:30:00.0000000Z","event":"qmt_start_requested","detail":"{"'
    tail = b'","orders_enabled":false}'
    path = _write_log(tmp_path, "simulation", [head, tail])
    result = audit_log_integrity.scan_audit_log(path)
    assert result["total_records"] == 2
    assert result["bad"] == 2
    assert result["ok"] == 0
    assert len(result["samples"]) == 2
    assert result["samples"][0]["line"] == 1


def test_check_profiles_fails_when_bad_exceeds_baseline(tmp_path: Path):
    _write_log(tmp_path, "simulation", [b'{"event_time":"2026-09-16T01:30:00Z","event":"x"'])
    _write_log(tmp_path, "production_readonly", [_record("status_refreshed", "ok")])
    strict = audit_log_integrity.check_profiles(tmp_path, max_bad=0)
    assert strict["overall"] == "FAILED"
    assert strict["profiles"]["simulation"]["verdict"] == "FAILED"
    assert strict["profiles"]["production_readonly"]["verdict"] == "PASSED"
    tolerant = audit_log_integrity.check_profiles(tmp_path, max_bad=1)
    assert tolerant["overall"] == "PASSED"


def test_check_profiles_marks_missing_profile_and_passes_on_empty_root(tmp_path: Path):
    result = audit_log_integrity.check_profiles(tmp_path, max_bad=0)
    assert result["overall"] == "PASSED"
    assert result["profiles"]["simulation"]["verdict"] == "MISSING"
    assert result["profiles"]["production_readonly"]["verdict"] == "MISSING"

