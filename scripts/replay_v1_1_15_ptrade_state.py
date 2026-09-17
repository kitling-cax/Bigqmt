"""Reconstruct the frozen PTrade v1.1.15 sleeve state from its evidence.

This is a host-only audit tool.  It reads the PTrade trade CSV and UTF-16 log,
replays fills in timestamp order, and produces end-of-day strategy-owned
positions/weighted entry costs.  It does not contact QMT or submit orders.
"""

from __future__ import annotations

import argparse
import bisect
import csv
import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIR = (ROOT / ".." / ".." / "kitling_ChatGPT_work" / "PTtrade策略编辑器"
               / "ptrade策略项目" / "S10-D1_低频动量轮动_RC1-RC2" / "5日回测"
               / "持有5天v1.1.15_长期").resolve()
LOG_RE = re.compile(
    r"^(\d{4}-\d\d-\d\d) .*? - INFO - (?:LIVE )?S10_D1_U25_NO_ALCOHOL_5D_SIM_MAIN_V1_1_15 "
    r"(?:(?:signal: (.*?) -> (.*?), reason=(.*?), best=(.*?))|"
    r"(?:hold (.*?); (.*?); best=(.*?))) score=(.*)$"
)


def _number(value: str) -> float:
    try:
        return float(value.replace(",", ""))
    except (AttributeError, TypeError, ValueError):
        return 0.0


def load_trades(path: Path) -> list[dict]:
    rows = []
    with path.open("r", encoding="gbk", errors="replace", newline="") as handle:
        for row in csv.reader(handle):
            if not row or row[0] == "日期" or len(row) < 8:
                continue
            side = row[3].strip()
            if side not in ("买", "卖"):
                continue
            rows.append({
                "day": row[0].replace("-", ""), "time": row[1], "code": row[2].strip(),
                "side": side, "quantity": int(_number(row[5])), "price": _number(row[6]),
                "fee": _number(row[7]),
            })
    rows.sort(key=lambda item: (item["day"], item["time"]))
    return rows


def load_log(path: Path) -> list[dict]:
    raw = path.read_bytes()
    text = raw.decode("utf-16", errors="replace") if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else raw.decode("gbk", errors="replace")
    rows = []
    for line in text.splitlines():
        match = LOG_RE.search(line.strip())
        if not match:
            continue
        if match.group(2) is not None:
            current, desired, reason, best, score = match.group(2), match.group(3), match.group(4), match.group(5), match.group(8)
            event = "signal"
        else:
            current, desired, reason, best, score = match.group(6), match.group(6), match.group(7), match.group(8), match.group(9)
            event = "hold"
        rows.append({"day": match.group(1).replace("-", ""), "event": event,
                     "current": None if current == "None" else current,
                     "desired": desired, "reason": reason,
                     "best": None if best == "None" else best,
                     "score": None if score in (None, "None") else float(score)})
    return rows


def replay(trades: list[dict]) -> tuple[dict[str, dict], list[dict]]:
    positions: dict[str, dict] = {}
    daily: dict[str, dict] = {}
    events = []
    by_day: dict[str, list[dict]] = defaultdict(list)
    for trade in trades:
        by_day[trade["day"]].append(trade)
    for day in sorted(by_day):
        before = set(positions)
        for trade in by_day[day]:
            code, quantity, price, fee = trade["code"], trade["quantity"], trade["price"], trade["fee"]
            item = positions.setdefault(code, {"quantity": 0, "cost": 0.0})
            if trade["side"] == "买":
                item["quantity"] += quantity
                item["cost"] += quantity * price + fee
            else:
                old_quantity = item["quantity"]
                avg = item["cost"] / old_quantity if old_quantity else 0.0
                item["quantity"] = max(0, old_quantity - quantity)
                item["cost"] = max(0.0, item["cost"] - avg * quantity)
            if item["quantity"] <= 0:
                positions.pop(code, None)
        active = {
            code: {"quantity": item["quantity"], "avg_entry_cost": item["cost"] / item["quantity"]}
            for code, item in positions.items() if item["quantity"] > 0
        }
        daily[day] = active
        after = set(active)
        for code in sorted(after - before):
            events.append({"day": day, "event": "ENTRY_OR_REENTRY", "code": code,
                           "quantity": active[code]["quantity"], "avg_entry_cost": active[code]["avg_entry_cost"]})
        for code in sorted(before - after):
            events.append({"day": day, "event": "EXIT", "code": code})
    return daily, events


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, default=DEFAULT_DIR)
    args = parser.parse_args()
    trade_path = next(args.directory.glob("交易详情*.csv"))
    log_path = next(args.directory.glob("*.txt"))
    trades = load_trades(trade_path)
    log_rows = load_log(log_path)
    daily, events = replay(trades)

    exact = 0
    active_contains = 0
    mismatches = []
    trade_days = sorted(daily)
    for row in log_rows:
        index = bisect.bisect_right(trade_days, row["day"]) - 1
        active = daily[trade_days[index]] if index >= 0 else {}
        codes = sorted(active)
        current = row["current"]
        exact_match = (current is None and not codes) or (len(codes) == 1 and codes[0] == current)
        contains_match = current is None and not codes or current in active
        exact += exact_match
        active_contains += contains_match
        if not contains_match and len(mismatches) < 25:
            mismatches.append({"day": row["day"], "log_current": current, "active_positions": active,
                               "event": row["event"], "reason": row["reason"]})

    artifact = {
        "schema_version": 1, "kind": "ptrade_v1_1_15_state_replay",
        "created_at": datetime.now().astimezone().isoformat(),
        "trade_csv": str(trade_path), "ptrade_log": str(log_path),
        "trade_count": len(trades), "log_day_count": len(log_rows),
        "daily_position_days": len(daily), "entry_exit_event_count": len(events),
        "log_current_exact_matches": exact, "log_current_active_contains": active_contains,
        "log_current_mismatch_count": len(log_rows) - active_contains,
        "mismatches_kept": mismatches,
        "entry_exit_events": events,
        "daily_positions": daily,
        "orders_enabled": False,
    }
    out = ROOT / "runtime_data" / "evidence" / "simulation" / (
        "ptrade_v1_1_15_state_replay_%s.json" % datetime.now().strftime("%Y%m%d_%H%M%S"))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(out), "trade_count": len(trades), "log_day_count": len(log_rows),
                      "entry_exit_event_count": len(events), "log_current_active_contains": active_contains,
                      "log_current_mismatch_count": artifact["log_current_mismatch_count"]},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
