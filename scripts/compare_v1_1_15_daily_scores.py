"""Compare QMT daily score/rank output with PTrade v1.1.15 log evidence.

This deliberately ignores target-state transitions.  It answers the narrower
question: for the same completed date, does QMT produce the same eligible
momentum scores and best candidate that PTrade logged?  That separates data
adjustment differences from execution/hold-state differences.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kitling_bigqmt.market_data import normalize_daily_bars  # noqa: E402
from kitling_bigqmt.readonly_rpc import ReadOnlyBigQmtClient  # noqa: E402
from kitling_bigqmt.redis_resp import RedisRespClient  # noqa: E402
from kitling_bigqmt.machine_config import load_gateway  # noqa: E402
from kitling_bigqmt.v1_1_15_reproduction import (  # noqa: E402
    MOMENTUM_MAX,
    MOMENTUM_MIN,
    UNIVERSE_PTRADE,
    legacy_weighted_momentum,
    ptrade_to_qmt,
)

DEFAULT_LOG = (ROOT / ".." / ".." / "kitling_ChatGPT_work" / "PTtrade策略编辑器"
               / "ptrade策略项目" / "S10-D1_低频动量轮动_RC1-RC2" / "5日回测"
               / "持有5天v1.1.15_长期" / "持有5天v1.1.15_长期.txt").resolve()
LINE_RE = re.compile(
    r"^(\d{4}-\d\d-\d\d) .*? - INFO - (?:LIVE )?S10_D1_U25_NO_ALCOHOL_5D_SIM_MAIN_V1_1_15 "
    r"(?:(?:signal: (.*?) -> (.*?), reason=(.*?), best=(.*?))|"
    r"(?:hold (.*?); (.*?); best=(.*?))) score=(.*)$"
)


def load_ptrade_days(path: Path) -> list[dict]:
    raw = path.read_bytes()
    text = raw.decode("utf-16", errors="replace") if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else raw.decode("gbk", errors="replace")
    rows = []
    for line in text.splitlines():
        m = LINE_RE.search(line.strip())
        if not m:
            continue
        day = m.group(1).replace("-", "")
        if m.group(2) is not None:
            current, desired, reason, best, score = m.group(2), m.group(3), m.group(4), m.group(5), m.group(8)
        else:
            current, desired, reason, best, score = m.group(6), m.group(6), m.group(7), m.group(8), m.group(9)
        rows.append({"day": day, "current": current, "reason": reason,
                     "best": None if best == "None" else best,
                     "score": None if score in (None, "None") else float(score)})
    # The two branches log independently; this regex only captures RC1, one
    # row per trading day (signal or hold).
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--adjustment", choices=("front", "back", "none"), default="front")
    parser.add_argument("--history-start", default="20150101")
    parser.add_argument("--end", default=datetime.now().strftime("%Y%m%d"))
    parser.add_argument("--ptrade-log", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--config", default=None)
    args = parser.parse_args()

    rows = load_ptrade_days(args.ptrade_log)
    config = load_gateway(ROOT, "simulation") if args.config is None else json.loads(Path(args.config).read_text(encoding="utf-8"))
    client = ReadOnlyBigQmtClient(RedisRespClient(**dict(config["redis"])), str(config["account_id"]),
                                  timeout_seconds=float(config.get("rpc_timeout_seconds", 12)))
    series: dict[str, dict[str, float]] = {}
    errors = []
    for ptrade_code in UNIVERSE_PTRADE:
        qmt_code = ptrade_to_qmt(ptrade_code)
        try:
            client.download_history_data(qmt_code, "1d", args.history_start, args.end)
            bars = normalize_daily_bars(client.market_data_ex(
                [qmt_code], ["close", "time"], "1d", args.history_start, args.end, -1, args.adjustment), qmt_code)
            series[ptrade_code] = {bar.trade_date: float(bar.close) for bar in bars
                                   if bar.close is not None and bar.close > 0}
        except Exception as exc:
            errors.append({"code": ptrade_code, "type": type(exc).__name__, "message": str(exc)})

    comparisons = []
    for row in rows:
        day = row["day"]
        scores = {}
        for code in UNIVERSE_PTRADE:
            values = [value for date, value in series.get(code, {}).items() if date <= day]
            score = legacy_weighted_momentum(values[-25:])
            if score is not None and MOMENTUM_MIN <= score <= MOMENTUM_MAX:
                scores[code] = score
        qmt_best = max(scores, key=scores.get) if scores else None
        p_best = row["best"]
        qmt_p_score = scores.get(p_best) if p_best else None
        comparisons.append({
            "day": day, "ptrade_best": p_best, "ptrade_score": row["score"],
            "qmt_best": qmt_best, "qmt_best_score": scores.get(qmt_best) if qmt_best else None,
            "qmt_ptrade_best_score": qmt_p_score,
            "best_code_match": qmt_best == p_best if p_best else qmt_best is None,
            "ptrade_best_score_match": (
                qmt_p_score is not None and row["score"] is not None
                and abs(qmt_p_score - row["score"]) <= 0.00005
            ) if p_best and row["score"] is not None else True,
            "reason": row["reason"],
        })

    scored = [item for item in comparisons if item["ptrade_best"] is not None]
    artifact = {
        "schema_version": 1, "kind": "qmt_v1_1_15_daily_score_parity",
        "created_at": datetime.now().astimezone().isoformat(),
        "adjustment_mode": args.adjustment, "raw_mode": "not_used",
        "ptrade_log": str(args.ptrade_log), "orders_enabled": False,
        "errors": errors, "ptrade_day_count": len(rows),
        "scored_day_count": len(scored),
        "best_code_matches": sum(item["best_code_match"] for item in scored),
        "ptrade_best_score_matches": sum(item["ptrade_best_score_match"] for item in scored),
        "first_best_code_mismatch": next((item for item in scored if not item["best_code_match"]), None),
        "first_score_mismatch": next((item for item in scored if not item["ptrade_best_score_match"]), None),
        "comparisons": comparisons,
    }
    evidence_dir = ROOT / "runtime_data" / "evidence" / "simulation"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = evidence_dir / ("qmt_v1_1_15_daily_score_parity_%s.json" % stamp)
    output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), "errors": errors, "ptrade_day_count": len(rows),
                      "scored_day_count": len(scored), "best_code_matches": artifact["best_code_matches"],
                      "ptrade_best_score_matches": artifact["ptrade_best_score_matches"],
                      "first_best_code_mismatch": artifact["first_best_code_mismatch"],
                      "first_score_mismatch": artifact["first_score_mismatch"]},
                     ensure_ascii=False, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
