import pytest

from kitling_bigqmt.execution_holding import ActualHoldingBlocked, actual_holding_status, actual_open_entry


def test_actual_entry_is_derived_from_real_fills_not_shadow_state():
    entry = actual_open_entry([
        {"fill_id": "a", "stock_code": "160723.SZ", "side": "BUY", "quantity": 34200, "fill_time": "1789093235"},
        {"fill_id": "b", "stock_code": "160723.SZ", "side": "BUY", "quantity": 7200, "fill_time": "1789093235"},
    ], "160723.SZ")
    assert entry["entry_day"] == "20260911"
    assert entry["quantity"] == 41400


def test_actual_hold_counts_entry_day_like_v1_1_15_close_state():
    calendar = ["20260911", "20260914", "20260915", "20260916", "20260917"]
    pending = actual_holding_status("20260911", "20260916", calendar)
    assert pending["actual_hold_days"] == 4
    assert pending["allowed"] is False
    allowed = actual_holding_status("20260911", "20260917", calendar)
    assert allowed["allowed"] is True


def test_qmt_millisecond_calendar_rows_are_normalized_to_trading_days():
    # 2026-09-11 00:00:00 Asia/Shanghai, the representation returned by
    # this BigQMT terminal's get_trading_dates RPC.
    status = actual_holding_status("20260911", "20260911", [1789056000000])
    assert status["actual_hold_days"] == 1


def test_missing_calendar_entry_fails_closed():
    with pytest.raises(ActualHoldingBlocked):
        actual_holding_status("20260911", "20260914", ["20260914"])
