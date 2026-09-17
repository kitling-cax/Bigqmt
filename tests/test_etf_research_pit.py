import pandas as pd
import pytest

from kitling_bigqmt.etf_research_pit import (
    build_rows,
    filter_available_asof,
    next_trade_day,
    split_events_from_evidence,
    trailing_return_drawdown_inputs,
    validate_rows,
)


def test_next_trade_day_and_split_factor_are_conservative():
    assert next_trade_day(["20260102", "20260105"], "20260102") == "20260105"
    split = {"rows": [{"code": "159941.SZ", "qmt_event_date": "20260102", "qmt_payload": [0, 3, 0, 0, 0, 0, 4],
                       "split_record": {"split_ratio": 4}, "bonus_shares_relation": "MATCH"}]}
    announcements = {"results": [{"code": "159941.SZ", "announcements": [{"announcement_date": "20251231"}]}]}
    events = split_events_from_evidence(split, announcements, {"159941.SZ"}, ["20260102", "20260105"])
    assert events[0]["available_at"].startswith("2026-01-05T09:30")
    raw = [
        {"code": "159941.SZ", "trade_date": "20260102", "open": 1, "high": 1, "low": 1, "close": 1, "volume_lots": 1, "amount_yuan": 1},
        {"code": "159941.SZ", "trade_date": "20260105", "open": 1, "high": 1, "low": 1, "close": 1, "volume_lots": 1, "amount_yuan": 1},
    ]
    rows = build_rows(raw, events, "release")
    assert rows[0]["adjustment_factor"] == 4
    assert rows[0]["available_at"].startswith("2026-01-05T09:30")
    assert rows[1]["close"] == 4
    assert validate_rows(rows, {"159941.SZ"}, events)["all_checks_passed"] is True


def test_asof_filter_and_trailing_metrics_exclude_future_available_bar():
    frame = pd.DataFrame({
        "code": ["A"] * 3,
        "trade_date": ["20260101", "20260102", "20260103"],
        "close": [100.0, 110.0, 90.0],
        "available_at": ["2026-01-01T07:10:00+00:00", "2026-01-02T07:10:00+00:00", "2026-01-04T07:10:00+00:00"],
        "bar_available_at": ["2026-01-01T07:10:00+00:00", "2026-01-02T07:10:00+00:00", "2026-01-03T07:10:00+00:00"],
        "row_hash": ["1", "2", "3"],
    })
    usable = filter_available_asof(frame, "2026-01-03T15:30:00+08:00")
    assert usable["trade_date"].dt.strftime("%Y%m%d").tolist() == ["20260101", "20260102"]
    metric = trailing_return_drawdown_inputs(usable, lookback=1)[0]
    assert metric["trailing_return"] == pytest.approx(0.1)
    with pytest.raises(ValueError, match="timezone"):
        filter_available_asof(frame, "2026-01-03")
