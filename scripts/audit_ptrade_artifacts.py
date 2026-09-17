"""Audit the PTrade artifacts that are actually available in a backtest folder.

The PTrade UI does not need to export a special file for this audit.  The
existing UTF-16 log, trade-detail CSV, and holdings CSV are treated as evidence
and checked for encoding, coverage, and end-of-run position consistency.
"""

from __future__ import annotations

import argparse
import bisect
import csv
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from replay_v1_1_15_ptrade_state import load_log, load_trades, replay  # noqa: E402


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_holdings(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="gbk", errors="replace", newline="") as handle:
        for row in csv.reader(handle):
            if not row or row[0] == "日期" or len(row) < 8:
                continue
            try:
                quantity = int(float(row[4].replace(",", "")))
            except (ValueError, TypeError):
                continue
            rows.append({"day": row[0].replace("-", ""), "time": row[1],
                         "code": row[2].strip(), "quantity": quantity,
                         "entry_cost": float(row[6].replace(",", "") or 0)})
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    files = {
        "log": next(args.directory.glob("*.txt")),
        "trades": next(args.directory.glob("交易详情*.csv")),
        "holdings": next(args.directory.glob("持仓明细*.csv")),
    }
    log_rows = load_log(files["log"])
    trades = load_trades(files["trades"])
    daily, events = replay(trades)
    holdings = load_holdings(files["holdings"])
    last_holdings_day = max((row["day"] for row in holdings), default=None)
    replay_days = sorted(daily)
    replay_reference_day = None
    if last_holdings_day and replay_days:
        index = bisect.bisect_right(replay_days, last_holdings_day) - 1
        if index >= 0:
            replay_reference_day = replay_days[index]
    expected = daily.get(replay_reference_day, {}) if replay_reference_day else {}
    actual = {row["code"]: row["quantity"] for row in holdings
              if row["day"] == last_holdings_day and row["quantity"] > 0}
    position_mismatches = []
    for code in sorted(set(expected) | set(actual)):
        expected_qty = int(expected.get(code, {}).get("quantity", 0))
        actual_qty = int(actual.get(code, 0))
        if expected_qty != actual_qty:
            position_mismatches.append({"code": code, "replayed": expected_qty, "holdings_csv": actual_qty})
    artifact = {
        "schema_version": 1,
        "kind": "ptrade_v1_1_15_artifact_only_audit",
        "created_at": datetime.now().astimezone().isoformat(),
        "directory": str(args.directory),
        "orders_enabled": False,
        "files": {name: {"path": str(path), "bytes": path.stat().st_size, "sha256": sha256(path)}
                  for name, path in files.items()},
        "log_rows": len(log_rows),
        "trade_rows": len(trades),
        "holding_rows": len(holdings),
        "trade_days": [min((row["day"] for row in trades), default=None), max((row["day"] for row in trades), default=None)],
        "log_days": [min((row["day"] for row in log_rows), default=None), max((row["day"] for row in log_rows), default=None)],
        "last_holdings_day": last_holdings_day,
        "replay_reference_day": replay_reference_day,
        "replayed_event_count": len(events),
        "last_day_position_mismatch_count": len(position_mismatches),
        "last_day_position_mismatches": position_mismatches,
        "score_matrix_present": False,
        "status": "PASSED" if not position_mismatches and log_rows and trades and holdings else "ATTENTION",
    }
    output = ROOT / "runtime_data" / "evidence" / "simulation" / (
        "ptrade_v1_1_15_artifact_audit_%s.json" % datetime.now().strftime("%Y%m%d_%H%M%S"))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), "status": artifact["status"],
                      "log_rows": len(log_rows), "trade_rows": len(trades),
                      "holding_rows": len(holdings), "last_holdings_day": last_holdings_day,
                      "replay_reference_day": replay_reference_day,
                      "last_day_position_mismatch_count": len(position_mismatches),
                      "score_matrix_present": False, "orders_enabled": False}, ensure_ascii=False, indent=2))
    return 0 if artifact["status"] == "PASSED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
