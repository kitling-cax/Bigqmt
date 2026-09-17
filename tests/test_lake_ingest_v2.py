import pandas as pd
import pytest

from kitling_bigqmt.lake_ingest_v2 import (
    APPROVAL_TOKEN,
    BronzeIngestError,
    normalize_bigqmt,
    normalize_tushare,
    publish_bronze_candidate,
    validate_bronze,
)


def test_normalize_and_validate_source_facts():
    big = pd.DataFrame([{
        "code": "510300.SH", "bar_time": "2026-09-11T07:00:00Z", "trade_date": "20260911", "period": "1d",
        "open": 4.6, "high": 4.7, "low": 4.5, "close": 4.65, "volume_lots": 100, "amount_yuan": 465000,
    }])
    out = normalize_bigqmt(big, "big-test", {"510300.SH"})
    assert out.iloc[0]["asset_class"] == "etf"
    assert out.iloc[0]["raw_volume_unit"] == "lots_measured"
    assert validate_bronze(out)["ohlc_valid"] is True


def test_tushare_units_are_retained_not_silently_converted():
    ts = pd.DataFrame([{
        "ts_code": "000001.SZ", "trade_date": "20260911", "new_open": 10, "new_high": 11,
        "new_low": 9, "new_close": 10.5, "new_volume_lots": 100, "new_amount_thousand_yuan": 1050,
    }])
    out = normalize_tushare(ts, "ts-test")
    assert out.iloc[0]["raw_amount"] == 1050
    assert out.iloc[0]["raw_amount_unit"] == "thousand_cny"


def test_publish_requires_token_and_isolated_target(tmp_path):
    frame = pd.DataFrame([{
        "code": "000001.SZ", "bar_time": "2026-09-11T07:00:00Z", "trade_date": "20260911", "period": "1d",
        "open": 1, "high": 2, "low": 1, "close": 1.5, "volume_lots": 1, "amount_yuan": 1,
    }])
    out = normalize_bigqmt(frame, "big-test")
    with pytest.raises(PermissionError):
        publish_bronze_candidate([out], "r1", tmp_path, "")
    result = publish_bronze_candidate([out], "r1", tmp_path, APPROVAL_TOKEN)
    assert result["status"] == "PUBLISHED_ISOLATED_BRONZE_CANDIDATE"
    assert (tmp_path / "v2" / "bronze" / "bars" / "_releases" / "r1" / "manifest.json").exists()
    assert result["global_latest_updated"] is False


def test_duplicate_source_business_key_is_rejected():
    frame = pd.DataFrame([{
        "code": "000001.SZ", "bar_time": "2026-09-11T07:00:00Z", "trade_date": "20260911", "period": "1d",
        "open": 1, "high": 2, "low": 1, "close": 1.5, "volume_lots": 1, "amount_yuan": 1,
    }])
    out = normalize_bigqmt(pd.concat([frame, frame], ignore_index=True), "big-test")
    with pytest.raises(BronzeIngestError, match="validation failed"):
        validate_bronze(out)
