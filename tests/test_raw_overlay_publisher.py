import json
from pathlib import Path

import pandas as pd
import pytest

from kitling_bigqmt.raw_overlay_publisher import (
    APPROVAL_TOKEN, RawOverlayPublishError, publish_isolated_raw, validate_candidate,
)


COLS = ["code", "bar_time", "trade_date", "period", "adjustment_mode", "open", "high", "low", "close",
        "volume_lots", "amount_yuan", "source", "source_release", "available_at", "row_hash"]


def _release(tmp_path: Path) -> Path:
    release = tmp_path / "bigqmt_candidate_test"
    release.mkdir()
    rows = [{"code": "000001.SZ", "bar_time": "2026-09-11T07:00:00Z", "trade_date": "20260911",
             "period": "1d", "adjustment_mode": "none", "open": 1.0, "high": 1.2, "low": .9,
             "close": 1.1, "volume_lots": 100, "amount_yuan": 11000, "source": "bigqmt",
             "source_release": "test", "available_at": "2026-09-11T07:01:00Z", "row_hash": "hash1"}]
    frame = pd.DataFrame(rows, columns=COLS)
    frame.to_parquet(release / "daily_raw_overlay.parquet", index=False)
    intraday = frame.assign(period="1m", row_hash="hash2")
    intraday.to_parquet(release / "intraday_raw_overlay.parquet", index=False)
    (release / "manifest.json").write_text(json.dumps({"mode": "LOCAL_CANDIDATE_ONLY_NO_LAKE_WRITE", "release_id": "test_release",
                                                       "files": {"daily_raw_overlay": {"rows": 1}, "intraday_raw_overlay": {"rows": 1}}}), encoding="utf-8")
    (release / "import_readiness.json").write_text(json.dumps({"raw_bronze_import_ready": True}), encoding="utf-8")
    return release


def test_candidate_validation_and_default_publish_are_read_only(tmp_path):
    release = _release(tmp_path)
    checked = validate_candidate(release)
    assert checked["daily_rows"] == 1
    target = tmp_path / "lake"
    with pytest.raises(PermissionError):
        publish_isolated_raw(release, target, "")
    assert not target.exists()


def test_explicit_publish_is_versioned_and_does_not_touch_latest_or_legacy(tmp_path):
    release = _release(tmp_path)
    target = tmp_path / "lake"
    result = publish_isolated_raw(release, target, APPROVAL_TOKEN)
    assert result["status"] == "PUBLISHED_ISOLATED_RAW"
    assert (target / "bronze" / "_bigqmt_raw_releases" / "test_release" / "publish_manifest.json").is_file()
    assert result["latest_modified"] is False
    assert not (target / "bronze" / "bars_raw").exists()


def test_invalid_ohlc_is_rejected(tmp_path):
    release = _release(tmp_path)
    frame = pd.read_parquet(release / "daily_raw_overlay.parquet")
    frame.loc[0, "high"] = .5
    frame.to_parquet(release / "daily_raw_overlay.parquet", index=False)
    with pytest.raises(RawOverlayPublishError, match="high OHLC"):
        validate_candidate(release)
