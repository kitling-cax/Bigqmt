"""Source-preserving Bronze ingestion for unified market-data lake v2."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd


BRONZE_COLUMNS = (
    "code", "bar_time", "trade_date", "frequency", "asset_class", "open", "high", "low", "close",
    "raw_volume", "raw_amount", "raw_volume_unit", "raw_amount_unit", "price_basis", "source",
    "source_release", "received_at", "ingested_at", "row_hash",
)
APPROVAL_TOKEN = "PUBLISH_UNIFIED_V2_BRONZE"


class BronzeIngestError(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash(row: dict[str, Any]) -> str:
    fields = {key: row.get(key) for key in BRONZE_COLUMNS if key not in {"row_hash", "ingested_at"}}
    payload = json.dumps(fields, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _asset(code: str, etf_codes: set[str]) -> str:
    return "etf" if str(code).upper() in etf_codes else "stock"


def normalize_bigqmt(frame: pd.DataFrame, source_release: str, etf_codes: set[str] | None = None,
                     received_at: str | None = None) -> pd.DataFrame:
    """Normalize BigQMT raw bars without converting them to adjusted prices."""
    required = {"code", "bar_time", "trade_date", "period", "open", "high", "low", "close", "volume_lots", "amount_yuan"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise BronzeIngestError("BigQMT frame missing: %s" % ",".join(missing))
    etf_codes = etf_codes or set()
    received_at = received_at or _now()
    rows: list[dict[str, Any]] = []
    for item in frame.to_dict(orient="records"):
        row = {
            "code": str(item["code"]).upper(), "bar_time": item["bar_time"], "trade_date": str(item["trade_date"]),
            "frequency": str(item["period"]), "asset_class": _asset(str(item["code"]), etf_codes),
            "open": float(item["open"]), "high": float(item["high"]), "low": float(item["low"]), "close": float(item["close"]),
            "raw_volume": float(item["volume_lots"]), "raw_amount": float(item["amount_yuan"]),
            "raw_volume_unit": "lots_measured", "raw_amount_unit": "cny_measured",
            "price_basis": "RAW_ADJUSTMENT_NONE", "source": "bigqmt", "source_release": source_release,
            "received_at": received_at, "ingested_at": _now(),
        }
        row["row_hash"] = _hash(row)
        rows.append(row)
    return pd.DataFrame(rows, columns=BRONZE_COLUMNS)


def normalize_tushare(frame: pd.DataFrame, source_release: str, etf_codes: set[str] | None = None,
                      received_at: str | None = None) -> pd.DataFrame:
    """Normalize a Tushare repair candidate while retaining its candidate status."""
    required = {"ts_code", "trade_date", "new_open", "new_high", "new_low", "new_close",
                "new_volume_lots", "new_amount_thousand_yuan"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise BronzeIngestError("Tushare frame missing: %s" % ",".join(missing))
    etf_codes = etf_codes or set()
    received_at = received_at or _now()
    rows: list[dict[str, Any]] = []
    for item in frame.to_dict(orient="records"):
        code = str(item["ts_code"]).upper()
        row = {
            "code": code, "bar_time": "%sT15:00:00+08:00" % str(item["trade_date"]), "trade_date": str(item["trade_date"]),
            "frequency": "1d", "asset_class": _asset(code, etf_codes),
            "open": float(item["new_open"]), "high": float(item["new_high"]), "low": float(item["new_low"]), "close": float(item["new_close"]),
            "raw_volume": float(item["new_volume_lots"]), "raw_amount": float(item["new_amount_thousand_yuan"]),
            "raw_volume_unit": "lots", "raw_amount_unit": "thousand_cny",
            "price_basis": "SOURCE_REPAIR_CANDIDATE_UNVERIFIED_RAW", "source": "tushare", "source_release": source_release,
            "received_at": received_at, "ingested_at": _now(),
        }
        row["row_hash"] = _hash(row)
        rows.append(row)
    return pd.DataFrame(rows, columns=BRONZE_COLUMNS)


def normalize_miniqmt(frame: pd.DataFrame, source_release: str, volume_unit: str,
                      amount_unit: str, etf_codes: set[str] | None = None,
                      received_at: str | None = None) -> pd.DataFrame:
    """Normalize an embedded-MiniQMT export only when units are explicit.

    The unit arguments are mandatory because the host cannot infer whether a
    particular MiniQMT build reports lots/shares or yuan/thousand-yuan.
    """
    if volume_unit.startswith("UNVERIFIED") or amount_unit.startswith("UNVERIFIED"):
        raise BronzeIngestError("MiniQMT units must be measured before import")
    required = {"code", "trade_date", "open", "high", "low", "close", "volume", "amount"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise BronzeIngestError("MiniQMT frame missing: %s" % ",".join(missing))
    etf_codes = etf_codes or set(); received_at = received_at or _now(); rows: list[dict[str, Any]] = []
    frequency = str(frame["frequency"].iloc[0]) if "frequency" in frame.columns and len(frame) else "1d"
    for item in frame.to_dict(orient="records"):
        code = str(item["code"]).upper(); trade_date = str(item["trade_date"])
        row = {"code": code, "bar_time": item.get("bar_time", "%sT15:00:00+08:00" % trade_date),
               "trade_date": trade_date, "frequency": str(item.get("frequency", frequency)),
               "asset_class": _asset(code, etf_codes), "open": float(item["open"]), "high": float(item["high"]),
               "low": float(item["low"]), "close": float(item["close"]), "raw_volume": float(item["volume"]),
               "raw_amount": float(item["amount"]), "raw_volume_unit": volume_unit, "raw_amount_unit": amount_unit,
               "price_basis": "RAW_ADJUSTMENT_NONE", "source": "miniqmt", "source_release": source_release,
               "received_at": received_at, "ingested_at": _now()}
        row["row_hash"] = _hash(row); rows.append(row)
    return pd.DataFrame(rows, columns=BRONZE_COLUMNS)


def validate_bronze(frame: pd.DataFrame) -> dict[str, Any]:
    missing = sorted(set(BRONZE_COLUMNS) - set(frame.columns))
    if missing:
        raise BronzeIngestError("normalized frame missing: %s" % ",".join(missing))
    if frame.empty:
        raise BronzeIngestError("normalized frame is empty")
    keys = ["source", "code", "bar_time", "frequency"]
    duplicate_keys = int(frame[keys].duplicated().sum())
    numeric = frame[["open", "high", "low", "close", "raw_volume", "raw_amount"]].apply(pd.to_numeric, errors="coerce")
    ohlc_ok = bool((numeric[["open", "high", "low", "close"]] > 0).all().all() and
                   (numeric["high"] >= numeric[["open", "low", "close"]].max(axis=1)).all() and
                   (numeric["low"] <= numeric[["open", "high", "close"]].min(axis=1)).all())
    quantity_ok = bool((numeric[["raw_volume", "raw_amount"]] >= 0).all().all())
    hash_ok = not frame["row_hash"].astype(str).duplicated().any()
    if duplicate_keys or not ohlc_ok or not quantity_ok or not hash_ok:
        raise BronzeIngestError("Bronze validation failed keys=%s ohlc=%s quantity=%s hashes=%s" % (duplicate_keys, ohlc_ok, quantity_ok, hash_ok))
    return {"rows": len(frame), "codes": int(frame["code"].nunique()), "duplicate_business_keys": duplicate_keys,
            "ohlc_valid": ohlc_ok, "quantity_nonnegative": quantity_ok, "row_hash_unique": hash_ok,
            "min_trade_date": str(frame["trade_date"].min()), "max_trade_date": str(frame["trade_date"].max())}


def publish_bronze_candidate(frames: Iterable[pd.DataFrame], release_id: str, lake_root: Path,
                             approval_token: str) -> dict[str, Any]:
    if approval_token != APPROVAL_TOKEN:
        raise PermissionError("explicit unified Bronze publish approval token is required")
    combined = pd.concat(list(frames), ignore_index=True)
    checks_by_source: dict[str, Any] = {}
    for source, group in combined.groupby("source", sort=True):
        checks_by_source[str(source)] = validate_bronze(group)
    target = Path(lake_root).resolve() / "v2" / "bronze" / "bars" / "_releases" / release_id
    if target.exists():
        raise BronzeIngestError("target release already exists: %s" % target)
    staging = target.parent / (".staging-" + release_id)
    if staging.exists():
        raise BronzeIngestError("staging release already exists: %s" % staging)
    staging.mkdir(parents=True, exist_ok=False)
    try:
        for (source, asset_class, frequency, year), group in combined.assign(
            year=pd.to_datetime(combined["trade_date"].astype(str), format="%Y%m%d").dt.year.astype(int)
        ).groupby(["source", "asset_class", "frequency", "year"], sort=True):
            directory = staging / ("source=%s" % source) / ("asset_class=%s" % asset_class) / ("frequency=%s" % frequency) / ("year=%s" % year)
            directory.mkdir(parents=True, exist_ok=True)
            group.drop(columns=["year"]).to_parquet(directory / "part-0.parquet", index=False, engine="pyarrow", compression="zstd")
        result = {
            "schema_version": 2, "kind": "unified_v2_bronze_candidate", "release_id": release_id,
            "status": "PUBLISHED_ISOLATED_BRONZE_CANDIDATE", "created_at": _now(),
            "rows": len(combined), "sources": sorted(combined["source"].astype(str).unique().tolist()),
            "checks_by_source": checks_by_source, "target": str(target),
            "global_latest_updated": False, "legacy_data_modified": False,
            "silver_pit_ready": False, "approval_token_used": True,
            "limitations": [
                "source facts are not canonical winners",
                "PIT and available_at are not asserted by Bronze",
                *(["MiniQMT is absent unless independently supplied"] if "miniqmt" not in set(combined["source"].astype(str)) else []),
            ],
        }
        (staging / "manifest.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staging, target)
        return result
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
