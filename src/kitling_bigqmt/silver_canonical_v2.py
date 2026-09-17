"""Build a source-reconciled Silver Raw candidate from v2 Bronze facts."""
from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


PRIORITY = ("miniqmt", "bigqmt", "tushare")
OUT_COLUMNS = ("code", "bar_time", "trade_date", "frequency", "asset_class", "open", "high", "low", "close",
               "volume_lots", "amount_yuan", "source_selected", "source_candidates", "quality_status",
               "available_at", "row_hash")


def _amount(row: dict[str, Any]) -> float:
    unit = str(row.get("raw_amount_unit") or "")
    value = float(row["raw_amount"])
    if unit == "thousand_cny":
        return value * 1000.0
    if unit in {"cny", "cny_measured"}:
        return value
    raise ValueError("unknown amount unit for %s: %s" % (row.get("source"), unit))


def _same(a: float, b: float) -> bool:
    return abs(a - b) <= max(1e-8, 1e-6 * max(abs(a), abs(b), 1.0))


def _same_field(a: float, b: float, index: int) -> bool:
    if index == 4:  # Tushare fund_daily may report fractional lots.
        return abs(a - b) <= 0.5
    if index == 5:  # Amount is rounded to yuan in QMT exports.
        return abs(a - b) <= 2.0
    return _same(a, b)


def _canonical_bar_time(item: dict[str, Any]) -> str:
    """Align source-specific timestamps without losing intraday identity."""
    frequency = str(item.get("frequency") or "")
    trade_date = str(item.get("trade_date") or "")
    if frequency == "1d":
        # Daily bars from QMT/Tushare use different close timestamps; the
        # business key is the exchange trade date.
        return trade_date
    raw = str(item.get("bar_time") or "")
    try:
        if "+" in raw or raw.endswith("Z") or "UTC" in raw:
            return pd.to_datetime(raw, utc=True).isoformat()
        digits = "".join(ch for ch in raw if ch.isdigit())
        if len(digits) >= 14:
            local = pd.to_datetime(digits[:14], format="%Y%m%d%H%M%S", errors="raise")
            return local.tz_localize("Asia/Shanghai").tz_convert("UTC").isoformat()
    except (TypeError, ValueError):
        pass
    return raw


def build_candidate(bronze: pd.DataFrame, release_id: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    required = {"code", "trade_date", "frequency", "asset_class", "open", "high", "low", "close",
                "raw_volume", "raw_amount", "raw_amount_unit", "source", "received_at"}
    missing = sorted(required - set(bronze.columns))
    if missing:
        raise ValueError("Bronze candidate missing: %s" % ",".join(missing))
    if "bar_time" not in bronze.columns:
        # Backward-compatible daily fixtures: a daily business date is the
        # canonical bar-time key. New intraday inputs must provide bar_time.
        bronze = bronze.copy()
        bronze["bar_time"] = bronze["trade_date"].astype(str)
    else:
        bronze = bronze.copy()
    # Normalize mixed parquet/CSV timestamp dtypes before pandas groupby
    # (otherwise integer MiniQMT timestamps and Timestamp BigQMT values cannot
    # be sorted together).
    bronze["bar_time"] = bronze.apply(lambda row: _canonical_bar_time(row.to_dict()), axis=1)
    rows: list[dict[str, Any]] = []
    group_keys = ["code", "bar_time", "trade_date", "frequency", "asset_class"]
    for key, group in bronze.groupby(group_keys, sort=True):
        candidates: list[dict[str, Any]] = []
        for item in group.to_dict(orient="records"):
            candidates.append({"source": str(item["source"]), "bar_time": _canonical_bar_time(item), "open": float(item["open"]), "high": float(item["high"]),
                               "low": float(item["low"]), "close": float(item["close"]), "volume_lots": float(item["raw_volume"]),
                               "amount_yuan": _amount(item), "received_at": str(item["received_at"]),
                               "source_release": str(item.get("source_release") or "")})
        candidates.sort(key=lambda item: PRIORITY.index(item["source"]) if item["source"] in PRIORITY else len(PRIORITY))
        selected = candidates[0]
        comparable = [(item["open"], item["high"], item["low"], item["close"], item["volume_lots"], item["amount_yuan"]) for item in candidates]
        verified = len(comparable) >= 2 and all(
            _same_field(row[index], comparable[0][index], index)
            for row in comparable[1:] for index in range(6)
        )
        quality = "VERIFIED_MULTI_SOURCE" if verified else ("VERIFIED_SINGLE_SOURCE" if len(candidates) == 1 else "CONFLICT")
        payload = {"code": str(key[0]), "bar_time": str(key[1]), "trade_date": str(key[2]), "frequency": str(key[3]), "asset_class": str(key[4]),
                   "open": selected["open"], "high": selected["high"], "low": selected["low"], "close": selected["close"],
                   "volume_lots": selected["volume_lots"], "amount_yuan": selected["amount_yuan"],
                   "source_selected": selected["source"] if quality != "CONFLICT" else None,
                   "source_candidates": json.dumps(candidates, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                   "quality_status": quality, "available_at": selected["received_at"], "source_release": release_id}
        payload["row_hash"] = __import__("hashlib").sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()
        rows.append(payload)
    frame = pd.DataFrame(rows)
    status_counts = frame["quality_status"].value_counts().to_dict()
    return frame, {"rows": len(frame), "codes": int(frame["code"].nunique()), "quality_status_counts": status_counts,
                   "verified_rows": int((frame["quality_status"] == "VERIFIED_MULTI_SOURCE").sum()),
                   "global_publishable": bool(len(frame) and not frame["quality_status"].isin({"CONFLICT"}).any())}


def publish_candidate(frame: pd.DataFrame, checks: dict[str, Any], release_id: str, lake_root: Path) -> dict[str, Any]:
    target = Path(lake_root).resolve() / "v2" / "silver" / "raw_canonical" / "_releases" / release_id
    if target.exists():
        raise ValueError("target exists: %s" % target)
    staging = target.parent / (".staging-" + release_id)
    staging.mkdir(parents=True, exist_ok=False)
    try:
        frame.to_parquet(staging / "bars_raw_canonical.parquet", index=False, engine="pyarrow", compression="zstd")
        manifest = {"schema_version": 2, "kind": "unified_v2_silver_raw_canonical_candidate", "release_id": release_id,
                    "status": "PUBLISHED_ISOLATED_SILVER_RAW_CANDIDATE", "created_at": datetime.now(timezone.utc).isoformat(),
                    **checks, "target": str(target), "global_latest_updated": False, "legacy_data_modified": False,
                    "pit_ready": False, "gates": {"raw_canonical": "PASSED", "pit_adjustment": "BLOCKED"},
                    "limitations": [
                        "conflict/provisional rows are retained for audit",
                        "no corporate actions or PIT factor asserted",
                        *(["MiniQMT absent"] if "miniqmt" not in set(frame.get("source_selected", pd.Series(dtype=str)).astype(str)) else []),
                    ]}
        (staging / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staging, target)
        return manifest
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
