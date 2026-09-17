import pandas as pd
import pytest
from kitling_bigqmt.silver_canonical_v2 import build_candidate

def _row(source, amount, close=10):
    return {"code":"000001.SZ", "trade_date":"20260911", "frequency":"1d", "asset_class":"stock",
            "open":close, "high":close+1, "low":close-1, "close":close, "raw_volume":100,
            "raw_amount":amount, "raw_amount_unit":"cny" if source=="bigqmt" else "thousand_cny",
            "source":source, "received_at":"2026-09-12T00:00:00Z", "source_release":"r"}

def test_cross_source_amount_is_compared_after_explicit_unit_conversion():
    frame, checks = build_candidate(pd.DataFrame([_row("bigqmt", 100000), _row("tushare", 100)]), "r")
    assert checks["verified_rows"] == 1
    assert frame.iloc[0]["quality_status"] == "VERIFIED_MULTI_SOURCE"

def test_price_conflict_is_retained_but_not_global_publishable():
    frame, checks = build_candidate(pd.DataFrame([_row("bigqmt", 100000), _row("tushare", 100, close=11)]), "r")
    assert frame.iloc[0]["quality_status"] == "CONFLICT"
    assert checks["global_publishable"] is False

def test_fractional_lot_and_rounded_yuan_are_reconciled():
    frame, checks = build_candidate(pd.DataFrame([_row("bigqmt", 100000), _row("tushare", 100.0015)]), "r")
    assert checks["verified_rows"] == 1
