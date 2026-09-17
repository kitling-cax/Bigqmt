"""Read-only root-cause probe for the residual v1.1.15 QMT/PTrade score gaps.

For each case (code + PTrade mismatch end-day), pull QMT none/front/back
daily closes and the cached dividend/ex-right factors over the same window,
then recompute the legacy weighted momentum.  This isolates whether a gap is
an adjustment-factor difference, a price-precision difference, or neither.
It never writes to the lake or QMT cache and never calls an order method.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kitling_bigqmt.market_data import normalize_daily_bars  # noqa: E402
from kitling_bigqmt.readonly_rpc import ReadOnlyBigQmtClient  # noqa: E402
from kitling_bigqmt.redis_resp import RedisRespClient  # noqa: E402
from kitling_bigqmt.machine_config import load_gateway  # noqa: E402
from kitling_bigqmt.v1_1_15_reproduction import legacy_weighted_momentum  # noqa: E402


# (qmt_code, PTrade mismatch end-day, short label) — the residual gaps seen in
# the 2026-09-15 front parity, net of PTRADE_FREEZE_EXCLUSION.
CASES = [
    ("159915.SZ", "20180326", "first-best-code-mismatch-159915"),
    ("159941.SZ", "20180523", "153-may-cluster-159941"),
    ("161127.SZ", "20180523", "153-may-cluster-161127"),
    ("162415.SZ", "20180523", "153-may-cluster-162415"),
    ("512200.SH", "20191220", "59b-2019-cluster-512200"),
    ("515880.SH", "20191220", "59b-2019-cluster-515880"),
    ("161127.SZ", "20191220", "59b-2019-cluster-161127"),
    ("159667.SZ", "20260622", "159667-score-value"),
    ("159995.SZ", "20260715", "159995-score-value"),
]
LOOKBACK_DAYS = 90


def _iso(value: str) -> str:
    return "%s-%s-%s" % (value[:4], value[4:6], value[6:8])


def run(cases: list[tuple[str, str, str]]) -> dict:
    cfg = load_gateway(ROOT, "simulation")
    redis_cfg = cfg["redis"]
    client = ReadOnlyBigQmtClient(
        RedisRespClient(redis_cfg["host"], redis_cfg["port"], redis_cfg["db"], timeout=5),
        cfg["account_id"],
        timeout_seconds=float(cfg.get("rpc_timeout_seconds", 12)),
    )
    artifact = {
        "schema_version": 1,
        "kind": "qmt_v1_1_15_adjustment_rootcause_probe",
        "created_at": datetime.now().astimezone().isoformat(),
        "account_id": str(cfg["account_id"]),
        "orders_enabled": False,
        "lake_write": False,
        "qmt_cache_write": False,
        "cases": [],
    }
    for code, end_day, label in cases:
        end = datetime.strptime(end_day, "%Y%m%d")
        start = end - timedelta(days=LOOKBACK_DAYS)
        start_str = start.strftime("%Y%m%d")
        entry = {"code": code, "label": label, "ptrade_end_day": end_day,
                 "range": {"start": start_str, "end": end_day}, "modes": {}, "factors": None, "errors": []}
        try:
            client.download_history_data(code, "1d", start_str, end_day)
            for dividend_type in ("none", "front", "back"):
                response = client.market_data_ex(
                    [code], ["close", "preClose", "suspendFlag", "time"],
                    "1d", start_str, end_day, -1, dividend_type, False,
                )
                bars = normalize_daily_bars(response, code)
                closes = [float(bar.close) for bar in bars if bar.close is not None and bar.close > 0]
                momentum = legacy_weighted_momentum(closes[-25:]) if len(closes) >= 25 else None
                tail = [{"d": bar.trade_date, "c": bar.close, "pc": bar.pre_close,
                         "s": bar.suspend_flag} for bar in bars[-8:]]
                entry["modes"][dividend_type] = {
                    "row_count": len(bars), "last_close": tail[-1]["c"] if tail else None,
                    "momentum_25d": momentum, "tail": tail,
                }
            try:
                factor_response = client.divid_factors(code, start_str, end_day)
                payload = factor_response.get("data")
                entry["factors"] = payload if isinstance(payload, (dict, list)) else {"raw": str(payload)[:2000]}
            except Exception as exc:
                entry["errors"].append({"stage": "divid_factors", "error": "%s: %s" % (type(exc).__name__, exc)})
        except Exception as exc:
            entry["errors"].append({"stage": "daily", "error": "%s: %s" % (type(exc).__name__, exc)})
        artifact["cases"].append(entry)
    return artifact


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    artifact = run(CASES)
    evidence_dir = ROOT / "runtime_data" / "evidence" / "simulation"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    output = args.output or evidence_dir / (
        "qmt_v1_1_15_adjustment_rootcause_%s.json" % datetime.now().strftime("%Y%m%d_%H%M%S"))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
