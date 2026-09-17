"""Build a conservative, research-only PIT price release for the U25 ETF pool.

This module deliberately has no broker operation and no global-catalog write.
It is designed for reproducible factor research/backtests: only independently
reconciled ETF split events are applied; action availability is conservatively
set to the next observed trading session after the event/announcement date.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd


SHANGHAI = timezone(timedelta(hours=8))


def day(value: Any) -> str:
    return str(value or "").replace("-", "")[:8]


def stable_hash(row: dict[str, Any]) -> str:
    fields = ("code", "trade_date", "open_raw", "high_raw", "low_raw", "close_raw",
              "volume_lots", "amount_yuan", "adjustment_factor", "available_at")
    payload = {key: row.get(key) for key in fields}
    text = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def next_trade_day(trading_days: list[str], value: str) -> str:
    for item in sorted(set(trading_days)):
        if item > value:
            return item
    raise ValueError("no later observed trading day after %s" % value)


def iso_at(value: str, hour: int, minute: int) -> str:
    parsed = datetime.strptime(value, "%Y%m%d")
    return datetime.combine(parsed.date(), time(hour, minute), tzinfo=SHANGHAI).isoformat()


def split_events_from_evidence(split_evidence: dict[str, Any], announcement_evidence: dict[str, Any],
                               codes: set[str], trading_days: list[str]) -> list[dict[str, Any]]:
    """Return only reconciled split events with a conservative availability time."""
    announcements: dict[str, list[str]] = {}
    for result in announcement_evidence.get("results", []):
        code = str(result.get("code") or "")
        announcements[code] = sorted({day(item.get("announcement_date")) for item in result.get("announcements", [])
                                      if day(item.get("announcement_date"))})
    output: list[dict[str, Any]] = []
    for row in split_evidence.get("rows", []):
        code = str(row.get("code") or "")
        event_day = day(row.get("qmt_event_date"))
        payload = list(row.get("qmt_payload") or [])
        split = dict(row.get("split_record") or {})
        ratio = float(split.get("split_ratio") or 0.0)
        bonus = float(payload[1]) if len(payload) > 1 else 0.0
        if code not in codes or not event_day or ratio <= 0:
            continue
        if str(row.get("bonus_shares_relation")) != "MATCH":
            raise ValueError("unreconciled split ratio for %s/%s" % (code, event_day))
        if abs((1.0 + bonus) - ratio) > max(0.01, ratio * 0.01):
            raise ValueError("QMT/external split-ratio mismatch for %s/%s" % (code, event_day))
        prior_announcements = [item for item in announcements.get(code, []) if item <= event_day]
        announcement_day = prior_announcements[-1] if prior_announcements else None
        conservative_anchor = max(event_day, announcement_day or event_day)
        available_day = next_trade_day(trading_days, conservative_anchor)
        output.append({
            "code": code, "event_date": event_day, "announcement_date": announcement_day,
            "split_ratio": ratio, "qmt_bonus_shares": bonus,
            "available_at": iso_at(available_day, 9, 30),
            "available_at_policy": "NEXT_OBSERVED_TRADING_SESSION_AFTER_EVENT_OR_ANNOUNCEMENT",
            "event_quality": "VERIFIED_EXTERNAL_SPLIT_RATIO_CONSERVATIVE_AVAILABLE_AT",
        })
    return sorted(output, key=lambda item: (item["code"], item["event_date"]))


def build_rows(raw_rows: list[dict[str, Any]], split_events: list[dict[str, Any]], release_id: str) -> list[dict[str, Any]]:
    """Turn verified raw ETF daily bars into a conservative PIT research view."""
    by_code: dict[str, list[dict[str, Any]]] = {}
    by_event: dict[tuple[str, str], dict[str, Any]] = {(item["code"], item["event_date"]): item for item in split_events}
    for row in raw_rows:
        by_code.setdefault(str(row["code"]), []).append(row)
    output: list[dict[str, Any]] = []
    for code, rows in sorted(by_code.items()):
        factor = 1.0
        factor_known_at = None
        for raw in sorted(rows, key=lambda item: str(item["trade_date"])):
            event = by_event.get((code, str(raw["trade_date"])))
            if event:
                factor *= float(event["split_ratio"])
                factor_known_at = event["available_at"]
            bar_at = iso_at(str(raw["trade_date"]), 15, 10)
            available_at = max(bar_at, factor_known_at or bar_at)
            row = {
                "code": code,
                "trade_date": str(raw["trade_date"]),
                "open": float(raw["open"]) * factor,
                "high": float(raw["high"]) * factor,
                "low": float(raw["low"]) * factor,
                "close": float(raw["close"]) * factor,
                "volume": float(raw["volume_lots"]),
                "amount": float(raw["amount_yuan"]),
                "open_raw": float(raw["open"]),
                "high_raw": float(raw["high"]),
                "low_raw": float(raw["low"]),
                "close_raw": float(raw["close"]),
                "volume_lots": float(raw["volume_lots"]),
                "amount_yuan": float(raw["amount_yuan"]),
                "adjustment_factor": factor,
                "adjustment_method": "FORWARD_SPLIT_ONLY_CONSERVATIVE_PIT_V1",
                "bar_available_at": bar_at,
                "factor_available_at": factor_known_at or bar_at,
                "available_at": available_at,
                "source": "bigqmt_cache+eastmoney_split_reconciliation",
                "source_release": release_id,
                "research_status": "RESEARCH_SAFE_ETF_SPLIT_PIT",
                "orders_enabled": False,
            }
            row["row_hash"] = stable_hash(row)
            output.append(row)
    return output


def validate_rows(rows: list[dict[str, Any]], expected_codes: set[str], events: list[dict[str, Any]]) -> dict[str, Any]:
    keys = [(str(row["code"]), str(row["trade_date"])) for row in rows]
    hashes = [str(row["row_hash"]) for row in rows]
    ohlc_ok = all(float(row["low"]) <= min(float(row["open"]), float(row["high"]), float(row["close"])) and
                  float(row["high"]) >= max(float(row["open"]), float(row["low"]), float(row["close"]))
                  for row in rows)
    factors_ok = all(float(row["adjustment_factor"]) > 0 for row in rows)
    availability_ok = all(str(row["available_at"]) >= str(row["bar_available_at"]) for row in rows)
    event_codes = {str(item["code"]) for item in events}
    return {
        "row_count": len(rows), "code_count": len({str(row["code"]) for row in rows}),
        "expected_codes_covered": expected_codes == {str(row["code"]) for row in rows},
        "business_key_unique": len(keys) == len(set(keys)), "row_hash_unique": len(hashes) == len(set(hashes)),
        "ohlc_ok": ohlc_ok, "positive_adjustment_factors": factors_ok,
        "available_at_not_before_bar": availability_ok,
        "verified_split_event_count": len(events), "verified_split_event_codes": sorted(event_codes),
        "all_checks_passed": bool(rows and expected_codes == {str(row["code"]) for row in rows} and
                                   len(keys) == len(set(keys)) and len(hashes) == len(set(hashes)) and
                                   ohlc_ok and factors_ok and availability_ok),
    }


def load_research_release(release: Path) -> tuple[dict[str, Any], pd.DataFrame]:
    """Load one explicitly selected isolated research PIT release.

    This never discovers or consults global ``LATEST``.  That makes research
    runs reproducible and prevents an isolated U25 release from being treated
    as the canonical all-market Silver/PIT data set.
    """
    release = Path(release).resolve()
    manifest = json.loads((release / "publish_manifest.json").read_text(encoding="utf-8"))
    if manifest.get("status") != "PUBLISHED_ISOLATED_RESEARCH_PIT":
        raise ValueError("research release is not published")
    if bool(manifest.get("global_latest_updated", False)) or bool(manifest.get("legacy_silver_bars_pit_modified", False)):
        raise ValueError("isolated research release safety contract violated")
    paths = sorted((release / "daily").rglob("*.parquet"))
    if not paths:
        raise ValueError("research release has no daily parquet files")
    frame = pd.concat([pd.read_parquet(path) for path in paths], ignore_index=True)
    required = {"code", "trade_date", "close", "available_at", "bar_available_at", "row_hash"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError("research release missing fields: %s" % ",".join(missing))
    if frame.empty or frame[["code", "trade_date"]].duplicated().any() or frame["row_hash"].duplicated().any():
        raise ValueError("research release has empty or duplicate business keys")
    return manifest, frame


def filter_available_asof(frame: pd.DataFrame, asof: str | pd.Timestamp) -> pd.DataFrame:
    """Return only bars legitimately visible at a timezone-aware research as-of."""
    cutoff = pd.Timestamp(asof)
    if cutoff.tzinfo is None:
        raise ValueError("asof must include timezone")
    result = frame.copy()
    result["available_at"] = pd.to_datetime(result["available_at"], utc=True)
    result["bar_available_at"] = pd.to_datetime(result["bar_available_at"], utc=True)
    result["trade_date"] = pd.to_datetime(result["trade_date"])
    result = result.loc[result["available_at"] <= cutoff.tz_convert("UTC")].copy()
    return result.sort_values(["code", "trade_date"]).reset_index(drop=True)


def max_drawdown(values: pd.Series) -> float:
    """Compute in-window peak-to-trough drawdown from a price/NAV sequence."""
    peak = values.cummax()
    return float((values / peak - 1.0).min()) if len(values) else 0.0


def trailing_return_drawdown_inputs(frame: pd.DataFrame, lookback: int = 25) -> list[dict[str, Any]]:
    """Build deterministic return/drawdown inputs, never a trading signal."""
    if lookback <= 0:
        raise ValueError("lookback must be positive")
    metrics: list[dict[str, Any]] = []
    for code, group in frame.groupby("code", sort=True):
        group = group.sort_values("trade_date")
        if len(group) < lookback + 1:
            continue
        window = group.tail(lookback + 1)
        start = float(window.iloc[0]["close"])
        end = float(window.iloc[-1]["close"])
        metrics.append({
            "code": str(code), "asof_trade_date": pd.Timestamp(window.iloc[-1]["trade_date"]).strftime("%Y%m%d"),
            "lookback_sessions": lookback, "trailing_return": end / start - 1.0,
            "maximum_drawdown": max_drawdown(window["close"].astype(float)),
            "data_available_at": str(window["available_at"].max()),
            "research_status": "INPUT_ONLY_NO_TRADING_SIGNAL",
        })
    return metrics
