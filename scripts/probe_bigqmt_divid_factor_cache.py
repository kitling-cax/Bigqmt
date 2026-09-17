"""Read-only probe for dividend/ex-right factors cached by BigQMT.

The probe uses daily ``preClose`` only to narrow likely event dates, then
reads the factor payload for each date through the single-date QMT API. It
never derives a factor from prices and never writes to the lake or QMT cache.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kitling_bigqmt.readonly_rpc import ReadOnlyBigQmtClient  # noqa: E402
from kitling_bigqmt.redis_resp import RedisRespClient  # noqa: E402
from kitling_bigqmt.machine_config import load_gateway  # noqa: E402


def _day(value: Any) -> str:
    number = float(value)
    if number > 10_000_000_000:
        number /= 1000.0
    return datetime.fromtimestamp(number, tz=timezone(timedelta(hours=8))).strftime("%Y%m%d")


def _rows(response: dict[str, Any], code: str) -> list[dict[str, Any]]:
    frame = (response.get("data") or {}).get(code, {})
    records = frame.get("records", frame) if isinstance(frame, dict) else []
    if isinstance(records, dict):
        lengths = [len(value) for value in records.values() if isinstance(value, list)]
        if not lengths or len(set(lengths)) != 1:
            return []
        return [{column: records[column][index] for column in records} for index in range(lengths[0])]
    if isinstance(records, list):
        return [dict(item) for item in records if isinstance(item, dict)]
    return []


def _codes() -> list[str]:
    pool = json.loads((ROOT / "config" / "v1_1_17_etf_pool.json").read_text(encoding="utf-8"))
    pool_codes = [str(item) for item in pool.get("qmt_codes", []) if item]
    reps = ["600519.SH", "000001.SZ", "300750.SZ", "688981.SH", "600000.SH", "000333.SZ"]
    return list(dict.fromkeys(reps + pool_codes))


def run(start: str, end: str) -> dict[str, Any]:
    cfg = load_gateway(ROOT, "simulation")
    redis_cfg = cfg["redis"]
    client = ReadOnlyBigQmtClient(
        RedisRespClient(redis_cfg["host"], redis_cfg["port"], redis_cfg["db"], timeout=5),
        cfg["account_id"],
        timeout_seconds=float(cfg.get("rpc_timeout_seconds", 12)),
    )
    result: dict[str, Any] = {
        "schema_version": 1,
        "kind": "bigqmt_divid_factor_cache_probe",
        "created_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "mode": "READ_ONLY_NO_DOWNLOAD_NO_IMPORT",
        "account_id": str(cfg["account_id"]),
        "source": "BigQMT get_divid_factors single-date RPC",
        "daily_narrowing_source": "get_market_data_ex dividend_type=none subscribe=false fields=time,close,preClose",
        "range": {"start": start, "end": end},
        "codes": _codes(),
        "summary": {"codes": 0, "daily_rows": 0, "event_days": 0, "nonempty_factor_days": 0, "empty_factor_days": 0, "errors": 0},
        "results": [],
        "lake_write": False,
        "qmt_cache_write": False,
    }
    for code in result["codes"]:
        item: dict[str, Any] = {"code": code, "daily_rows": 0, "event_days": [], "factors": {}, "errors": []}
        try:
            response = client.market_data_ex([code], ["time", "close", "preClose"], "1d", start, end, -1, "none", False)
            rows = _rows(response, code)
            item["daily_rows"] = len(rows)
            previous_close = None
            for row in rows:
                try:
                    close = float(row.get("close"))
                    pre_close = float(row.get("preClose"))
                    if previous_close is None or abs(pre_close - previous_close) > 1e-4:
                        item["event_days"].append(_day(row.get("time")))
                    previous_close = close
                except (TypeError, ValueError):
                    continue
            item["event_days"] = list(dict.fromkeys(item["event_days"]))
            for day in item["event_days"]:
                try:
                    factor_response = client.divid_factors(code, day, day)
                    payload = factor_response.get("data")
                    if isinstance(payload, dict) and payload:
                        item["factors"][day] = payload
                    else:
                        item.setdefault("empty_factor_days", []).append(day)
                except Exception as exc:  # evidence records errors per date
                    item["errors"].append({"day": day, "error": f"{type(exc).__name__}: {exc}"})
        except Exception as exc:
            item["errors"].append({"stage": "daily", "error": f"{type(exc).__name__}: {exc}"})
        result["results"].append(item)
        result["summary"]["codes"] += 1
        result["summary"]["daily_rows"] += int(item["daily_rows"])
        result["summary"]["event_days"] += len(item["event_days"])
        result["summary"]["nonempty_factor_days"] += len(item["factors"])
        result["summary"]["empty_factor_days"] += len(item.get("empty_factor_days", []))
        result["summary"]["errors"] += len(item["errors"])
    result["status"] = "PASSED" if result["summary"]["nonempty_factor_days"] > 0 and result["summary"]["errors"] == 0 else "BLOCKED"
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="20200101")
    parser.add_argument("--end", default="20260911")
    args = parser.parse_args()
    result = run(args.start, args.end)
    evidence_dir = ROOT / "runtime_data" / "evidence" / "simulation" / "bigqmt_missing_key_scans"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    path = evidence_dir / f"divid_factor_cache_probe_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    result["evidence"] = str(path)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
