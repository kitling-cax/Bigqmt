"""Prepare a PIT-factor candidate from QMT factor-event evidence.

This is a local, non-publishing derivation.  It never infers factors from
adjusted prices and never writes the shared lake.  The resulting rows remain
blocked until an independent canonical corporate-action chain confirms them.
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import duckdb

ROOT = Path(__file__).resolve().parents[1]
SHANGHAI = timezone(timedelta(hours=8))


def _factor_events(path: Path) -> dict[str, list[tuple[str, float]]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    events: dict[str, list[tuple[str, float]]] = {}
    for item in data.get("results", []):
        code = str(item.get("code"))
        rows: list[tuple[str, float]] = []
        for day, payload in (item.get("factors") or {}).items():
            for _timestamp, values in (payload or {}).items():
                try:
                    factor = float(values[-1])
                    if math.isfinite(factor) and factor > 0:
                        rows.append((str(day), factor))
                except (TypeError, ValueError, IndexError):
                    continue
        events[code] = sorted(rows)
    return events


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("release_dir", type=Path)
    parser.add_argument("--factor-evidence", type=Path,
                        default=ROOT / "runtime_data" / "evidence" / "simulation" / "bigqmt_missing_key_scans" / "divid_factor_cache_probe_20260912_120237.json")
    args = parser.parse_args()
    daily_path = args.release_dir / "daily_raw_overlay.parquet"
    with duckdb.connect() as db:
        rows = db.execute("select code, trade_date, period, adjustment_mode, row_hash from read_parquet(?) order by code, trade_date",
                          [str(daily_path)]).fetchall()
    events = _factor_events(args.factor_evidence)
    candidates: list[dict[str, Any]] = []
    missing_event_history: list[str] = []
    for code, trade_date, period, adjustment_mode, row_hash in rows:
        code = str(code); day = str(trade_date).replace("-", "")[:8]
        applicable = [(event_day, factor) for event_day, factor in events.get(code, []) if event_day <= day]
        product = 1.0
        for _event_day, factor in applicable:
            product *= factor
        if not events.get(code):
            missing_event_history.append(code)
        candidates.append({
            "code": code, "trade_date": day, "period": str(period), "adjustment_mode": str(adjustment_mode),
            "row_hash": str(row_hash), "adjustment_factor_candidate": product,
            "latest_event_day": applicable[-1][0] if applicable else None,
            "event_count_through_bar": len(applicable),
            "factor_source": "bigqmt_get_divid_factors_event_cache",
            "available_at_status": "UNVERIFIED_CANONICAL_PIT",
        })
    result = {
        "schema_version": 1, "kind": "bigqmt_pit_factor_candidate",
        "created_at": datetime.now(SHANGHAI).isoformat(), "mode": "LOCAL_CANDIDATE_ONLY_NO_LAKE_WRITE",
        "release_id": json.loads((args.release_dir / "manifest.json").read_text(encoding="utf-8")).get("release_id"),
        "factor_evidence": str(args.factor_evidence), "candidate_rows": len(candidates),
        "event_codes": len(events), "event_count": sum(len(v) for v in events.values()),
        "codes_without_any_qmt_event": sorted(set(missing_event_history)),
        "rows": candidates,
        "gate": "BLOCKED_CANONICAL_PIT_AND_AVAILABLE_AT_UNVERIFIED",
        "lake_write": False, "global_latest_updated": False,
        "next_action": "Cross-check event payloads and available_at against canonical miniQMT/Tushare corporate-action chain",
    }
    path = args.release_dir / "pit_factor_candidate.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"path": str(path), "candidate_rows": len(candidates), "event_count": result["event_count"],
                      "codes_without_any_qmt_event": result["codes_without_any_qmt_event"],
                      "gate": result["gate"], "lake_write": False, "global_latest_updated": False}, ensure_ascii=False, indent=2))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
