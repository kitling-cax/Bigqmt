"""Compare a QMT signal probe with the frozen PTrade v1.1.15 log evidence."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path


DEFAULT_PTRADE_LOG = (
    r"C:\BigQMT\research\PTtrade策略编辑器\ptrade策略项目"
    r"\S10-D1_低频动量轮动_RC1-RC2\5日回测\持有5天v1.1.15_长期\持有5天v1.1.15_长期.txt"
)
SIGNAL_RE = re.compile(
    r"^(\d{4}-\d\d-\d\d) .*? LIVE .*? signal: (.*?) -> (.*?), "
    r"reason=(.*?), best=(.*?)(?: score=(.*))?$"
)


def load_ptrade_signals(path: Path) -> list[dict]:
    raw = path.read_bytes()
    text = raw.decode("utf-16", errors="replace") if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else raw.decode("gbk", errors="replace")
    result = []
    for line in text.splitlines():
        match = SIGNAL_RE.search(line.strip())
        if not match:
            continue
        day, current, desired, reason, best, score = match.groups()
        result.append({
            "day": day.replace("-", ""),
            "current": None if current == "None" else current,
            "desired": desired,
            "reason": reason,
            "best": None if best == "None" else best,
            "score": None if score in (None, "None") else float(score),
        })
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("probe", type=Path)
    parser.add_argument("--ptrade-log", type=Path, default=Path(DEFAULT_PTRADE_LOG))
    args = parser.parse_args()
    probe = json.loads(args.probe.read_text(encoding="utf-8"))
    qmt = [row for row in probe.get("signals", []) if row.get("desired") != row.get("current")]
    gold = load_ptrade_signals(args.ptrade_log)

    tuple_fields = ("day", "current", "desired", "reason", "best")
    exact = 0
    code_matches = 0
    mismatches = []
    for index in range(max(len(qmt), len(gold))):
        q = qmt[index] if index < len(qmt) else None
        p = gold[index] if index < len(gold) else None
        q_tuple = tuple(q.get(field) for field in tuple_fields) if q else None
        p_tuple = tuple(p.get(field) for field in tuple_fields) if p else None
        if q_tuple == p_tuple:
            exact += 1
        else:
            if len(mismatches) < 25:
                mismatches.append({"index": index, "qmt": q, "ptrade": p})
        if q and p and q.get("desired") == p.get("desired"):
            code_matches += 1

    artifact = {
        "schema_version": 1,
        "kind": "qmt_v1_1_15_signal_parity_comparison",
        "created_at": datetime.now().astimezone().isoformat(),
        "qmt_probe": str(args.probe),
        "ptrade_log": str(args.ptrade_log),
        "qmt_adjustment_mode": probe.get("adjustment_mode"),
        "status": "NOT_PASSED" if mismatches else "PASSED",
        "qmt_signal_count": len(qmt),
        "ptrade_signal_count": len(gold),
        "exact_tuple_matches": exact,
        "desired_code_matches_at_same_index": code_matches,
        "mismatches_kept": mismatches,
        "orders_enabled": False,
    }
    output = args.probe.parent / (args.probe.stem + "_vs_ptrade.json")
    output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {key: artifact[key] for key in (
        "status", "qmt_signal_count", "ptrade_signal_count",
        "exact_tuple_matches", "desired_code_matches_at_same_index",
    )}
    summary["output"] = str(output)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if artifact["status"] == "PASSED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
