"""Classify remaining v1.1.15 QMT/PTrade daily-rank differences.

This is an audit-only tool.  It does not change signal rules, state, or order
configuration.  A QMT candidate can differ from the PTrade logged ``best``
because PTrade excluded that candidate during an explicit freeze session, or
because the two engines have different adjusted-history/eligibility values.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PARITY = ROOT / "runtime_data" / "evidence" / "simulation" / (
    "qmt_v1_1_15_daily_score_parity_20260908_135401.json"
)
DEFAULT_LOG = (ROOT / ".." / ".." / "kitling_ChatGPT_work" / "PTtrade策略编辑器"
               / "ptrade策略项目" / "S10-D1_低频动量轮动_RC1-RC2" / "5日回测"
               / "持有5天v1.1.15_长期" / "持有5天v1.1.15_长期.txt").resolve()

MAIN_ID = "S10_D1_U25_NO_ALCOHOL_5D_SIM_MAIN_V1_1_15"
DAY_RE = re.compile(
    r"^(\d{4}-\d\d-\d\d) .*? - INFO - (?:LIVE )?" + re.escape(MAIN_ID) +
    r" (?:(?:signal: (.*?) -> (.*?), reason=(.*?), best=(.*?))|"
    r"(?:hold (.*?); (.*?); best=(.*?))) score=(.*)$"
)
FREEZE_RE = re.compile(
    r"^(\d{4}-\d\d-\d\d) .*? - INFO - " + re.escape(MAIN_ID) +
    r" freeze (.*?) after (.*?), cooldown=(\d+) sessions\."
)


def read_log(path: Path) -> tuple[list[dict], dict[str, list[dict]]]:
    raw = path.read_bytes()
    text = (raw.decode("utf-16", errors="replace") if raw.startswith((b"\xff\xfe", b"\xfe\xff"))
            else raw.decode("gbk", errors="replace"))
    days = []
    freezes: dict[str, list[dict]] = {}
    for line in text.splitlines():
        line = line.strip()
        match = DAY_RE.search(line)
        if match:
            if match.group(2) is not None:
                current, reason, best = match.group(2), match.group(4), match.group(5)
            else:
                current, reason, best = match.group(6), match.group(7), match.group(8)
            days.append({
                "day": match.group(1).replace("-", ""),
                "current": current,
                "reason": reason,
                "best": None if best == "None" else best,
            })
            continue
        match = FREEZE_RE.search(line)
        if match:
            day = match.group(1).replace("-", "")
            freezes.setdefault(day, []).append({
                "security": match.group(2),
                "reason": match.group(3),
                "cooldown": int(match.group(4)),
            })
    return days, freezes


def classify(parity: dict, log_days: list[dict], freeze_events: dict[str, list[dict]]) -> dict:
    comparisons = {item["day"]: item for item in parity.get("comparisons", [])}
    frozen: dict[str, int] = {}
    differences = []
    for row in log_days:
        for security in list(frozen):
            frozen[security] -= 1
            if frozen[security] <= 0:
                del frozen[security]

        item = comparisons.get(row["day"])
        if not item or item.get("ptrade_best") is None:
            # Blank/risk-only PTrade rows are intentionally outside this gate.
            for event in freeze_events.get(row["day"], []):
                frozen[event["security"]] = event["cooldown"] + 1
            continue

        code_mismatch = not item.get("best_code_match", False)
        score_mismatch = not item.get("ptrade_best_score_match", False)
        if code_mismatch or score_mismatch:
            qmt_best = item.get("qmt_best")
            if code_mismatch and qmt_best in frozen:
                category = "PTRADE_FREEZE_EXCLUSION"
                frozen_sessions_remaining = frozen[qmt_best]
            elif code_mismatch:
                category = "DATA_OR_ELIGIBILITY_DIFFERENCE"
                frozen_sessions_remaining = None
            else:
                category = "SCORE_VALUE_DIFFERENCE"
                frozen_sessions_remaining = None
            differences.append({
                "day": row["day"],
                "category": category,
                "ptrade_best": item.get("ptrade_best"),
                "ptrade_score": item.get("ptrade_score"),
                "qmt_best": qmt_best,
                "qmt_best_score": item.get("qmt_best_score"),
                "qmt_ptrade_best_score": item.get("qmt_ptrade_best_score"),
                "reason": item.get("reason"),
                "qmt_best_frozen_sessions_remaining": frozen_sessions_remaining,
            })

        # PTrade writes the freeze event on the same completed day.  It becomes
        # effective for the next ranking session after _advance_freezes logic.
        for event in freeze_events.get(row["day"], []):
            frozen[event["security"]] = event["cooldown"] + 1

    counts = {}
    for item in differences:
        counts[item["category"]] = counts.get(item["category"], 0) + 1
    return {
        "schema_version": 1,
        "kind": "qmt_v1_1_15_rank_difference_diagnosis",
        "created_at": datetime.now().astimezone().isoformat(),
        "orders_enabled": False,
        "parity_file": str(DEFAULT_PARITY),
        "ptrade_day_count": len(log_days),
        "difference_count": len(differences),
        "category_counts": counts,
        "interpretation": {
            "PTRADE_FREEZE_EXCLUSION": "QMT raw rank is higher, but PTrade explicitly excluded that security during freeze sessions.",
            "DATA_OR_ELIGIBILITY_DIFFERENCE": "No matching PTrade freeze was found; compare dypre adjustment, available history, and eligibility fields.",
            "SCORE_VALUE_DIFFERENCE": "Same best code, but score differs beyond the parity tolerance; compare adjusted close values and rounding.",
        },
        "differences": differences,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--parity-file", type=Path, default=DEFAULT_PARITY)
    parser.add_argument("--ptrade-log", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    parity = json.loads(args.parity_file.read_text(encoding="utf-8"))
    days, freezes = read_log(args.ptrade_log)
    artifact = classify(parity, days, freezes)
    output = args.output
    if output is None:
        output = ROOT / "runtime_data" / "evidence" / "simulation" / (
            "qmt_v1_1_15_rank_difference_diagnosis_%s.json" %
            datetime.now().strftime("%Y%m%d_%H%M%S")
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "output": str(output),
        "difference_count": artifact["difference_count"],
        "category_counts": artifact["category_counts"],
        "orders_enabled": False,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
