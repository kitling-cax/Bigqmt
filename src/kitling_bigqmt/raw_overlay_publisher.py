"""Validate and copy-on-write publish an isolated BigQMT Raw overlay.

The default operation is read-only.  Publishing requires the explicit token
``PUBLISH_BIGQMT_RAW_OVERLAY`` and writes a versioned directory under
``bronze/_bigqmt_raw_releases`` only; legacy ``bronze/bars_raw`` and catalog
``LATEST`` are never modified by this module.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


APPROVAL_TOKEN = "PUBLISH_BIGQMT_RAW_OVERLAY"
REQUIRED_COLUMNS = (
    "code", "bar_time", "trade_date", "period", "adjustment_mode", "open", "high", "low", "close",
    "volume_lots", "amount_yuan", "source", "source_release", "available_at", "row_hash",
)
BUSINESS_KEY = ("code", "bar_time", "period", "adjustment_mode")


class RawOverlayPublishError(ValueError):
    pass


def _read_frame(path: Path, expected_periods: set[str]) -> pd.DataFrame:
    if not path.is_file():
        raise RawOverlayPublishError("missing candidate file: %s" % path)
    frame = pd.read_parquet(path)
    missing = sorted(set(REQUIRED_COLUMNS) - set(frame.columns))
    if missing:
        raise RawOverlayPublishError("%s missing columns: %s" % (path.name, ",".join(missing)))
    frame = frame.loc[:, list(REQUIRED_COLUMNS)].copy()
    if frame.empty:
        raise RawOverlayPublishError("%s is empty" % path.name)
    if not set(frame["period"].astype(str)).issubset(expected_periods):
        raise RawOverlayPublishError("%s contains unsupported periods" % path.name)
    if set(frame["adjustment_mode"].astype(str)) != {"none"}:
        raise RawOverlayPublishError("%s is not raw adjustment_mode=none" % path.name)
    for column in ("open", "high", "low", "close"):
        if frame[column].isna().any() or (frame[column].astype(float) <= 0).any():
            raise RawOverlayPublishError("%s contains invalid %s" % (path.name, column))
    if (frame["high"].astype(float) < frame[["open", "low", "close"]].astype(float).max(axis=1)).any():
        raise RawOverlayPublishError("%s violates high OHLC relation" % path.name)
    if (frame["low"].astype(float) > frame[["open", "high", "close"]].astype(float).min(axis=1)).any():
        raise RawOverlayPublishError("%s violates low OHLC relation" % path.name)
    if (frame["volume_lots"].astype(float) < 0).any() or (frame["amount_yuan"].astype(float) < 0).any():
        raise RawOverlayPublishError("%s contains negative volume or amount" % path.name)
    if frame[list(BUSINESS_KEY)].duplicated().any():
        raise RawOverlayPublishError("%s contains duplicate business keys" % path.name)
    if frame["row_hash"].astype(str).duplicated().any():
        raise RawOverlayPublishError("%s contains duplicate row hashes" % path.name)
    return frame


def validate_candidate(release_dir: Path) -> dict[str, Any]:
    release_dir = Path(release_dir).resolve()
    try:
        manifest = json.loads((release_dir / "manifest.json").read_text(encoding="utf-8"))
        readiness = json.loads((release_dir / "import_readiness.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RawOverlayPublishError("candidate metadata is unreadable: %s" % exc)
    if manifest.get("mode") != "LOCAL_CANDIDATE_ONLY_NO_LAKE_WRITE":
        raise RawOverlayPublishError("candidate is not a local no-write release")
    if readiness.get("raw_bronze_import_ready") is not True:
        raise RawOverlayPublishError("raw_bronze_import_ready is not true")
    release_id = str(manifest.get("release_id") or "").strip()
    if not release_id or any(char in release_id for char in ("/", "\\", ":")):
        raise RawOverlayPublishError("invalid release_id")
    daily = _read_frame(release_dir / "daily_raw_overlay.parquet", {"1d"})
    intraday = _read_frame(release_dir / "intraday_raw_overlay.parquet", {"1m", "5m"})
    expected_daily = int((manifest.get("files", {}).get("daily_raw_overlay") or {}).get("rows", -1))
    expected_intraday = int((manifest.get("files", {}).get("intraday_raw_overlay") or {}).get("rows", -1))
    if len(daily) != expected_daily or len(intraday) != expected_intraday:
        raise RawOverlayPublishError("candidate row counts do not match manifest")
    return {
        "release_id": release_id, "release_dir": str(release_dir),
        "daily_rows": len(daily), "intraday_rows": len(intraday),
        "daily_codes": int(daily["code"].nunique()), "intraday_codes": int(intraday["code"].nunique()),
        "periods": {"daily": sorted(daily["period"].astype(str).unique().tolist()),
                    "intraday": sorted(intraday["period"].astype(str).unique().tolist())},
        "source_release": sorted(set(daily["source_release"].astype(str)) | set(intraday["source_release"].astype(str))),
        "pit_publishable": False,
        "legacy_bars_raw_modified": False,
        "latest_modified": False,
    }


def _tree_hash(path: Path) -> str:
    digest = hashlib.sha256()
    for child in sorted(item for item in path.rglob("*") if item.is_file()):
        digest.update(child.relative_to(path).as_posix().encode("utf-8"))
        digest.update(child.read_bytes())
    return digest.hexdigest()


def publish_isolated_raw(release_dir: Path, lake_root: Path, approval_token: str) -> dict[str, Any]:
    if approval_token != APPROVAL_TOKEN:
        raise PermissionError("explicit raw publish approval token is required")
    validation = validate_candidate(release_dir)
    lake_root = Path(lake_root).resolve()
    target = lake_root / "bronze" / "_bigqmt_raw_releases" / validation["release_id"]
    if target.exists():
        existing = target / "publish_manifest.json"
        if existing.is_file():
            old = json.loads(existing.read_text(encoding="utf-8"))
            if old.get("release_id") == validation["release_id"]:
                return {"status": "DUPLICATE", "target": str(target), "manifest": old}
        raise RawOverlayPublishError("target release already exists with a different manifest")
    staging = lake_root / "_staging" / ("bigqmt_raw_publish_" + validation["release_id"])
    if staging.exists():
        raise RawOverlayPublishError("staging path already exists; inspect before retry: %s" % staging)
    staging.mkdir(parents=True, exist_ok=False)
    try:
        (staging / "daily").mkdir()
        (staging / "intraday").mkdir()
        for source_name, destination_name in (("daily_raw_overlay.parquet", "daily"), ("intraday_raw_overlay.parquet", "intraday")):
            frame = pd.read_parquet(Path(release_dir) / source_name)
            frame["year"] = pd.to_datetime(frame["trade_date"].astype(str), format="%Y%m%d").dt.year.astype("int16")
            partition = ["year", "period"] if destination_name == "daily" else ["year", "month", "period"]
            if "month" in partition:
                frame["month"] = pd.to_datetime(frame["trade_date"].astype(str), format="%Y%m%d").dt.month.astype("int8")
            # Keep a release-local partition tree.  It is an immutable overlay,
            # not a merge into legacy bars_raw or a replacement of LATEST.
            for values, group in frame.groupby(partition, sort=True):
                if not isinstance(values, tuple):
                    values = (values,)
                directory = staging / destination_name
                for column, value in zip(partition, values):
                    directory = directory / ("%s=%s" % (column, value))
                directory.mkdir(parents=True, exist_ok=True)
                group.to_parquet(directory / ("part-%s.parquet" % hashlib.sha256(str(values).encode()).hexdigest()[:16]), index=False, engine="pyarrow")
        result = {
            **validation, "schema_version": 1,
            "release_id": validation["release_id"],
            "status": "PUBLISHED_ISOLATED_RAW",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "target": str(target), "staging": str(staging),
            "tree_hash": _tree_hash(staging),
            "logical_tables": {"daily": "bronze/bigqmt_raw_overlay", "intraday": "bronze/bigqmt_intraday_raw_overlay"},
            "physical_release_root": str(target),
            "pit_publishable": False, "latest_modified": False, "legacy_bars_raw_modified": False,
            "approval_token_used": True,
        }
        # Write the manifest before the atomic directory move.  If anything
        # fails before the move, the staging directory can be removed without
        # leaving a half-published table.  The global catalog is untouched.
        (staging / "publish_manifest.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staging, target)
        return result
    except Exception:
        shutil.rmtree(staging, ignore_errors=False)
        raise
