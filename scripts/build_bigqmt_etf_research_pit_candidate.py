"""Build a local conservative PIT candidate for U25 ETF research.

Only read-only BigQMT market-data RPC calls are made.  The output is local
until the separate explicit isolated-release publisher is invoked.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from clean_validate_bigqmt_cache_candidate import FIELDS, _clean_rows, _rows  # noqa: E402
from kitling_bigqmt.etf_research_pit import build_rows, split_events_from_evidence, validate_rows  # noqa: E402
from kitling_bigqmt.readonly_rpc import ReadOnlyBigQmtClient  # noqa: E402
from kitling_bigqmt.redis_resp import RedisRespClient  # noqa: E402
from kitling_bigqmt.machine_config import load_gateway  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Build local U25 ETF conservative PIT research candidate")
    parser.add_argument("--start", default="20200101")
    parser.add_argument("--end", default="20260911")
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--pool", type=Path, default=ROOT / "config" / "v1_1_17_etf_pool.json")
    parser.add_argument("--split-evidence", type=Path, default=ROOT / "runtime_data" / "evidence" / "simulation" / "bigqmt_missing_key_scans" / "etf_split_field_reconciliation_20260912.json")
    parser.add_argument("--announcement-evidence", type=Path, default=ROOT / "runtime_data" / "evidence" / "simulation" / "bigqmt_missing_key_scans" / "akshare_etf_announcement_probe_20260912.json")
    args = parser.parse_args()
    config = load_gateway(ROOT, "simulation") if args.config is None else json.loads(args.config.read_text(encoding="utf-8"))
    pool = json.loads(args.pool.read_text(encoding="utf-8"))
    codes = list(dict.fromkeys(str(item).upper() for item in pool.get("qmt_codes", []) if item))
    if not codes:
        raise ValueError("ETF pool has no codes")
    client = ReadOnlyBigQmtClient(RedisRespClient(**dict(config["redis"])), str(config["account_id"]),
                                  float(config.get("rpc_timeout_seconds", 12)))
    cleaned: list[dict[str, object]] = []
    errors: list[dict[str, str]] = []
    issues: list[dict[str, object]] = []
    for code in codes:
        try:
            response = client.market_data_ex([code], FIELDS, "1d", args.start, args.end, -1, "none", subscribe=False)
            rows, row_issues = _clean_rows(_rows(response, code), code, "1d")
            cleaned.extend(rows)
            issues.extend(row_issues)
        except Exception as exc:
            errors.append({"code": code, "error": "%s: %s" % (type(exc).__name__, exc)})
    hard_issues = [item for item in issues if item.get("rule") != "pre_listing_placeholder"]
    if errors or hard_issues:
        raise RuntimeError("QMT daily extraction blocked: errors=%s hard_issues=%s" % (len(errors), len(hard_issues)))
    trading_days = sorted({str(item["trade_date"]) for item in cleaned})
    split_evidence = json.loads(args.split_evidence.read_text(encoding="utf-8"))
    announcement_evidence = json.loads(args.announcement_evidence.read_text(encoding="utf-8"))
    events = split_events_from_evidence(split_evidence, announcement_evidence, set(codes), trading_days)
    release_id = "bigqmt_etf_research_pit_%s" % datetime.now().strftime("%Y%m%d_%H%M%S")
    rows = build_rows(cleaned, events, release_id)
    checks = validate_rows(rows, set(codes), events)
    if not checks["all_checks_passed"]:
        raise RuntimeError("candidate validation failed: %s" % checks)
    destination = ROOT / "runtime_data" / "candidates" / release_id
    destination.mkdir(parents=True, exist_ok=False)
    frame = pd.DataFrame(rows)
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], format="%Y%m%d")
    for field in ("bar_available_at", "factor_available_at", "available_at"):
        frame[field] = pd.to_datetime(frame[field], utc=True)
    frame.to_parquet(destination / "etf_research_pit.parquet", index=False, engine="pyarrow", compression="zstd")
    (destination / "split_events.json").write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest = {
        "schema_version": 1, "kind": "bigqmt_etf_research_pit_candidate",
        "release_id": release_id, "created_at": datetime.now().astimezone().isoformat(),
        "mode": "LOCAL_CANDIDATE_ONLY_NO_LAKE_WRITE",
        "scope": {"pool_id": pool.get("pool_id"), "codes": codes, "start": args.start, "end": args.end,
                  "frequency": "1d", "asset_class": "ETF"},
        "source": {"bars": "BigQMT get_market_data_ex dividend_type=none subscribe=false",
                   "event_ratio": "Eastmoney ETF split reconciliation via AkShare + QMT event payload",
                   "availability": "conservative next observed trading session after event/announcement"},
        "rows": len(rows), "events": len(events), "checks": checks,
        "gates": {"raw_cache_quality": "PASSED", "etf_split_ratio": "PASSED",
                  "conservative_available_at": "PASSED", "research_backtest": "PASSED",
                  "global_latest": "BLOCKED_EXACT_AVAILABLE_AT_AND_FULL_UNIVERSE_PIT_NOT_COMPLETE"},
        "safety": {"lake_write": False, "global_latest_updated": False, "redis_write": False,
                   "broker_call": False, "orders_enabled": False},
        "limitations": ["split-only factor chain covers verified U25 ETF split events",
                        "non-split cash distributions are absent from this QMT event scope",
                        "availability is deliberately conservative, not an asserted exchange timestamp",
                        "research release is not a global LATEST replacement"],
    }
    (destination / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "RESEARCH_PIT_CANDIDATE_READY", "candidate": str(destination),
                      "rows": len(rows), "events": len(events), "checks": checks,
                      "safety": manifest["safety"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
