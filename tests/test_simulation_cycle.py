from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from kitling_bigqmt.simulation_cycle import (
    SimulationExecutionBlocked,
    build_cycle_plan,
    deterministic_signal_id,
    is_execution_window,
)


TZ = ZoneInfo("Asia/Shanghai")


def _event(desired="160723.SZ", day="20260911"):
    return {"signal_day": day, "signal": {"desired_qmt": desired, "reason": "SMA4"}}


def _ticks(code="160723.SZ"):
    return {code: {"askPrice": [2.0], "bidPrice": [2.0], "lastPrice": 2.0}}


def test_execution_window_excludes_weekend_and_lunch_after_cutoff():
    assert is_execution_window(datetime(2026, 9, 14, 9, 35, tzinfo=TZ))
    assert not is_execution_window(datetime(2026, 9, 12, 10, 0, tzinfo=TZ))
    assert not is_execution_window(datetime(2026, 9, 14, 14, 51, tzinfo=TZ))


def test_cycle_is_deterministic_and_refuses_open_order_or_bad_reconciliation():
    kwargs = dict(
        now=datetime(2026, 9, 14, 10, 0, tzinfo=TZ), signal_event=_event(),
        activation_signal_not_before="20260911", sleeve_summary={"cash": 100000, "positions": []},
        ticks=_ticks(), account_id="90000001", open_orders=[], reconciliation_status="PASSED",
        trading_days=["20260911", "20260914"],
    )
    plan = build_cycle_plan(**kwargs)
    assert plan and plan["signal_id"] == deterministic_signal_id(_event(), plan)
    with pytest.raises(SimulationExecutionBlocked, match="open orders"):
        build_cycle_plan(**{**kwargs, "open_orders": [{"order_id": "x"}]})
    with pytest.raises(SimulationExecutionBlocked, match="reconciliation"):
        build_cycle_plan(**{**kwargs, "reconciliation_status": "BLOCKED"})


def test_cycle_refuses_weekday_that_qmt_calendar_does_not_confirm():
    kwargs = dict(
        now=datetime(2026, 9, 14, 10, 0, tzinfo=TZ), signal_event=_event(),
        activation_signal_not_before="20260911", sleeve_summary={"cash": 100000, "positions": []},
        ticks=_ticks(), account_id="90000001", open_orders=[], reconciliation_status="PASSED",
        trading_days=["20260911"],
    )
    with pytest.raises(SimulationExecutionBlocked, match="calendar"):
        build_cycle_plan(**kwargs)


def test_ordinary_rotation_waits_for_five_real_fill_sessions_but_risk_exit_does_not():
    kwargs = dict(
        now=datetime(2026, 9, 14, 10, 0, tzinfo=TZ),
        activation_signal_not_before="20260911",
        sleeve_summary={"cash": 1000, "positions": [{"stock_code": "160723.SZ", "quantity": 100}]},
        ticks=_ticks(), account_id="90000001", open_orders=[], reconciliation_status="PASSED",
        attributable_fills=[{"fill_id": "fill-1", "stock_code": "160723.SZ", "side": "BUY",
                              "quantity": 100, "fill_time": "1789093235"}],
        trading_days=["20260911", "20260914"],
    )
    with pytest.raises(SimulationExecutionBlocked, match="holding-period"):
        build_cycle_plan(**{**kwargs, "signal_event": _event("518880.SH", "20260911")})
    risk_event = _event("518880.SH", "20260911")
    risk_event["signal"]["reason"] = "RISK_DRAWDOWN_DIRECT_RANK"
    plan = build_cycle_plan(**{**kwargs, "signal_event": risk_event})
    assert plan and plan["side"] == "SELL"
