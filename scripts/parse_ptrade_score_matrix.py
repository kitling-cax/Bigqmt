"""Parse the diagnostic SCORE_MATRIX records emitted by the v1.1.15 copy.

This is deliberately a host-side, read-only tool.  It never imports the PTrade
runtime and never changes a strategy, account, or order state.  The diagnostic
copy logs one JSON array per signal-calculation day; this parser validates that
the array is complete before it is used in parity analysis.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path


MARKER = "SCORE_MATRIX "
REQUIRED_FIELDS = {
    "day",
    "security",
    "history_count",
    "last_close_adjusted",
    "momentum_score",
    "momentum_eligible",
    "sma4_value",
    "sma4_pass",
    "frozen_sessions_before",
    "excluded_reason",
    "strategy_version",
    "source_run_id",
    "config_hash",
}
DAY_RE = re.compile(r"\bday=(\d{8})\b")


def decode_log(path: Path) -> str:
    raw = path.read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16", errors="replace")
    for encoding in ("utf-8", "gb18030", "gbk"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _records_from_line(line: str) -> tuple[str | None, list[dict] | None, str | None]:
    marker_at = line.find(MARKER)
    if marker_at < 0:
        return None, None, None
    payload = line[marker_at + len(MARKER):]
    records_at = payload.find(" records=")
    if records_at < 0:
        return None, None, "missing records field"
    prefix = payload[:records_at]
    match = DAY_RE.search(prefix)
    if not match:
        return None, None, "missing or invalid day field"
    raw_records = payload[records_at + len(" records="):].strip()
    try:
        records = json.loads(raw_records)
    except json.JSONDecodeError as exc:
        return match.group(1), None, "invalid records JSON: %s" % exc
    if not isinstance(records, list):
        return match.group(1), None, "records is not a JSON array"
    return match.group(1), records, None


def validate_matrix(day: str, records: list[dict], expected_count: int) -> list[str]:
    errors: list[str] = []
    if len(records) != expected_count:
        errors.append("%s has %d records; expected %d" % (day, len(records), expected_count))
    securities: set[str] = set()
    for index, item in enumerate(records):
        if not isinstance(item, dict):
            errors.append("%s[%d] is not an object" % (day, index))
            continue
        missing = sorted(REQUIRED_FIELDS - set(item))
        if missing:
            errors.append("%s[%d] missing %s" % (day, index, ",".join(missing)))
        security = item.get("security")
        if security in securities:
            errors.append("%s duplicate security %s" % (day, security))
        if isinstance(security, str):
            securities.add(security)
        if item.get("day") != day:
            errors.append("%s[%d] embedded day=%r" % (day, index, item.get("day")))
        if not isinstance(item.get("history_count"), int):
            errors.append("%s[%d] history_count is not int" % (day, index))
    return errors


def parse_score_matrix(path: Path, expected_count: int = 25) -> dict:
    days: list[dict] = []
    parse_errors: list[dict] = []
    for line_number, line in enumerate(decode_log(path).splitlines(), start=1):
        if MARKER not in line:
            continue
        day, records, error = _records_from_line(line.strip())
        if error:
            parse_errors.append({"line": line_number, "day": day, "error": error})
            continue
        assert day is not None and records is not None
        validation_errors = validate_matrix(day, records, expected_count)
        days.append({
            "day": day,
            "line": line_number,
            "record_count": len(records),
            "validation_errors": validation_errors,
            "records": records,
        })
    valid_days = [item for item in days if not item["validation_errors"]]
    return {
        "schema_version": 1,
        "kind": "ptrade_v1_1_15_score_matrix_diagnostic",
        "created_at": datetime.now().astimezone().isoformat(),
        "source_log": str(path),
        "orders_enabled": False,
        "expected_record_count": expected_count,
        "score_matrix_line_count": len(days) + len(parse_errors),
        "valid_day_count": len(valid_days),
        "invalid_day_count": len(days) - len(valid_days),
        "parse_errors": parse_errors,
        "days": days,
        "status": "READY" if days and not parse_errors and len(valid_days) == len(days) else "INCOMPLETE",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--expected-count", type=int, default=25)
    args = parser.parse_args()
    report = parse_score_matrix(args.log, args.expected_count)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: report[key] for key in (
        "status", "source_log", "score_matrix_line_count", "valid_day_count",
        "invalid_day_count", "parse_errors", "orders_enabled",
    )}, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "READY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
