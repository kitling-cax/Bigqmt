"""Explicit source-freshness checks for the unified v2 release gate."""
from __future__ import annotations
from typing import Any
import pandas as pd


def assess_source_freshness(frames: dict[str, pd.DataFrame], expected_last_trade_date: str) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for source, frame in frames.items():
        if frame.empty or "trade_date" not in frame.columns:
            results[source] = {"status": "BLOCKED_EMPTY_OR_MISSING_DATE"}; continue
        dates = pd.to_datetime(frame["trade_date"].astype(str), errors="coerce")
        latest = dates.max().strftime("%Y%m%d") if dates.notna().any() else None
        results[source] = {"latest_trade_date": latest, "expected_last_trade_date": expected_last_trade_date,
                           "status": "PASSED" if latest == expected_last_trade_date else "BLOCKED_STALE_OR_UNVERIFIED",
                           "rows": len(frame), "codes": int(frame["code" if "code" in frame.columns else "ts_code"].nunique())}
    return {"expected_last_trade_date": expected_last_trade_date, "sources": results,
            "all_sources_fresh": bool(results) and all(item["status"] == "PASSED" for item in results.values())}
