import importlib.util
import json
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "parse_ptrade_score_matrix.py"
SPEC = importlib.util.spec_from_file_location("parse_ptrade_score_matrix", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def _row(day: str, security: str) -> dict:
    return {
        "day": day,
        "security": security,
        "history_count": 25,
        "last_close_adjusted": 1.0,
        "momentum_score": 1.0,
        "momentum_eligible": True,
        "sma4_value": 1.0,
        "sma4_pass": True,
        "frozen_sessions_before": 0,
        "excluded_reason": None,
        "strategy_version": "v1.1.15",
        "source_run_id": "test",
        "config_hash": None,
    }


def test_parse_utf16_score_matrix(tmp_path: Path):
    rows = [_row("20260617", "159667.SZ")]
    line = "2026-06-17 INFO S10 SCORE_MATRIX day=20260617 current=None min_hold_days=5 shadow=False records=" + json.dumps(rows)
    source = tmp_path / "ptrade.txt"
    source.write_bytes(("\ufeff" + line).encode("utf-16"))
    report = MODULE.parse_score_matrix(source, expected_count=1)
    assert report["status"] == "READY"
    assert report["valid_day_count"] == 1
    assert report["days"][0]["records"][0]["security"] == "159667.SZ"


def test_incomplete_matrix_is_not_ready(tmp_path: Path):
    row = _row("20260617", "159667.SZ")
    source = tmp_path / "ptrade.txt"
    source.write_text("SCORE_MATRIX day=20260617 records=" + json.dumps([row]), encoding="utf-8")
    report = MODULE.parse_score_matrix(source, expected_count=25)
    assert report["status"] == "INCOMPLETE"
    assert report["invalid_day_count"] == 1
