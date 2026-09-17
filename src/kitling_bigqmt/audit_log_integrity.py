"""Fail-closed, read-only integrity measurement for Tray JSONL audit logs.

The native Tray appends one JSON object per physical line to
runtime_data/audit/<profile>/native_tray.jsonl.  A record whose detail contains
an unescaped control character, most importantly a newline, is written as
several physical lines; every line-oriented reader then silently skips it.
This module only reads bytes and reports counters, so it is safe to run against
live logs while the Tray is writing to them.

Historical damaged lines are never rewritten.  Callers express a known legacy
baseline through max_bad so that new damage still fails the check.
"""

from __future__ import annotations

import json
from pathlib import Path

PROFILES = ("simulation", "production_readonly")
DEFAULT_MAX_BAD = 0


def audit_log_path(root: Path, profile: str) -> Path:
    """Return the audit log path for one Tray profile."""

    return Path(root) / "runtime_data" / "audit" / profile / "native_tray.jsonl"


def scan_audit_log(path: Path, sample_limit: int = 3) -> dict:
    """Count parseable and malformed records in one JSONL audit log.

    A missing file is reported as exists=False instead of raising, so the check
    stays usable on a host where a profile has never run.
    """

    path = Path(path)
    result = {
        "path": str(path),
        "exists": path.is_file(),
        "total_records": 0,
        "ok": 0,
        "bad": 0,
        "bad_line_numbers": [],
        "samples": [],
        "last_event": None,
        "last_event_time": None,
    }
    if not result["exists"]:
        return result

    limit = max(1, sample_limit)
    for number, raw in enumerate(path.read_bytes().split(b"\n"), start=1):
        if not raw.strip():
            continue
        result["total_records"] += 1
        try:
            record = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            result["bad"] += 1
            result["bad_line_numbers"].append(number)
            if len(result["samples"]) < limit:
                result["samples"].append(
                    {
                        "line": number,
                        "length": len(raw),
                        "preview": raw[:100].decode("utf-8", "replace"),
                    }
                )
            continue
        result["ok"] += 1
        if isinstance(record, dict):
            result["last_event"] = record.get("event")
            result["last_event_time"] = record.get("event_time") or record.get("ts")

    result["bad_line_numbers"] = result["bad_line_numbers"][-50:]
    return result


def check_profiles(root: Path, profiles: tuple = PROFILES, max_bad: int = DEFAULT_MAX_BAD) -> dict:
    """Scan each profile and return an overall fail-closed verdict."""

    reports = {profile: scan_audit_log(audit_log_path(root, profile)) for profile in profiles}
    overall = "PASSED"
    for report in reports.values():
        if not report["exists"]:
            report["verdict"] = "MISSING"
            continue
        clean = report["bad"] <= max_bad
        report["verdict"] = "PASSED" if clean else "FAILED"
        if not clean:
            overall = "FAILED"
    return {"overall": overall, "max_bad": max_bad, "profiles": reports}

